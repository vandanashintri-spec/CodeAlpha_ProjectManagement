import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from config.settings import _debug_default

from .models import Activity, Membership, Notification, Project, Task, TaskComment

User = get_user_model()


class ProjectManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="StrongPass123!")
        self.member = User.objects.create_user(username="member", password="StrongPass123!")
        self.outsider = User.objects.create_user(username="outsider", password="StrongPass123!")
        self.project = Project.objects.create(name="Launch plan", owner=self.owner)
        Membership.objects.create(project=self.project, user=self.owner)
        Membership.objects.create(project=self.project, user=self.member)
        self.task = Task.objects.create(
            project=self.project,
            title="Prepare release notes",
            created_by=self.owner,
            assignee=self.member,
        )

    def test_registration_creates_user_and_logs_them_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newperson",
                "email": "new@example.com",
                "password1": "A-very-strong-password-2026",
                "password2": "A-very-strong-password-2026",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="newperson")
        self.assertTrue(user.check_password("A-very-strong-password-2026"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_rejects_bad_credentials_and_logout_is_post_only(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.owner.username, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password")
        response = self.client.post(
            reverse("login"),
            {"username": self.owner.username, "password": "StrongPass123!"},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertRedirects(self.client.get(reverse("dashboard")), f"{reverse('login')}?next=/")

    def test_csrf_is_required_for_authenticated_mutations(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        response = csrf_client.post(
            reverse("task_status", args=[self.project.pk, self.task.pk]),
            {"status": Task.Status.COMPLETED},
        )
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)

    def test_database_health_endpoint(self):
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            self.client.post(reverse("health_check")).status_code,
            405,
        )

    def test_debug_defaults_off_when_deployment_environment_is_present(self):
        with patch.dict(
            os.environ,
            {"DJANGO_SECRET_KEY": "deployment-key", "ALLOWED_HOSTS": "example.com"},
            clear=True,
        ):
            self.assertFalse(_debug_default())

    def test_dashboard_requires_login_and_project_creation_adds_owner(self):
        self.assertRedirects(self.client.get(reverse("dashboard")), f"{reverse('login')}?next=/")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        response = self.client.post(
            reverse("project_create"),
            {"name": "New initiative", "description": "A new project."},
        )
        created = Project.objects.get(name="New initiative")
        self.assertRedirects(response, created.get_absolute_url())
        self.assertTrue(created.members.filter(pk=self.owner.pk).exists())

    def test_project_board_task_and_notification_pages_render(self):
        self.client.force_login(self.owner)
        urls = [
            reverse("project_detail", args=[self.project.pk]),
            reverse("task_detail", args=[self.project.pk, self.task.pk]),
            reverse("notifications"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_project_membership_and_owner_permissions(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.project.get_absolute_url()).status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("project_edit", args=[self.project.pk])).status_code,
            403,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("add_member", args=[self.project.pk]),
            {"user": self.outsider.pk},
        )
        self.assertRedirects(response, self.project.get_absolute_url())
        self.assertTrue(self.project.members.filter(pk=self.outsider.pk).exists())

    def test_assignment_comment_and_read_notifications(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("task_create", args=[self.project.pk]),
            {
                "title": "New assigned task",
                "assignee": self.member.pk,
                "priority": Task.Priority.MEDIUM,
                "status": Task.Status.TODO,
            },
        )
        task = Task.objects.get(project=self.project, title="New assigned task")
        assignment = Notification.objects.get(recipient=self.member, task=task)
        self.assertIn("assigned", assignment.message)
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("task_detail", args=[self.project.pk, task.pk]),
            {"body": "I have started this task."},
        )
        self.assertRedirects(response, task.get_absolute_url())
        comment = TaskComment.objects.get(task=task)
        self.assertEqual(comment.author, self.member)
        comment_notice = Notification.objects.get(
            recipient=self.owner,
            task=task,
            message__contains="commented",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("notification_read", args=[comment_notice.pk]),
        )
        self.assertRedirects(response, reverse("notifications"))
        comment_notice.refresh_from_db()
        self.assertIsNotNone(comment_notice.read_at)

    def test_member_can_move_status_but_cannot_edit_or_delete_task(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("task_status", args=[self.project.pk, self.task.pk]),
            {"status": Task.Status.IN_PROGRESS},
        )
        self.assertRedirects(response, self.project.get_absolute_url())
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(
            self.client.get(reverse("task_edit", args=[self.project.pk, self.task.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("task_delete", args=[self.project.pk, self.task.pk]),
            ).status_code,
            403,
        )

    def test_task_creation_validates_assignee_against_project_members(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("task_create", args=[self.project.pk]),
            {
                "title": "Outsider assignment",
                "assignee": self.outsider.pk,
                "priority": Task.Priority.HIGH,
                "status": Task.Status.TODO,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Task.objects.filter(title="Outsider assignment").exists())

    def test_dashboard_uses_database_totals_and_project_progress(self):
        today = timezone.localdate()
        Task.objects.create(
            project=self.project,
            title="Overdue task",
            created_by=self.owner,
            due_date=today - timezone.timedelta(days=1),
        )
        Task.objects.create(
            project=self.project,
            title="Active task",
            created_by=self.owner,
            status=Task.Status.IN_PROGRESS,
            due_date=today + timezone.timedelta(days=2),
        )
        Task.objects.create(
            project=self.project,
            title="Finished task",
            created_by=self.owner,
            status=Task.Status.COMPLETED,
            due_date=today - timezone.timedelta(days=3),
        )
        other_project = Project.objects.create(name="Private project", owner=self.outsider)
        Task.objects.create(
            project=other_project,
            title="Not visible",
            created_by=self.outsider,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dashboard"))
        totals = response.context["totals"]
        self.assertEqual(totals["projects"], 1)
        self.assertEqual(totals["total"], 4)
        self.assertEqual(totals["completed"], 1)
        self.assertEqual(totals["pending"], 2)
        self.assertEqual(totals["in_progress"], 1)
        self.assertEqual(totals["overdue"], 1)
        self.assertEqual(totals["progress"], 25)

    def test_ajax_board_status_update_persists_and_checks_membership(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("task_status", args=[self.project.pk, self.task.pk]),
            {"status": Task.Status.COMPLETED},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Task.Status.COMPLETED)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)
        self.assertTrue(
            Activity.objects.filter(
                task=self.task,
                actor=self.member,
                action=Activity.Action.TASK_STATUS_CHANGED,
            ).exists()
        )
        self.client.force_login(self.outsider)
        denied = self.client.post(
            reverse("task_status", args=[self.project.pk, self.task.pk]),
            {"status": Task.Status.TODO},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(denied.status_code, 404)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)

    def test_calendar_limits_dates_and_filters_to_selected_project(self):
        due_date = timezone.localdate() + timezone.timedelta(days=5)
        first = Task.objects.create(
            project=self.project,
            title="Calendar included",
            created_by=self.owner,
            due_date=due_date,
        )
        second_project = Project.objects.create(name="Second project", owner=self.owner)
        Membership.objects.create(project=second_project, user=self.owner)
        second = Task.objects.create(
            project=second_project,
            title="Calendar excluded",
            created_by=self.owner,
            due_date=due_date,
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("calendar"),
            {
                "view": "week",
                "date": due_date.isoformat(),
                "project": self.project.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first.title)
        self.assertNotContains(response, second.title)
        self.assertEqual(response.context["view_mode"], "week")
        self.assertEqual(len(response.context["calendar_weeks"][0]), 7)
        month_response = self.client.get(
            reverse("calendar"),
            {
                "view": "month",
                "date": due_date.isoformat(),
                "project": self.project.pk,
            },
        )
        self.assertContains(month_response, first.title)
        self.assertEqual(month_response.context["selected_date"].day, 1)
        invalid_date = self.client.get(
            reverse("calendar"),
            {"view": "month", "date": "not-a-date"},
        )
        self.assertEqual(invalid_date.status_code, 200)
        self.assertEqual(invalid_date.context["view_mode"], "month")

    def test_calendar_falls_back_to_today_for_boundary_years(self):
        self.client.force_login(self.owner)
        today = timezone.localdate()
        for date_value in ("0001-01-01", "9999-12-01"):
            with self.subTest(date=date_value):
                response = self.client.get(
                    reverse("calendar"),
                    {"view": "month", "date": date_value},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["selected_date"],
                    today.replace(day=1),
                )

    def test_search_combines_text_project_member_priority_status_and_dates(self):
        target_date = timezone.localdate() + timezone.timedelta(days=4)
        matching = Task.objects.create(
            project=self.project,
            title="Search target",
            description="Needle phrase in description",
            created_by=self.owner,
            assignee=self.member,
            priority=Task.Priority.HIGH,
            status=Task.Status.IN_PROGRESS,
            due_date=target_date,
        )
        Task.objects.create(
            project=self.project,
            title="Different priority",
            description="Needle phrase in description",
            created_by=self.owner,
            assignee=self.member,
            priority=Task.Priority.LOW,
            status=Task.Status.IN_PROGRESS,
            due_date=target_date,
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("task_search"),
            {
                "q": "Needle phrase",
                "project": self.project.pk,
                "assignee": self.member.pk,
                "priority": Task.Priority.HIGH,
                "status": Task.Status.IN_PROGRESS,
                "due_after": target_date.isoformat(),
                "due_before": target_date.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result_count"], 1)
        self.assertContains(response, matching.title)
        self.assertNotContains(response, "Different priority")
        invalid_range = self.client.get(
            reverse("task_search"),
            {
                "due_after": target_date.isoformat(),
                "due_before": (target_date - timezone.timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(invalid_range.context["result_count"], 0)
        self.assertTrue(invalid_range.context["form"].errors)

    def test_activity_is_recorded_and_private_project_history_is_hidden(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("project_create"),
            {"name": "History project", "description": "First version"},
        )
        history_project = Project.objects.get(name="History project")
        self.assertRedirects(response, history_project.get_absolute_url())
        self.assertTrue(
            Activity.objects.filter(
                project=history_project,
                actor=self.owner,
                action=Activity.Action.PROJECT_CREATED,
            ).exists()
        )
        edit_response = self.client.post(
            reverse("project_edit", args=[history_project.pk]),
            {"name": "Updated history project", "description": "Second version"},
        )
        self.assertRedirects(edit_response, history_project.get_absolute_url())
        history_project.refresh_from_db()
        self.assertEqual(history_project.name, "Updated history project")
        self.assertTrue(
            Activity.objects.filter(
                project=history_project,
                action=Activity.Action.PROJECT_UPDATED,
            ).exists()
        )
        Activity.objects.create(
            project=Project.objects.create(name="Outsider private", owner=self.outsider),
            actor=self.outsider,
            action=Activity.Action.PROJECT_CREATED,
            detail="Private activity sentinel",
        )
        response = self.client.get(reverse("activity_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updated history project")
        self.assertNotContains(response, "Private activity sentinel")

    def test_task_activity_tracks_creation_assignment_edits_and_comments(self):
        self.client.force_login(self.owner)
        due_date = timezone.localdate() + timezone.timedelta(days=9)
        self.client.post(
            reverse("task_create", args=[self.project.pk]),
            {
                "title": "History task",
                "description": "Track all meaningful edits.",
                "assignee": self.member.pk,
                "due_date": due_date.isoformat(),
                "priority": Task.Priority.LOW,
                "status": Task.Status.TODO,
            },
        )
        task = Task.objects.get(project=self.project, title="History task")
        edit_response = self.client.post(
            reverse("task_edit", args=[self.project.pk, task.pk]),
            {
                "title": task.title,
                "description": "Updated task details.",
                "assignee": self.owner.pk,
                "due_date": (due_date + timezone.timedelta(days=1)).isoformat(),
                "priority": Task.Priority.HIGH,
                "status": Task.Status.IN_PROGRESS,
            },
        )
        self.assertRedirects(edit_response, task.get_absolute_url())
        task.refresh_from_db()
        self.assertEqual(task.description, "Updated task details.")
        self.assertEqual(task.assignee, self.owner)
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(task.priority, Task.Priority.HIGH)
        self.assertEqual(task.due_date, due_date + timezone.timedelta(days=1))
        self.client.force_login(self.member)
        self.client.post(
            reverse("task_detail", args=[self.project.pk, task.pk]),
            {"body": "An activity entry should be recorded."},
        )
        actions = set(
            Activity.objects.filter(task=task).values_list("action", flat=True)
        )
        self.assertTrue(
            {
                Activity.Action.TASK_CREATED,
                Activity.Action.TASK_ASSIGNED,
                Activity.Action.TASK_REASSIGNED,
                Activity.Action.TASK_STATUS_CHANGED,
                Activity.Action.TASK_PRIORITY_CHANGED,
                Activity.Action.TASK_DUE_DATE_CHANGED,
                Activity.Action.COMMENT_ADDED,
            }.issubset(actions)
        )

    def test_project_task_and_comment_delete_permissions_and_relationships(self):
        owner_comment = TaskComment.objects.create(
            task=self.task,
            author=self.owner,
            body="Owner comment",
        )
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.post(
                reverse(
                    "comment_delete",
                    args=[self.project.pk, self.task.pk, owner_comment.pk],
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("task_delete", args=[self.project.pk, self.task.pk])
            ).status_code,
            403,
        )
        member_comment = TaskComment.objects.create(
            task=self.task,
            author=self.member,
            body="My comment",
        )
        response = self.client.post(
            reverse(
                "comment_delete",
                args=[self.project.pk, self.task.pk, member_comment.pk],
            )
        )
        self.assertRedirects(response, self.task.get_absolute_url())
        self.assertFalse(TaskComment.objects.filter(pk=member_comment.pk).exists())
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(reverse("task_delete", args=[self.project.pk, self.task.pk])).status_code,
            200,
        )
        response = self.client.post(
            reverse("task_delete", args=[self.project.pk, self.task.pk])
        )
        self.assertRedirects(response, self.project.get_absolute_url())
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertFalse(TaskComment.objects.filter(pk=owner_comment.pk).exists())
        response = self.client.post(reverse("project_delete", args=[self.project.pk]))
        self.assertRedirects(response, reverse("dashboard"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
