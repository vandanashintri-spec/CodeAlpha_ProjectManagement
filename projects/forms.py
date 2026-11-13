from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Project, Task, TaskComment

User = get_user_model()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("name", "description")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class AddMemberForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), label="Team member")

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        existing_ids = project.members.values_list("pk", flat=True)
        self.fields["user"].queryset = User.objects.exclude(
            pk__in=list(existing_ids) + [project.owner_id]
        ).order_by("username")


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("title", "description", "assignee", "due_date", "priority", "status")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = project.members.order_by("username")
        self.fields["assignee"].required = False


class TaskStatusForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("status",)


class CommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ("body",)
        labels = {"body": "Add a comment"}
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Share an update…"})}


class TaskSearchForm(forms.Form):
    q = forms.CharField(required=False, label="Search tasks")
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        empty_label="All projects",
    )
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Any team member",
    )
    priority = forms.ChoiceField(
        required=False,
        choices=[("", "Any priority"), *Task.Priority.choices],
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Any status"), *Task.Status.choices],
    )
    due_after = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Due on or after",
    )
    due_before = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Due on or before",
    )
    overdue = forms.BooleanField(required=False, label="Overdue only")

    def __init__(self, *args, projects, members, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = projects
        self.fields["assignee"].queryset = members

    def clean(self):
        cleaned_data = super().clean()
        due_after = cleaned_data.get("due_after")
        due_before = cleaned_data.get("due_before")
        if due_after and due_before and due_after > due_before:
            raise forms.ValidationError("The start date must be on or before the end date.")
        return cleaned_data


class CalendarFilterForm(forms.Form):
    view = forms.ChoiceField(
        choices=(("month", "Month"), ("week", "Week")),
        required=False,
        initial="month",
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        empty_label="All projects",
    )

    def __init__(self, *args, projects, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = projects
