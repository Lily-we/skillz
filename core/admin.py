from django.contrib import admin

from .models import (
    AssessmentAnswer,
    AssessmentResult,
    AssessmentTask,
    Candidate,
    Competency,
    CriterionResult,
    DocumentationSource,
    LearningContent,
    LearningModule,
    LearningPathItem,
    PracticeAttempt,
    PracticeTask,
    RubricCriterion,
)


@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "required_level", "assessed_in_demo")
    list_filter = ("scope", "assessed_in_demo")


@admin.register(AssessmentTask)
class AssessmentTaskAdmin(admin.ModelAdmin):
    list_display = ("competency",)


@admin.register(RubricCriterion)
class RubricCriterionAdmin(admin.ModelAdmin):
    list_display = ("task", "text", "order")


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")


@admin.register(AssessmentAnswer)
class AssessmentAnswerAdmin(admin.ModelAdmin):
    list_display = ("candidate", "task", "submitted_at")


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = ("answer", "score", "gap")


@admin.register(CriterionResult)
class CriterionResultAdmin(admin.ModelAdmin):
    list_display = ("result", "criterion", "status")


@admin.register(DocumentationSource)
class DocumentationSourceAdmin(admin.ModelAdmin):
    list_display = ("competency", "title", "url")


@admin.register(LearningModule)
class LearningModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "competency", "duration_minutes")


@admin.register(LearningPathItem)
class LearningPathItemAdmin(admin.ModelAdmin):
    list_display = ("candidate", "module", "order")


@admin.register(LearningContent)
class LearningContentAdmin(admin.ModelAdmin):
    list_display = ("candidate", "competency", "generated_at")


@admin.register(PracticeTask)
class PracticeTaskAdmin(admin.ModelAdmin):
    list_display = ("competency",)


@admin.register(PracticeAttempt)
class PracticeAttemptAdmin(admin.ModelAdmin):
    list_display = ("candidate", "task", "score_before", "score_after", "submitted_at")
