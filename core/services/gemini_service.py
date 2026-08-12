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


def evaluate_answer(task_prompt: str, rubric: str, answer_text: str, required_level: int) -> dict:
    """
    Returns: {"score": int, "evidence": str, "gap_reason": str, "raw_response": dict|None}
    Falls back to a mocked response if no API key is configured yet.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")

    if not api_key or not GENAI_AVAILABLE:
        # Mocked fallback — lets you build/demo the rest of the flow
        # before the key is wired up. Never silently fails the request.
        return {
            "score": min(3, required_level),
            "evidence": "[MOCKED — set GEMINI_API_KEY to get real evaluation]",
            "gap_reason": "[MOCKED — this is a placeholder result, not a real assessment]",
            "raw_response": None,
        }

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(task_prompt, rubric, answer_text)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESULT_SCHEMA,
        ),
    )

    parsed = json.loads(response.text)
    parsed["score"] = max(1, min(5, int(parsed["score"])))  # clamp, don't trust the model blindly
    parsed["raw_response"] = parsed.copy()
    return parsed
