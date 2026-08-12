# Skillz — MVP backend

AI-powered job-readiness platform. Demo scope: Company X / Junior Python
Developer, 11 competencies (5 base + 6 company-specific), 6 with a real
Gemini-scored assessment task.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit .env and paste your real GEMINI_API_KEY
python manage.py migrate
python manage.py seed_company_x
python manage.py createsuperuser   # optional, to browse data at /admin/
python manage.py runserver
```

Get a free Gemini API key at https://aistudio.google.com — sidebar → "Get API
key" → "Create API key". No billing needed for the free tier.

## What's here so far

- `core/models.py` — the data model: Competency (base vs company-specific),
  AssessmentTask + RubricCriterion (multi-criterion for REST APIs/SQL),
  Candidate (tied 1:1 to a Django User, with optional profile fields),
  AssessmentAnswer, AssessmentResult + CriterionResult, LearningModule,
  LearningPathItem, DocumentationSource, LearningContent, PracticeTask,
  PracticeAttempt
- `core/services/gemini_service.py` — the only file that calls Gemini:
  - `evaluate_answer()` — single-score or (if `criteria` passed)
    per-criterion evaluation; the final score is always derived
    deterministically in Python from Gemini's verdicts, never asked
    for directly
  - `generate_learning_content()` — grounds the lesson in real doc URLs
    via Gemini's `url_context` tool, targeted at the candidate's
    specific gap, not a general course
  - Both fall back to clearly-labeled mocked output if `GEMINI_API_KEY`
    isn't set
- `core/services/scoring.py` — deterministic gap/match-% math, shared by
  the candidate gap profile and the employer dashboard so they can never
  disagree
- `core/management/commands/seed_company_x.py` — seeds Company X's full
  profile: 11 competencies, 6 assessment tasks, rubric criteria + doc
  sources + practice tasks for REST APIs and SQL (the two competencies
  with the full learn→practice→reassess loop, per MVP scope)
- Full page flow, verified end to end via curl with a real DB:
  - `/` `/register/` `/login/` `/logout/` — landing + real Django auth
  - `/requirements/` — Company X's 11 competencies
  - `/assessment/` — 6 tasks; REST APIs/SQL show per-criterion evaluation
  - `/gap-profile/` — readiness %, per-competency gap, criteria chips,
    "Start personalized learning" link where the full loop exists
  - `/learning/<id>/` — Gemini-generated lesson grounded in official docs
  - `/practice/<id>/` — practice task; submitting re-scores the
    competency in place (capped at +1 level per attempt, never jumps
    straight to mastery)
  - `/learning-path/`, `/readiness/` — unchanged from before
  - `/dashboard/` — employer view, candidates ranked by match %
  - `/candidates/<id>/` — full profile + evidence + development path +
    "Contact Skillz" placeholder

## Still to build

- Visual polish pass
- Candidate profile edit form (fields exist on the model; no UI to fill
  them in yet — currently editable only via `/admin/`)
- "Move to next weakest gap" isn't automatic yet — after a practice
  attempt, the candidate goes back to the gap profile and picks manually
- Reassessment for competencies outside REST APIs/SQL

## Security note

`.env` is gitignored — never commit it. `.env.example` is the template
that's safe to commit. If you ever paste a real key somewhere it
shouldn't be, rotate it immediately in AI Studio.
