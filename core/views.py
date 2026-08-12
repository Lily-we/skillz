from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import RegisterForm
from .models import (
    AssessmentAnswer,
    AssessmentResult,
    AssessmentTask,
    Competency,
    LearningPathItem,
)
from .services.gemini_service import evaluate_answer


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
    ).select_related("competency").order_by("competency__scope", "competency__order")

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

            result = evaluate_answer(
                task_prompt=task.prompt,
                rubric=task.rubric,
                answer_text=answer_text,
                required_level=task.competency.required_level,
            )
            AssessmentResult.objects.update_or_create(
                answer=answer,
                defaults={
                    "score": result["score"],
                    "evidence": result["evidence"],
                    "gap_reason": result["gap_reason"],
                    "raw_response": result.get("raw_response"),
                },
            )
        return redirect("gap_profile")

    return render(request, "core/assessment.html", {
        "tasks": tasks,
        "existing": existing,
    })


@login_required
def gap_profile(request):
    candidate = request.user.candidate
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
        })
    rows.sort(key=lambda x: -x["gap"])

    biggest_gap = rows[0] if rows and rows[0]["gap"] > 0 else None

    assessed_total = AssessmentTask.objects.filter(competency__assessed_in_demo=True).count()
    if rows:
        readiness_pct = round(
            sum(min(r["current"] / r["required"], 1) for r in rows) / len(rows) * 100
        )
    else:
        readiness_pct = 0

    return render(request, "core/gap_profile.html", {
        "rows": rows,
        "biggest_gap": biggest_gap,
        "readiness_pct": readiness_pct,
        "answered_count": len(rows),
        "assessed_total": assessed_total,
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
    # Base gaps first, then company-specific — the "you already know Python,
    # so you get Django/company-conventions, not another Python course" idea.
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
