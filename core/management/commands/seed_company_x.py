from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    AssessmentTask,
    Competency,
    DocumentationSource,
    LearningModule,
    PracticeTask,
    RubricCriterion,
)


# Company X — Junior Python Developer.
# Base competencies are generic to the role; company-specific ones are
# what "job-ready at Company X specifically" actually means. Only a
# subset get a real assessment task in the hackathon demo — see the
# MVP scope doc for why.

BASE_COMPETENCIES = [
    {
        "name": "Python",
        "required_level": 4,
        "assessed_in_demo": True,
        "task_prompt": "Write a function `dedupe(items)` that removes duplicate "
                        "values from a list while preserving the original order. "
                        "Explain the time complexity of your solution.",
        "rubric": "Correct working solution (e.g. using a seen-set). Award full "
                   "marks only if the candidate also states the time complexity "
                   "correctly (O(n)) and shows awareness of why a naive O(n^2) "
                   "approach is worse. Partial credit for correct code without "
                   "complexity discussion.",
        "modules": [
            ("Python fundamentals refresher", 15),
            ("Writing efficient Python: complexity basics", 20),
            ("Practical Python exercises", 30),
        ],
    },
    {
        "name": "SQL",
        "required_level": 3,
        "assessed_in_demo": True,
        "task_prompt": "Given tables `orders(id, customer_id, total)` and "
                        "`customers(id, name)`, write a query that returns the "
                        "top 5 customers by total spend.",
        "rubric": "Correct JOIN between orders and customers. Correct GROUP BY "
                   "customer with SUM(total). Correct ORDER BY + LIMIT 5. Minor "
                   "syntax slips are fine; missing GROUP BY or aggregation is a "
                   "real gap.",
        "modules": [
            ("SQL joins and aggregation", 20),
            ("Practical query-writing drills", 25),
        ],
        # SQL gets the full loop — see MVP scope: multi-criterion rubric,
        # doc-grounded learning content, and a practice/reassess step.
        "criteria": [
            "Uses a JOIN between orders and customers",
            "Uses GROUP BY with SUM() to aggregate spend per customer",
            "Uses ORDER BY to sort by spend descending",
            "Uses LIMIT to return exactly 5 rows",
        ],
        "doc_sources": [
            ("PostgreSQL: SELECT / JOIN tutorial", "https://www.postgresql.org/docs/current/tutorial-join.html"),
            ("PostgreSQL: Aggregate functions", "https://www.postgresql.org/docs/current/tutorial-agg.html"),
        ],
        "practice": {
            "prompt": "Given tables `products(id, name)` and `order_items(id, "
                       "order_id, product_id, quantity)`, write a query that "
                       "returns each product name with the total quantity sold "
                       "across all orders, sorted highest first.",
            "rubric": "Correct JOIN between order_items and products. Correct "
                       "GROUP BY product with SUM(quantity). Correct ORDER BY "
                       "descending. A gap is missing the JOIN, missing "
                       "GROUP BY, or wrong aggregation.",
        },
    },
    {
        "name": "REST APIs",
        "required_level": 3,
        "assessed_in_demo": True,
        "task_prompt": "Design the endpoints (method + path) for a simple task "
                        "tracker resource: creating, listing, updating, and "
                        "deleting a task.",
        "rubric": "Correct HTTP verbs (POST/GET/PATCH or PUT/DELETE) mapped to "
                   "the right actions. Sensible resource-based paths (e.g. "
                   "/tasks/{id}). Bonus for mentioning status codes. A gap is "
                   "using the wrong verb for an action or non-RESTful paths "
                   "(e.g. /getTasks).",
        "modules": [
            ("REST API design conventions", 15),
            ("Status codes and error handling", 15),
        ],
        # REST APIs gets the full loop too — this is the demo's centerpiece
        # per the product spec's own example scenario.
        "criteria": [
            "Uses correct HTTP methods for each action (POST create, GET list, PATCH/PUT update, DELETE remove)",
            "Uses resource-based, RESTful paths (e.g. /tasks, /tasks/{id}) rather than verb-based paths",
            "Mentions appropriate HTTP status codes for at least one action",
            "Can explain the reasoning behind at least one design choice",
        ],
        "doc_sources": [
            ("MDN: HTTP request methods", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods"),
            ("MDN: HTTP response status codes", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status"),
        ],
        "practice": {
            "prompt": "Describe a REST endpoint for retrieving a single user's "
                       "profile by ID, and a separate endpoint for updating "
                       "their email address. For each, give the HTTP method, "
                       "path, and the status code you'd return on success and "
                       "on 'not found'.",
            "rubric": "GET /users/{id} for retrieval, with 200 on success and "
                       "404 if not found. PATCH (or PUT) /users/{id} for the "
                       "update, with 200 on success and 404 if not found. A gap "
                       "is using POST for either action, or omitting status codes.",
        },
    },
    {
        "name": "Git",
        "required_level": 2,
        "assessed_in_demo": True,
        "task_prompt": "You just committed and pushed a file containing a secret "
                        "API key. What do you do?",
        "rubric": "Should mention: rotating/revoking the leaked key (not just "
                   "deleting the file), removing it from history if pushed "
                   "(e.g. git filter-repo / BFG), and adding it to .gitignore "
                   "going forward. A gap is only saying 'delete the file and "
                   "commit again' without addressing the exposed key itself.",
        "modules": [
            ("Git workflows for teams", 15),
            ("Handling leaked secrets", 10),
        ],
    },
    {
        "name": "Problem Solving",
        "required_level": 4,
        "assessed_in_demo": True,
        "task_prompt": "This function is supposed to return a running total "
                        "for a list of numbers, but it has a bug:\n\n"
                        "def running_totals(nums, totals=[]):\n"
                        "    for n in nums:\n"
                        "        totals.append(n + (totals[-1] if totals else 0))\n"
                        "    return totals\n\n"
                        "Find the bug, explain why it happens, and fix it.",
        "rubric": "Should identify the mutable default argument bug (totals=[] "
                   "persists across calls) — not just a surface symptom. Fix "
                   "should use totals=None with totals = totals or [] inside "
                   "the function, or equivalent. A gap is fixing the visible "
                   "symptom without explaining the root cause.",
        "modules": [
            ("Common Python pitfalls", 15),
            ("Debugging practice set", 30),
        ],
    },
]

COMPANY_COMPETENCIES = [
    {
        "name": "Django",
        "required_level": 4,
        "assessed_in_demo": True,
        "task_prompt": "Company X soft-deletes records instead of removing them "
                        "(every model has an `is_deleted` boolean). Given a "
                        "Django model `Order(customer, total, created_at, "
                        "is_deleted)`, write a queryset returning all non-deleted "
                        "orders from the last 30 days, grouped by customer with "
                        "a total spend.",
        "rubric": "Correctly filters is_deleted=False (this is the Company "
                   "X-specific part — generic Django knowledge alone misses "
                   "it). Correct use of created_at filtering (e.g. "
                   "timezone.now() - timedelta(days=30)). Correct values() + "
                   "annotate(Sum(...)) for the grouped total. A gap is a "
                   "correct-looking generic Django queryset that ignores the "
                   "soft-delete convention.",
        "modules": [
            ("Django ORM deep dive", 25),
            ("Company X internal conventions: soft deletes & data access", 15),
        ],
    },
    {"name": "Jira", "required_level": 3, "assessed_in_demo": False},
    {"name": "Internal ERP", "required_level": 3, "assessed_in_demo": False},
    {"name": "Code review workflow", "required_level": 3, "assessed_in_demo": False},
    {"name": "Deployment process", "required_level": 3, "assessed_in_demo": False},
    {"name": "Documentation standards", "required_level": 2, "assessed_in_demo": False},
]


class Command(BaseCommand):
    help = "Seed the Company X / Junior Python Developer competency profile"

    @transaction.atomic
    def handle(self, *args, **options):
        Competency.objects.all().delete()  # idempotent — safe to rerun

        def create_group(items, scope):
            for i, item in enumerate(items):
                comp = Competency.objects.create(
                    name=item["name"],
                    scope=scope,
                    required_level=item["required_level"],
                    assessed_in_demo=item["assessed_in_demo"],
                    order=i,
                )
                if item["assessed_in_demo"]:
                    task = AssessmentTask.objects.create(
                        competency=comp,
                        prompt=item["task_prompt"],
                        rubric=item["rubric"],
                    )
                    for title, minutes in item.get("modules", []):
                        LearningModule.objects.create(
                            competency=comp, title=title, duration_minutes=minutes
                        )
                    for j, criterion_text in enumerate(item.get("criteria", [])):
                        RubricCriterion.objects.create(
                            task=task, text=criterion_text, order=j
                        )
                    for title, url in item.get("doc_sources", []):
                        DocumentationSource.objects.create(
                            competency=comp, title=title, url=url
                        )
                    if item.get("practice"):
                        PracticeTask.objects.create(
                            competency=comp,
                            prompt=item["practice"]["prompt"],
                            rubric=item["practice"]["rubric"],
                        )
                self.stdout.write(f"  {scope}: {comp.name} (required {comp.required_level})")

        self.stdout.write(self.style.SUCCESS("Base competencies:"))
        create_group(BASE_COMPETENCIES, Competency.SCOPE_BASE)

        self.stdout.write(self.style.SUCCESS("Company-specific competencies:"))
        create_group(COMPANY_COMPETENCIES, Competency.SCOPE_COMPANY)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {Competency.objects.count()} competencies, "
            f"{AssessmentTask.objects.count()} with real assessment tasks."
        ))
