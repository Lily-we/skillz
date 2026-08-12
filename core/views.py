from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RegisterForm
from .models import (
    AssessmentAnswer,
    AssessmentResult,
    AssessmentTask,
    Candidate,
    Competency,
    CriterionResult,
    DocumentationSource,
    LearningContent,
    LearningPathItem,
    PracticeAttempt,
    PracticeTask,
)
from .services.gemini_service import evaluate_answer, generate_learning_content
from .services.scoring import assessed_total, biggest_gap, candidate_profile_rows


def landing(request):
    return render(request, "core/landing.html")


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)  # Candidate is auto-created via signal
            return redirect("requirements")
    else:
        form = RegisterForm()
    return render(request, "core/register.html", {"form": form})


def requirements(request):
    base = Competency.objects.filter(scope=Competency.SCOPE_BASE)
    company = Competency.objects.filter(scope=Competency.SCOPE_COMPANY)
    return render(request, "core/requirements.html", {
        "base_competencies": base,
        "company_competencies": company,
    })


@login_required
def assessment(request):
    candidate = request.user.candidate
    tasks = AssessmentTask.objects.filter(
        competency__assessed_in_demo=True
    ).select_related("competency").prefetch_related("criteria").order_by(
        "competency__scope", "competency__order"
    )

    existing = {
        a.task_id: a for a in AssessmentAnswer.objects.filter(candidate=candidate)
    }

    if request.method == "POST":
        for task in tasks:
            answer_text = request.POST.get(f"task_{task.id}", "").strip()
            if not answer_text:
                continue  # allow partial submission — demo mode

            answer, _ = AssessmentAnswer.objects.update_or_create(
                candidate=candidate, task=task,
                defaults={"answer_text": answer_text},
            )

            criteria_qs = list(task.criteria.all())
            criteria_texts = [c.text for c in criteria_qs] if criteria_qs else None

            result = evaluate_answer(
                task_prompt=task.prompt,
                rubric=task.rubric,
                answer_text=answer_text,
                required_level=task.competency.required_level,
                criteria=criteria_texts,
            )
            assessment_result, _ = AssessmentResult.objects.update_or_create(
                answer=answer,
                defaults={
                    "score": result["score"],
                    "evidence": result["evidence"],
                    "gap_reason": result["gap_reason"],
                    "raw_response": result.get("raw_response"),
                },
            )

            # Store per-criterion verdicts if this task had them
            CriterionResult.objects.filter(result=assessment_result).delete()
            if result.get("criteria"):
                by_text = {c.text: c for c in criteria_qs}
                for verdict in result["criteria"]:
                    criterion = by_text.get(verdict["criterion"])
                    if criterion:
                        CriterionResult.objects.create(
                            result=assessment_result,
                            criterion=criterion,
                            status=verdict["status"],
                            note=verdict.get("note", ""),
                        )
        return redirect("gap_profile")

    return render(request, "core/assessment.html", {
        "tasks": tasks,
        "existing": existing,
    })


@login_required
def gap_profile(request):
    candidate = request.user.candidate
    rows, readiness_pct = candidate_profile_rows(candidate)

    # Which gapped competencies have the full learn->practice loop built
    for row in rows:
        row["has_practice"] = hasattr(row["competency"], "practice_task")

    return render(request, "core/gap_profile.html", {
        "rows": rows,
        "biggest_gap": biggest_gap(rows),
        "readiness_pct": readiness_pct,
        "answered_count": len(rows),
        "assessed_total": assessed_total(),
    })


@login_required
def learning_path(request):
    candidate = request.user.candidate
    results = (
        AssessmentResult.objects
        .filter(answer__candidate=candidate)
        .select_related("answer__task__competency")
    )

    LearningPathItem.objects.filter(candidate=candidate).delete()  # regenerate each visit

    gapped = [r for r in results if r.gap > 0]
    gapped.sort(key=lambda r: (
        0 if r.competency.scope == Competency.SCOPE_BASE else 1,
        -r.gap,
    ))

    order = 0
    path_items = []
    for r in gapped:
        modules = r.competency.modules.all()
        for module in modules:
            order += 1
            item = LearningPathItem.objects.create(
                candidate=candidate,
                module=module,
                order=order,
                reason=r.gap_reason,
            )
            path_items.append(item)

    return render(request, "core/learning_path.html", {
        "path_items": path_items,
        "has_gaps": bool(gapped),
    })


@login_required
def readiness(request):
    candidate = request.user.candidate
    results = (
        AssessmentResult.objects
        .filter(answer__candidate=candidate)
        .select_related("answer__task__competency")
    )
    interview_focus = [
        r.competency for r in results if r.competency.required_level >= 4
    ]
    return render(request, "core/readiness.html", {
        "interview_focus": interview_focus,
    })


@login_required
def learning(request, competency_id):
    """
    The personalized lesson. Only reachable for a competency the candidate
    actually has a gap in AND that has a PracticeTask built — see MVP scope.
    Generated once via Gemini (grounded in DocumentationSource URLs), then cached.
    """
    candidate = request.user.candidate
    competency = get_object_or_404(Competency, id=competency_id)

    if not hasattr(competency, "practice_task"):
        return redirect("gap_profile")

    result = (
        AssessmentResult.objects
        .filter(answer__candidate=candidate, answer__task__competency=competency)
        .select_related("answer__task__competency")
        .first()
    )
    if not result or result.gap <= 0:
        return redirect("gap_profile")

    content = LearningContent.objects.filter(candidate=candidate, competency=competency).first()
    if not content:
        doc_urls = list(competency.doc_sources.values_list("url", flat=True))
        generated = generate_learning_content(
            competency_name=competency.name,
            gap_reason=result.gap_reason,
            evidence=result.evidence,
            doc_urls=doc_urls,
        )
        content = LearningContent.objects.create(
            candidate=candidate, competency=competency, **generated
        )

    return render(request, "core/learning.html", {
        "competency": competency,
        "content": content,
        "doc_sources": competency.doc_sources.all(),
        "result": result,
    })


@login_required
def practice(request, competency_id):
    """The hands-on task after the lesson. Submitting re-scores the competency in place."""
    candidate = request.user.candidate
    competency = get_object_or_404(Competency, id=competency_id)
    practice_task = get_object_or_404(PracticeTask, competency=competency)

    result = (
        AssessmentResult.objects
        .filter(answer__candidate=candidate, answer__task__competency=competency)
        .first()
    )
    score_before = result.score if result else 1

    if request.method == "POST":
        answer_text = request.POST.get("answer", "").strip()
        if answer_text:
            evaluated = evaluate_answer(
                task_prompt=practice_task.prompt,
                rubric=practice_task.rubric,
                answer_text=answer_text,
                required_level=competency.required_level,
            )
            # Never let one practice attempt jump straight to mastery —
            # at most one level of improvement per attempt, grounded in
            # what the model actually scored, not automatically 5/5.
            score_after = min(evaluated["score"], score_before + 1, 5)

            PracticeAttempt.objects.create(
                candidate=candidate,
                task=practice_task,
                answer_text=answer_text,
                score_before=score_before,
                score_after=score_after,
                evidence=evaluated["evidence"],
            )

            if result:
                result.score = score_after
                result.evidence = evaluated["evidence"]
                result.gap_reason = evaluated["gap_reason"] if score_after < competency.required_level else ""
                result.save()

            return render(request, "core/practice_result.html", {
                "competency": competency,
                "score_before": score_before,
                "score_after": score_after,
                "evidence": evaluated["evidence"],
                "required": competency.required_level,
                "met": score_after >= competency.required_level,
            })

    return render(request, "core/practice.html", {
        "competency": competency,
        "practice_task": practice_task,
        "score_before": score_before,
    })


def dashboard(request):
    """Employer view — read-only, no employer accounts for this MVP (see product spec)."""
    candidates = Candidate.objects.select_related("user").all()
    rows = []
    for c in candidates:
        c_rows, pct = candidate_profile_rows(c)
        if not c_rows:
            continue  # hasn't taken the assessment yet
        gaps = [r["competency"].name for r in c_rows if r["gap"] > 0]
        rows.append({
            "candidate": c,
            "match_pct": pct,
            "gaps": gaps,
        })
    rows.sort(key=lambda x: -x["match_pct"])

    return render(request, "core/dashboard.html", {"rows": rows})


def candidate_detail(request, candidate_id):
    candidate = get_object_or_404(Candidate, id=candidate_id)
    rows, pct = candidate_profile_rows(candidate)
    practice_history = PracticeAttempt.objects.filter(candidate=candidate).select_related("task__competency")

    return render(request, "core/candidate_detail.html", {
        "candidate": candidate,
        "rows": rows,
        "match_pct": pct,
        "practice_history": practice_history,
    })
