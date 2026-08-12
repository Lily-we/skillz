from django.shortcuts import render

from .models import Competency


def home(request):
    """
    Requirements screen — the one we're using to prove the base template
    renders real Company X data correctly before building the rest.
    """
    base = Competency.objects.filter(scope=Competency.SCOPE_BASE)
    company = Competency.objects.filter(scope=Competency.SCOPE_COMPANY)
    return render(request, "core/home.html", {
        "base_competencies": base,
        "company_competencies": company,
    })
