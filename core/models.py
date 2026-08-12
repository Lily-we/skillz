from django.conf import settings
from django.db import models


class Competency(models.Model):
    """
    A single thing Company X requires. `scope` distinguishes the two
    kinds of requirement the whole product is built around:
    - base: generic to the role anywhere (Python, SQL, Git...)
    - company: specific to Company X (Django, Jira, internal ERP...)
    """
    SCOPE_BASE = "base"
    SCOPE_COMPANY = "company"
    SCOPE_CHOICES = [
        (SCOPE_BASE, "Base"),
        (SCOPE_COMPANY, "Company-specific"),
    ]

    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    required_level = models.PositiveSmallIntegerField(help_text="1-5")
    description = models.TextField(blank=True)

    # Only competencies flagged True get a real assessment task + Gemini
    # scoring in the hackathon demo. The rest still show on the
    # requirements screen so the profile looks complete and realistic.
    assessed_in_demo = models.BooleanField(default=False)

    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["scope", "order", "name"]
        verbose_name_plural = "competencies"

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()})"


class AssessmentTask(models.Model):
    """The practical prompt a candidate answers for one competency."""
    competency = models.OneToOneField(
        Competency, on_delete=models.CASCADE, related_name="task"
    )
    prompt = models.TextField(help_text="What we show the candidate")
    rubric = models.TextField(
        help_text="What evidence we expect — sent to Gemini as the grading rubric, not shown to the candidate"
    )

    def __str__(self):
        return f"Task: {self.competency.name}"


class Candidate(models.Model):
    """One per logged-in user. Created automatically on registration."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="candidate"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Profile fields — deliberately optional. Skillz doesn't assume a
    # traditional CS-degree background; these are shown to employers for
    # context but never used to compute competency scores.
    bio = models.TextField(blank=True)
    education = models.TextField(blank=True, help_text="Formal, self-taught, bootcamp, career switch — whatever applies")
    experience = models.TextField(blank=True)
    projects = models.TextField(blank=True)
    technologies = models.TextField(blank=True, help_text="Comma-separated or free text")
    certifications = models.TextField(blank=True)

    def __str__(self):
        return self.user.username


class AssessmentAnswer(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="answers")
    task = models.ForeignKey(AssessmentTask, on_delete=models.CASCADE, related_name="answers")
    answer_text = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("candidate", "task")


class AssessmentResult(models.Model):
    """The structured output Gemini returns for one answer."""
    answer = models.OneToOneField(AssessmentAnswer, on_delete=models.CASCADE, related_name="result")
    score = models.PositiveSmallIntegerField(help_text="1-5, demonstrated level")
    evidence = models.TextField(help_text="What in the answer supports this score")
    gap_reason = models.TextField(blank=True, help_text="Empty if no gap")
    raw_response = models.JSONField(blank=True, null=True, help_text="Full Gemini response, for debugging")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def competency(self):
        return self.answer.task.competency

    @property
    def gap(self):
        return max(self.competency.required_level - self.score, 0)


class LearningModule(models.Model):
    """A fixed pool. Gemini selects/orders from this — it doesn't invent modules."""
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=150)
    duration_minutes = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)

    def __str__(self):
        return self.title


class LearningPathItem(models.Model):
    """The ordered, personalized path generated for one candidate."""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="path_items")
    module = models.ForeignKey(LearningModule, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    reason = models.TextField(blank=True, help_text="Why this was included, e.g. from Gemini")

    class Meta:
        ordering = ["order"]


# ---------------------------------------------------------------------
# Multi-criterion rubrics. Only used for competencies that get the full
# learn -> practice -> reassess loop (REST APIs, SQL for this MVP) — see
# PracticeTask below. Other competencies keep the simpler single-score
# AssessmentResult from evaluate_answer() without criteria.
# ---------------------------------------------------------------------

class RubricCriterion(models.Model):
    """One checkable thing a good answer demonstrates, e.g. 'Uses correct HTTP method'."""
    task = models.ForeignKey(AssessmentTask, on_delete=models.CASCADE, related_name="criteria")
    text = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.text


class CriterionResult(models.Model):
    """Gemini's per-criterion verdict for one AssessmentResult."""
    STATUS_MET = "met"
    STATUS_PARTIAL = "partial"
    STATUS_MISSING = "missing"
    STATUS_CHOICES = [
        (STATUS_MET, "Met"),
        (STATUS_PARTIAL, "Partially demonstrated"),
        (STATUS_MISSING, "Missing"),
    ]

    result = models.ForeignKey(AssessmentResult, on_delete=models.CASCADE, related_name="criterion_results")
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.CharField(max_length=300, blank=True)


# ---------------------------------------------------------------------
# Trusted knowledge sourcing. Gemini is grounded against these live via
# the URL context tool — it doesn't invent explanations from training
# memory, and we don't maintain our own copy of the docs.
# ---------------------------------------------------------------------

class DocumentationSource(models.Model):
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name="doc_sources")
    title = models.CharField(max_length=150)
    url = models.URLField()

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------
# The learn -> practice -> reassess loop. Fully built for a small subset
# of competencies per the MVP scope decision; others stop at the gap
# profile.
# ---------------------------------------------------------------------

class LearningContent(models.Model):
    """A Gemini-generated lesson, targeted at one candidate's specific gap. Cached, not regenerated per view."""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="learning_contents")
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE)

    why_it_matters = models.TextField()
    concept = models.TextField()
    explanation = models.TextField()
    example = models.TextField()
    reasoning = models.TextField()
    common_mistake = models.TextField()
    key_knowledge = models.TextField()

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("candidate", "competency")


class PracticeTask(models.Model):
    """The hands-on task a candidate does after the lesson, for one competency."""
    competency = models.OneToOneField(Competency, on_delete=models.CASCADE, related_name="practice_task")
    prompt = models.TextField()
    rubric = models.TextField()

    def __str__(self):
        return f"Practice: {self.competency.name}"


class PracticeAttempt(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="practice_attempts")
    task = models.ForeignKey(PracticeTask, on_delete=models.CASCADE)
    answer_text = models.TextField()
    score_before = models.PositiveSmallIntegerField()
    score_after = models.PositiveSmallIntegerField()
    evidence = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

