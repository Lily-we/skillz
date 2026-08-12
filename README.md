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
  AssessmentTask, Candidate, AssessmentAnswer, AssessmentResult,
  LearningModule, LearningPathItem
- `core/services/gemini_service.py` — the only file that calls Gemini.
  Takes a task prompt + rubric + candidate answer, returns structured JSON
  `{score, evidence, gap_reason}`. Falls back to a clearly-labeled mocked
  result if `GEMINI_API_KEY` isn't set, so the rest of the app stays
  demoable without the key.
- `core/management/commands/seed_company_x.py` — seeds the whole Company X
  profile + assessment tasks + learning module pool. Safe to rerun.

## Still to build

- Views/templates for the actual screens (requirements → assessment →
  gap dashboard → learning path)
- Deterministic gap-calculation + readiness-score logic wired to real data
- Learning path generation (Gemini selects/orders from the fixed
  LearningModule pool per candidate's gaps)

## Security note

`.env` is gitignored — never commit it. `.env.example` is the template
that's safe to commit. If you ever paste a real key somewhere it
shouldn't be, rotate it immediately in AI Studio.
