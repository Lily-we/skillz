"""
This is the one file that actually talks to Gemini.

Deliberately narrow: it takes a task's prompt + rubric + a candidate's
answer, and returns a *structured* score. It does NOT decide what the
assessment is, does NOT invent competencies, and does NOT freeform-chat.
That structure lives in models.py / seed data — Gemini operates inside it.

If GEMINI_API_KEY isn't set, evaluate_answer() returns a clearly-fake
mocked result instead of crashing, so the rest of the app is demoable
even before you've wired up the key.
"""
import json
import os

from django.conf import settings

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# The exact shape Gemini must return. Passing this as response_schema
# forces structured JSON output instead of letting the model ramble —
# this is what makes the score usable by deterministic code downstream.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "Demonstrated competency level, 1-5, judged strictly against the rubric",
        },
        "evidence": {
            "type": "string",
            "description": "1-2 sentences: what in the answer specifically supports this score",
        },
        "gap_reason": {
            "type": "string",
            "description": "1-2 sentences: what's missing vs the required level. Empty string if score meets or exceeds the required level.",
        },
    },
    "required": ["score", "evidence", "gap_reason"],
}

# Used when the task has explicit RubricCriterion rows — REST APIs and SQL
# for this MVP. Gemini judges each criterion independently instead of one
# holistic "is this correct" call; the score is still derived deterministically
# in Python from these verdicts, not invented by the model. See
# _score_from_criteria() below.
CRITERIA_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "description": "Restate the criterion text exactly as given"},
                    "status": {"type": "string", "enum": ["met", "partial", "missing"]},
                    "note": {"type": "string", "description": "1 sentence: evidence or what's missing for this criterion"},
                },
                "required": ["criterion", "status", "note"],
            },
        },
        "evidence": {
            "type": "string",
            "description": "1-2 sentence overall summary of what the answer demonstrates",
        },
        "gap_reason": {
            "type": "string",
            "description": "1-2 sentences: what's missing overall. Empty string if all criteria are met.",
        },
    },
    "required": ["criteria", "evidence", "gap_reason"],
}


def _model_name() -> str:
    # Configurable via env so a future Google model rename doesn't require
    # a code change — gemini-2.5-flash was deprecated for new API keys as
    # of mid-2026; gemini-3.6-flash is the current stable default.
    return os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def _get_api_key():
    return getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")


def _score_from_criteria(criteria_verdicts: list, required_level: int) -> int:
    """
    Deterministic score derivation from per-criterion verdicts — NOT
    left to Gemini to invent. met=1 point, partial=0.5, missing=0, scaled
    to the 1-5 range relative to how many criteria exist.
    """
    if not criteria_verdicts:
        return 1
    points = sum(
        1.0 if v["status"] == "met" else 0.5 if v["status"] == "partial" else 0.0
        for v in criteria_verdicts
    )
    fraction = points / len(criteria_verdicts)
    # Map 0-1 fraction onto 1-5, then never exceed required+1 for a
    # "meets and slightly exceeds" ceiling — keeps scores grounded in the
    # actual criteria rather than let a lucky mapping hit 5/5 on a 60% answer.
    score = round(1 + fraction * 4)
    return max(1, min(5, score))


def _build_prompt(task_prompt: str, rubric: str, answer_text: str) -> str:
    return f"""You are grading a candidate's answer to a practical assessment task
for a Junior Python Developer role at a specific company.

TASK GIVEN TO CANDIDATE:
{task_prompt}

GRADING RUBRIC (what evidence to look for — the candidate did not see this):
{rubric}

CANDIDATE'S ANSWER:
{answer_text}

Score strictly against the rubric on a 1-5 scale:
1 = no relevant understanding shown
2 = surface-level, mostly incorrect or missing key ideas
3 = partially correct, meets some but not all rubric criteria
4 = solid, meets rubric criteria with minor gaps
5 = fully meets rubric criteria with clear reasoning

Be skeptical of answers that look generic or copy-pasted without
reasoning specific to this task — score those lower on evidence, not
by trying to detect whether AI was used.
"""


def _build_criteria_prompt(task_prompt: str, criteria: list, answer_text: str) -> str:
    criteria_list = "\n".join(f"- {c}" for c in criteria)
    return f"""You are grading a candidate's answer to a practical assessment task
for a Junior Python Developer role at a specific company.

TASK GIVEN TO CANDIDATE:
{task_prompt}

EVALUATION CRITERIA (judge each one independently — the candidate did not see this list):
{criteria_list}

CANDIDATE'S ANSWER:
{answer_text}

For EACH criterion above, decide: met, partial, or missing, with one
sentence of evidence or explanation. Do not give a single holistic pass/fail —
judge every criterion on its own.

Be skeptical of answers that look generic or copy-pasted without
reasoning specific to this task.
"""


def evaluate_answer(task_prompt: str, rubric: str, answer_text: str, required_level: int, criteria: list = None) -> dict:
    """
    Returns: {"score": int, "evidence": str, "gap_reason": str, "raw_response": dict|None,
              "criteria": list|None}
    Falls back to a mocked response if no API key is configured yet.

    If `criteria` (list of RubricCriterion text strings) is passed, Gemini
    judges each independently and the score is derived deterministically
    from those verdicts rather than asked for directly.
    """
    api_key = _get_api_key()

    if not api_key or not GENAI_AVAILABLE:
        # Mocked fallback — lets you build/demo the rest of the flow
        # before the key is wired up. Never silently fails the request.
        mocked = {
            "score": min(3, required_level),
            "evidence": "[MOCKED — set GEMINI_API_KEY to get real evaluation]",
            "gap_reason": "[MOCKED — this is a placeholder result, not a real assessment]",
            "raw_response": None,
            "criteria": None,
        }
        if criteria:
            mocked["criteria"] = [
                {"criterion": c, "status": "partial", "note": "[MOCKED]"} for c in criteria
            ]
        return mocked

    client = genai.Client(api_key=api_key)

    if criteria:
        prompt = _build_criteria_prompt(task_prompt, criteria, answer_text)
        response = client.models.generate_content(
            model=_model_name(),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CRITERIA_RESULT_SCHEMA,
            ),
        )
        parsed = json.loads(response.text)
        parsed["score"] = _score_from_criteria(parsed["criteria"], required_level)
        parsed["raw_response"] = parsed.copy()
        return parsed

    prompt = _build_prompt(task_prompt, rubric, answer_text)
    response = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESULT_SCHEMA,
        ),
    )

    parsed = json.loads(response.text)
    parsed["score"] = max(1, min(5, int(parsed["score"])))  # clamp, don't trust the model blindly
    parsed["raw_response"] = parsed.copy()
    parsed["criteria"] = None
    return parsed


LEARNING_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "why_it_matters": {"type": "string"},
        "concept": {"type": "string", "description": "The specific concept the candidate needs, named plainly"},
        "explanation": {"type": "string", "description": "2-4 sentences, grounded in the provided documentation"},
        "example": {"type": "string", "description": "A short code or realistic example, grounded in the docs"},
        "reasoning": {"type": "string", "description": "Why the example works, 2-3 sentences"},
        "common_mistake": {"type": "string", "description": "The specific mistake this candidate's answer showed"},
        "key_knowledge": {"type": "string", "description": "1-2 sentence summary to remember"},
    },
    "required": ["why_it_matters", "concept", "explanation", "example", "reasoning", "common_mistake", "key_knowledge"],
}


def generate_learning_content(competency_name: str, gap_reason: str, evidence: str, doc_urls: list) -> dict:
    """
    Grounds the lesson in the actual content at doc_urls via Gemini's
    url_context tool, rather than Gemini's training memory or a knowledge
    base we'd have to maintain ourselves. Targets only the specific gap —
    not a general course on the competency.
    """
    api_key = _get_api_key()

    if not api_key or not GENAI_AVAILABLE:
        return {
            "why_it_matters": "[MOCKED — set GEMINI_API_KEY for real, doc-grounded content]",
            "concept": f"{competency_name} (mocked)",
            "explanation": "[MOCKED]",
            "example": "[MOCKED]",
            "reasoning": "[MOCKED]",
            "common_mistake": "[MOCKED]",
            "key_knowledge": "[MOCKED]",
        }

    client = genai.Client(api_key=api_key)
    doc_list = "\n".join(f"- {u}" for u in doc_urls)

    prompt = f"""A candidate for a Junior Python Developer role was assessed on {competency_name}
and has a gap.

WHAT THEIR ANSWER SHOWED: {evidence}
SPECIFIC GAP IDENTIFIED: {gap_reason}

OFFICIAL DOCUMENTATION TO GROUND YOUR LESSON IN (use the url_context tool to
read these — do not rely on your own training memory for facts about this topic):
{doc_list}

Write a short, targeted lesson that closes EXACTLY this gap — nothing more.
Do NOT teach the whole topic. Do NOT include material the candidate already
demonstrated. Base your explanation and example on the actual content of the
documentation links above.
"""

    tools = [types.Tool(url_context=types.UrlContext())]
    response = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=tools,
            response_mime_type="application/json",
            response_schema=LEARNING_CONTENT_SCHEMA,
        ),
    )
    return json.loads(response.text)
