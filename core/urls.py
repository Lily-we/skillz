from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="home"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("requirements/", views.requirements, name="requirements"),
    path("assessment/", views.assessment, name="assessment"),
    path("gap-profile/", views.gap_profile, name="gap_profile"),
    path("learning-path/", views.learning_path, name="learning_path"),
    path("readiness/", views.readiness, name="readiness"),

    path("learning/<int:competency_id>/", views.learning, name="learning"),
    path("practice/<int:competency_id>/", views.practice, name="practice"),

    path("dashboard/", views.dashboard, name="dashboard"),
    path("candidates/<int:candidate_id>/", views.candidate_detail, name="candidate_detail"),
]
