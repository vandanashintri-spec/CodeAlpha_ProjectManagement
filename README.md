# Taskflow — Project Management System

A beginner-friendly project and task management app built with Django and SQLite. Team members can organize projects on a three-column task board, assign work, discuss tasks, and receive in-app notifications.

## Features

- Account registration, login, and POST-only logout with Django's secure password handling.
- Project dashboard with task totals and completed-task progress.
- Project creation and owner-controlled editing, deletion, and member invitations.
- Project task board with To Do, In Progress, and Completed columns.
- Tasks with descriptions, due dates, priorities, assignees, and status updates.
- Project-member-only task and comment access, with task-edit/delete and comment-delete permissions.
- In-app assignment and comment notifications with unread counts and read actions.
- Responsive interface, CSRF-protected forms, validation, and confirmation messages.
- A database-backed dashboard with project/task totals, completion progress, overdue work, recent updates, and deadlines for the next seven days.
- Drag-and-drop task cards with AJAX status updates and a keyboard/accessibility-friendly status selector fallback.
- Month and week calendar views with project filtering, date navigation, status indicators, and overdue highlighting.
- Search across task titles and descriptions, with combinable project, assignee, priority, status, date-range, and overdue filters.
- A project-scoped activity history for project edits, task creation/assignment/reassignment/status/priority/due-date changes, and comments.

## Requirements

- Python 3.10 or later
- pip

## Run locally (Windows PowerShell)

From the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and create an account or sign in. The SQLite database is created as `db.sqlite3` in the project directory. Newly registered users can create projects and invite other registered users by username. Use the sidebar to open task search, the calendar, activity history, and notifications. Task search filters can be combined; the calendar supports month/week views and per-project filtering. On a project board, drag cards to change status or use each card's status selector.

The additive activity-history migration creates a new table; it does not replace existing models or delete project data. Apply it to an existing local database with `python manage.py migrate`.

The checked-in `.env.example` lists supported variables but is not loaded automatically by Django. With no deployment environment variables set, local defaults keep SQLite and debug mode for the `runserver` workflow. If you configure `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`, or `RENDER_EXTERNAL_HOSTNAME` locally, set `DJANGO_DEBUG=True` explicitly; when any of these deployment settings are present, an unset `DJANGO_DEBUG` defaults to False. Production should set `DJANGO_DEBUG=False` explicitly.

For production, set a private `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, use a PostgreSQL `DATABASE_URL`, and serve the app over HTTPS. See [DEPLOYMENT.md](./DEPLOYMENT.md) for the exact Render setup.

## Deployment

Render production settings, PostgreSQL, Gunicorn, WhiteNoise, backups, optional data transfer, and exact deployment steps are documented in [DEPLOYMENT.md](./DEPLOYMENT.md). A Render blueprint is provided in `render.yaml`; reviewing and creating its paid services requires your own Render account and approval. No deployment or GitHub push has been performed.

This app currently has no file upload feature and sends no email. Render media storage and SMTP are therefore optional, not deployment requirements.

## Run checks and tests

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Project layout

- `config/` — Django settings and URL configuration.
- `projects/` — project, membership, task, comment, notification models; forms, views, and tests.
- `templates/` — shared layout, authentication, dashboard, board, task, and notification screens.
- `static/projects/` — responsive CSS and small navigation script.
