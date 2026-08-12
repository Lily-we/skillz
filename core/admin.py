from django.contrib import admin

from .models import (
    AssessmentAnswer,
    AssessmentResult,
    AssessmentTask,
    Candidate,
    Competency,
    LearningModule,
    LearningPathItem,
)


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "required_level", "assessed_in_demo")
    list_filter = ("scope", "assessed_in_demo")


@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
    list_display = ("competency",)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("candidate", "task", "submitted_at")


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("answer", "score", "gap")


@admin.register(LearningModule)
class LearningModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "competency", "duration_minutes")


@admin.register(LearningPathItem)
class LearningPathItemAdmin(admin.ModelAdmin):
    list_display = ("candidate", "module", "order")
