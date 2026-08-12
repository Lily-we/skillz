"""
Deterministic scoring — no AI involved. Gemini produces per-answer scores;
everything from here down (gaps, match %, ranking) is plain arithmetic, so
an employer can see exactly why a candidate has the match % they have.
"""
from core.models import AssessmentResult, AssessmentTask, Competency


def candidate_profile_rows(candidate):
    """
    Returns (rows, readiness_pct) for one candidate.
    rows: list of dicts, one per assessed-and-answered competency, sorted
    by gap size descending (biggest gap first).
    """
    results = (
        AssessmentResult.objects
        .filter(answer__candidate=candidate)
        .select_related("answer__task__competency")
    )

    rows = []
    for r in results:
        comp = r.competency
        rows.append({
            "competency": comp,
            "current": r.score,
            "required": comp.required_level,
            "gap": r.gap,
            "gap_reason": r.gap_reason,
            "evidence": r.evidence,
            "result": r,
        })
    rows.sort(key=lambda x: -x["gap"])

    if rows:
        # sum(demonstrated) / sum(required) — the exact formula the product
        # spec asked for, so an employer can re-derive the % by hand from
        # the numbers shown alongside it.
        readiness_pct = round(
            sum(r["current"] for r in rows) / sum(r["required"] for r in rows) * 100
        )
    else:
        readiness_pct = 0

    return rows, readiness_pct


def biggest_gap(rows):
    return rows[0] if rows and rows[0]["gap"] > 0 else None


def assessed_total():
    return AssessmentTask.objects.filter(competency__assessed_in_demo=True).count()
