import calendar as month_calendar
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    AddMemberForm,
    CalendarFilterForm,
    CommentForm,
    ProjectForm,
    RegistrationForm,
    TaskSearchForm,
    TaskForm,
    TaskStatusForm,
)
from .models import Activity, Membership, Notification, Project, Task

User = get_user_model()


@require_GET
def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def _user_projects(user):
    return Project.objects.filter(Q(owner=user) | Q(members=user)).distinct()


def _record_activity(actor, project, action, task=None, detail=""):
    return Activity.objects.create(
        actor=actor,
        project=project,
        task=task,
        action=action,
        detail=detail,
    )


def _member_project_or_404(user, project_id):
    return get_object_or_404(
        Project.objects.filter(Q(owner=user) | Q(members=user)).distinct(),
        pk=project_id,
    )


def _task_or_404(project, task_id):
    return get_object_or_404(Task.objects.select_related("assignee", "created_by"), project=project, pk=task_id)


def _notify(recipient, actor, task, message):
    if recipient and recipient != actor:
        Notification.objects.create(
            recipient=recipient,
            actor=actor,
            task=task,
            message=message,
        )


@login_required
def dashboard(request):
    projects = _user_projects(request.user)
    tasks = Task.objects.filter(project__in=projects)
    today = timezone.localdate()
    totals = tasks.aggregate(
        total=Count("pk"),
        completed=Count("pk", filter=Q(status=Task.Status.COMPLETED)),
        pending=Count("pk", filter=Q(status=Task.Status.TODO)),
        in_progress=Count("pk", filter=Q(status=Task.Status.IN_PROGRESS)),
        overdue=Count(
            "pk",
            filter=Q(due_date__lt=today, status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]),
        ),
    )
    totals["progress"] = (
        round(totals["completed"] * 100 / totals["total"]) if totals["total"] else 0
    )
    totals["projects"] = projects.count()
    totals["remaining"] = totals["total"] - totals["completed"]
    recent_projects = projects.order_by("-created_at")[:5]
    recent_tasks = tasks.select_related("project", "assignee").order_by("-updated_at")[:6]
    upcoming_tasks = (
        tasks.filter(
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        )
        .exclude(status=Task.Status.COMPLETED)
        .select_related("project", "assignee")
        .order_by("due_date", "title")[:6]
    )
    recent_activities = (
        Activity.objects.filter(project__in=projects)
        .select_related("actor", "project", "task")
        .order_by("-created_at")[:8]
    )
    return render(
        request,
        "projects/dashboard.html",
        {
            "projects": recent_projects,
            "totals": totals,
            "assigned_task_count": request.user.assigned_tasks.count(),
            "recent_tasks": recent_tasks,
            "upcoming_tasks": upcoming_tasks,
            "recent_activities": recent_activities,
        },
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account is ready. Welcome!")
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("login")


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.owner = request.user
        project.save()
        Membership.objects.create(project=project, user=request.user)
        _record_activity(
            request.user,
            project,
            Activity.Action.PROJECT_CREATED,
            detail=f"Created project {project.name}.",
        )
        messages.success(request, "Project created.")
        return redirect(project)
    return render(request, "projects/project_form.html", {"form": form, "title": "Create a project"})


@login_required
def project_detail(request, project_id):
    project = _member_project_or_404(request.user, project_id)
    tasks = project.tasks.select_related("assignee", "created_by")
    columns = [
        (Task.Status.TODO, "To Do"),
        (Task.Status.IN_PROGRESS, "In Progress"),
        (Task.Status.COMPLETED, "Completed"),
    ]
    board = [(status, label, tasks.filter(status=status)) for status, label in columns]
    return render(
        request,
        "projects/project_detail.html",
        {
            "project": project,
            "board": board,
            "members": project.members.order_by("username"),
            "is_owner": project.owner_id == request.user.pk,
            "member_form": AddMemberForm(project=project),
            "completed_task_count": project.tasks.filter(status=Task.Status.COMPLETED).count(),
        },
    )


@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if project.owner_id != request.user.pk:
        raise PermissionDenied
    original_values = {
        "name": project.name,
        "description": project.description,
    }
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        changed = [
            field
            for field in ("name", "description")
            if original_values[field] != form.cleaned_data[field]
        ]
        form.save()
        if changed:
            _record_activity(
                request.user,
                project,
                Activity.Action.PROJECT_UPDATED,
                detail=f"Updated project {', '.join(changed)}.",
            )
        messages.success(request, "Project details updated.")
        return redirect(project)
    return render(
        request,
        "projects/project_form.html",
        {"form": form, "title": "Edit project", "project": project},
    )


@login_required
def project_delete(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if project.owner_id != request.user.pk:
        raise PermissionDenied
    if request.method == "POST":
        project.delete()
        messages.success(request, "Project deleted.")
        return redirect("dashboard")
    return render(
        request,
        "projects/confirm_delete.html",
        {"object": project, "cancel_url": project.get_absolute_url()},
    )


@login_required
def add_member(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if project.owner_id != request.user.pk:
        raise PermissionDenied
    form = AddMemberForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        project.members.add(form.cleaned_data["user"])
        messages.success(request, f"{form.cleaned_data['user']} was added to the project.")
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
        if request.method == "POST" and form.errors:
            messages.error(request, "Choose an eligible team member.")
    return redirect(project)


@login_required
def task_create(request, project_id):
    project = _member_project_or_404(request.user, project_id)
    form = TaskForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.created_by = request.user
        task.save()
        _record_activity(
            request.user,
            project,
            Activity.Action.TASK_CREATED,
            task=task,
            detail=f"Created task {task.title}.",
        )
        if task.assignee:
            _record_activity(
                request.user,
                project,
                Activity.Action.TASK_ASSIGNED,
                task=task,
                detail=f"Assigned {task.title} to {task.assignee.username}.",
            )
        _notify(task.assignee, request.user, task, f"You were assigned “{task.title}”.")
        messages.success(request, "Task created.")
        return redirect(task)
    return render(
        request,
        "projects/task_form.html",
        {"form": form, "title": "Create a task", "project": project},
    )


@login_required
def task_detail(request, project_id, task_id):
    project = _member_project_or_404(request.user, project_id)
    task = _task_or_404(project, task_id)
    form = CommentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
        _record_activity(
            request.user,
            project,
            Activity.Action.COMMENT_ADDED,
            task=task,
            detail=f"Commented on {task.title}.",
        )
        recipients = {task.assignee, task.created_by}
        for recipient in recipients:
            _notify(recipient, request.user, task, f"{request.user.username} commented on “{task.title}”.")
        messages.success(request, "Comment added.")
        return redirect(task)
    return render(
        request,
        "projects/task_detail.html",
        {
            "project": project,
            "task": task,
            "comment_form": form,
            "can_manage_task": project.owner_id == request.user.pk or task.created_by_id == request.user.pk,
        },
    )


@login_required
def task_edit(request, project_id, task_id):
    project = _member_project_or_404(request.user, project_id)
    task = _task_or_404(project, task_id)
    if project.owner_id != request.user.pk and task.created_by_id != request.user.pk:
        raise PermissionDenied
    old_assignee = task.assignee
    old_status = task.status
    old_priority = task.priority
    old_due_date = task.due_date
    form = TaskForm(request.POST or None, instance=task, project=project)
    if request.method == "POST" and form.is_valid():
        task = form.save()
        if task.assignee_id != (old_assignee.pk if old_assignee else None):
            action = (
                Activity.Action.TASK_ASSIGNED
                if old_assignee is None
                else Activity.Action.TASK_REASSIGNED
            )
            target = task.assignee.username if task.assignee else "no one"
            _record_activity(
                request.user,
                project,
                action,
                task=task,
                detail=f"Assigned {task.title} to {target}.",
            )
            _notify(task.assignee, request.user, task, f"You were assigned “{task.title}”.")
        if task.status != old_status:
            _record_activity(
                request.user,
                project,
                Activity.Action.TASK_STATUS_CHANGED,
                task=task,
                detail=f"Changed {task.title} to {task.get_status_display()}.",
            )
        if task.priority != old_priority:
            _record_activity(
                request.user,
                project,
                Activity.Action.TASK_PRIORITY_CHANGED,
                task=task,
                detail=f"Changed {task.title} priority to {task.get_priority_display()}.",
            )
        if task.due_date != old_due_date:
            due_date = task.due_date.isoformat() if task.due_date else "no due date"
            _record_activity(
                request.user,
                project,
                Activity.Action.TASK_DUE_DATE_CHANGED,
                task=task,
                detail=f"Changed {task.title} due date to {due_date}.",
            )
        messages.success(request, "Task updated.")
        return redirect(task)
    return render(
        request,
        "projects/task_form.html",
        {"form": form, "title": "Edit task", "project": project, "task": task},
    )


@login_required
def task_delete(request, project_id, task_id):
    project = _member_project_or_404(request.user, project_id)
    task = _task_or_404(project, task_id)
    if project.owner_id != request.user.pk and task.created_by_id != request.user.pk:
        raise PermissionDenied
    if request.method == "POST":
        task.delete()
        messages.success(request, "Task deleted.")
        return redirect(project)
    return render(
        request,
        "projects/confirm_delete.html",
        {"object": task, "cancel_url": task.get_absolute_url()},
    )


@login_required
@require_POST
def task_status(request, project_id, task_id):
    project = _member_project_or_404(request.user, project_id)
    task = _task_or_404(project, task_id)
    old_status = task.status
    form = TaskStatusForm(request.POST, instance=task)
    if form.is_valid():
        form.save()
        if task.status != old_status:
            _record_activity(
                request.user,
                project,
                Activity.Action.TASK_STATUS_CHANGED,
                task=task,
                detail=f"Changed {task.title} to {task.get_status_display()}.",
            )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "status": task.status,
                    "label": task.get_status_display(),
                    "updated_at": timezone.localtime(task.updated_at).isoformat(),
                }
            )
        messages.success(request, "Task status updated.")
    else:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"error": "Select a valid task status."}, status=400)
        messages.error(request, "Select a valid task status.")
    return redirect(project)


@login_required
@require_POST
def comment_delete(request, project_id, task_id, comment_id):
    project = _member_project_or_404(request.user, project_id)
    task = _task_or_404(project, task_id)
    comment = get_object_or_404(task.comments, pk=comment_id)
    if comment.author_id != request.user.pk and project.owner_id != request.user.pk:
        raise PermissionDenied
    comment.delete()
    messages.success(request, "Comment deleted.")
    return redirect(task)


@login_required
def notifications(request):
    items = request.user.notifications.select_related("actor", "task", "task__project")
    return render(request, "projects/notifications.html", {"notifications": items})


@login_required
@require_POST
def notification_read(request, notification_id):
    notification = get_object_or_404(request.user.notifications, pk=notification_id)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("notifications")


@login_required
def task_search(request):
    projects = _user_projects(request.user)
    members = User.objects.filter(
        Q(owned_projects__in=projects) | Q(team_projects__in=projects)
    ).distinct().order_by("username")
    form = TaskSearchForm(request.GET or None, projects=projects, members=members)
    tasks = (
        Task.objects.filter(project__in=projects)
        .select_related("project", "assignee")
        .order_by("due_date", "-updated_at")
    )
    if form.is_valid():
        filters = form.cleaned_data
        if filters["q"]:
            tasks = tasks.filter(
                Q(title__icontains=filters["q"])
                | Q(description__icontains=filters["q"])
            )
        if filters["project"]:
            tasks = tasks.filter(project=filters["project"])
        if filters["assignee"]:
            tasks = tasks.filter(assignee=filters["assignee"])
        if filters["priority"]:
            tasks = tasks.filter(priority=filters["priority"])
        if filters["status"]:
            tasks = tasks.filter(status=filters["status"])
        if filters["due_after"]:
            tasks = tasks.filter(due_date__gte=filters["due_after"])
        if filters["due_before"]:
            tasks = tasks.filter(due_date__lte=filters["due_before"])
        if filters["overdue"]:
            tasks = tasks.filter(
                due_date__lt=timezone.localdate(),
                status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS],
            )
    elif form.is_bound:
        tasks = tasks.none()
    return render(
        request,
        "projects/task_search.html",
        {"form": form, "tasks": tasks, "result_count": tasks.count()},
    )


@login_required
def calendar_view(request):
    projects = _user_projects(request.user)
    form = CalendarFilterForm(request.GET or None, projects=projects)
    form_valid = form.is_valid()
    view_mode = form.cleaned_data.get("view") if form_valid else "month"
    view_mode = view_mode or "month"
    selected_project = form.cleaned_data.get("project") if form_valid else None
    try:
        selected_date = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        selected_date = timezone.localdate()
    if selected_date.year in (date.min.year, date.max.year):
        selected_date = timezone.localdate()

    if view_mode == "week":
        range_start = selected_date - timedelta(days=selected_date.weekday())
        range_end = range_start + timedelta(days=6)
        weeks = [[range_start + timedelta(days=offset) for offset in range(7)]]
        previous_date = selected_date - timedelta(days=7)
        next_date = selected_date + timedelta(days=7)
    else:
        selected_date = selected_date.replace(day=1)
        last_day = month_calendar.monthrange(selected_date.year, selected_date.month)[1]
        range_start = selected_date - timedelta(days=selected_date.weekday())
        month_end = selected_date.replace(day=last_day)
        range_end = month_end + timedelta(days=(6 - month_end.weekday()))
        weeks = month_calendar.Calendar(firstweekday=0).monthdatescalendar(
            selected_date.year,
            selected_date.month,
        )
        previous_date = (selected_date - timedelta(days=1)).replace(day=1)
        following_month = month_end + timedelta(days=1)
        next_date = following_month.replace(day=1)

    tasks = Task.objects.filter(
        project__in=projects,
        due_date__gte=range_start,
        due_date__lte=range_end,
    ).select_related("project", "assignee").order_by("due_date", "title")
    if selected_project:
        tasks = tasks.filter(project=selected_project)
    tasks_by_date = {}
    for task in tasks:
        tasks_by_date.setdefault(task.due_date, []).append(task)
    today = timezone.localdate()
    calendar_weeks = [
        [
            {
                "date": day,
                "tasks": tasks_by_date.get(day, []),
                "in_current_month": day.month == selected_date.month,
                "is_today": day == today,
            }
            for day in week
        ]
        for week in weeks
    ]
    return render(
        request,
        "projects/calendar.html",
        {
            "form": form,
            "view_mode": view_mode,
            "selected_date": selected_date,
            "selected_project": selected_project,
            "calendar_weeks": calendar_weeks,
            "previous_date": previous_date,
            "next_date": next_date,
            "today": today,
        },
    )


@login_required
def activity_history(request):
    projects = _user_projects(request.user)
    selected_project_id = request.GET.get("project")
    activities = Activity.objects.filter(project__in=projects).select_related(
        "actor", "project", "task"
    )
    selected_project = None
    if selected_project_id:
        try:
            selected_project_id = int(selected_project_id)
        except (TypeError, ValueError):
            raise Http404
        selected_project = get_object_or_404(projects, pk=selected_project_id)
        activities = activities.filter(project=selected_project)
    return render(
        request,
        "projects/activity.html",
        {
            "activities": activities,
            "projects": projects.order_by("name"),
            "selected_project": selected_project,
        },
    )
