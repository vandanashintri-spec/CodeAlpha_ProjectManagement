from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("health/", views.health_check, name="health_check"),
    path("tasks/", views.task_search, name="task_search"),
    path("calendar/", views.calendar_view, name="calendar"),
    path("activity/", views.activity_history, name="activity_history"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:project_id>/", views.project_detail, name="project_detail"),
    path("projects/<int:project_id>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:project_id>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:project_id>/members/", views.add_member, name="add_member"),
    path("projects/<int:project_id>/tasks/new/", views.task_create, name="task_create"),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/",
        views.task_detail,
        name="task_detail",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/edit/",
        views.task_edit,
        name="task_edit",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/delete/",
        views.task_delete,
        name="task_delete",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/status/",
        views.task_status,
        name="task_status",
    ),
    path(
        "projects/<int:project_id>/tasks/<int:task_id>/comments/<int:comment_id>/delete/",
        views.comment_delete,
        name="comment_delete",
    ),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:notification_id>/read/", views.notification_read, name="notification_read"),
]
