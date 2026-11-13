# Production deployment guide

This project is configured for Render, but **has not been deployed**. This guide assumes Windows PowerShell, Git, and Python are installed. Render and GitHub accounts are not included or configured for you.

## What this project needs

- **Render Web Service:** `render.yaml` uses the paid `starter` plan so pre-deploy migrations are supported and the service does not sleep like a free demo instance.
- **Render PostgreSQL:** the blueprint provisions a `basic-256mb` database. Render plan names, availability, limits and pricing can change; confirm current pricing before approving the blueprint.
- **Static files:** WhiteNoise serves collected CSS and JavaScript. No separate static hosting service is needed.
- **Uploaded files:** this application has no file/image upload models or forms, so there are no media files to persist or migrate. If uploads are added later, use object storage or a persistent Render disk and update `MEDIA_ROOT`/storage configuration; the current local filesystem is not persistent across Render deploys.
- **Email:** the application currently sends no email. SMTP is optional and is not required for registration, login, notifications or deployment.
- **Secrets:** the Render blueprint generates `DJANGO_SECRET_KEY`. Never commit a real `.env`, database URL, password, or exported user data.

The free Render web tier is suitable only for a temporary demonstration: it may sleep, has ephemeral local files, and is not paired with the production database configured here. A persistent PostgreSQL database and continuously available service incur charges. Check Render's current free-tier terms and pricing; do not assume a free database is permanent or backed up.

## 1. Back up the existing local database

Do this before changing databases or importing data. Stop `runserver` first so SQLite is not being written while copied.

```powershell
New-Item -ItemType Directory -Force .\backups
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item .\db.sqlite3 ".\backups\project-management-$stamp.sqlite3"
python manage.py showmigrations
```

Keep the backup somewhere private and outside Git. To restore it, stop the application, make another copy of the current `db.sqlite3`, and then copy the chosen backup back to `db.sqlite3`. Do not delete the only copy of either database.

## 2. Create your own GitHub repository

No repository is configured in this workspace. The following commands are instructions only; they have **not** been run.

1. On GitHub, create a new empty repository. Do not initialize it with a README or license because this workspace already has project files.
2. From PowerShell in this project folder, review ignored files and pending files:

   ```powershell
   git init -b main
   git status --short
   git check-ignore .env db.sqlite3
   ```

3. Confirm that `.env`, databases, backups and any data export are not staged. Then create your first commit:

   ```powershell
   git add .
   git status --short
   git commit -m "Prepare project management app for deployment"
   ```

4. Link the empty repository URL shown by GitHub and push only when you are ready:

   ```powershell
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
   git push -u origin main
   ```

Replace the URL with your own. Never add a database dump, `.env` file, or secret to Git.

## 3. Create the Render services

1. Sign in to Render and select **New + → Blueprint**.
2. Connect your GitHub account, choose the repository you just created, and select the branch to deploy.
3. Review `render.yaml`. It creates a Python web service and a PostgreSQL database in the Oregon region. Change the region for both services together if you need another region.
4. Review the current price for the `starter` web plan and `basic-256mb` database, then approve creation. Do not approve paid resources unless you intend to pay for them.
5. Render generates `DJANGO_SECRET_KEY` and injects the PostgreSQL `DATABASE_URL`. The blueprint sets `DJANGO_DEBUG=false` and `SECURE_SSL_REDIRECT=true`. Render's `RENDER_EXTERNAL_HOSTNAME` is used to configure the service host and trusted HTTPS origin.
6. Wait for the build, pre-deploy migration, and health check to finish. Build runs `pip install -r requirements.txt` and `collectstatic`; the pre-deploy command runs `python manage.py migrate`; Gunicorn serves the app.

Do not set `DEBUG=True` on the live service. If you add a custom domain, set `ALLOWED_HOSTS` to its exact hostname and `CSRF_TRUSTED_ORIGINS` to its HTTPS origin in the Render environment. Separate multiple values with commas.

## 4. Run production checks

Render's pre-deploy command applies database migrations automatically. If you need to run an administrative command against the production database from your own machine, use Render's **external** database URL and keep it only in process environment variables. Do not paste it into source code, issue trackers, chat, or shell history.

Example PowerShell setup for a one-off command:

```powershell
$env:DJANGO_DEBUG = "False"
$env:DJANGO_SECRET_KEY = Read-Host "Enter the service DJANGO_SECRET_KEY"
$env:ALLOWED_HOSTS = Read-Host "Enter the service hostname"
$env:DATABASE_URL = Read-Host "Enter the external PostgreSQL URL"
python manage.py check --deploy
Remove-Item Env:DJANGO_SECRET_KEY, Env:ALLOWED_HOSTS, Env:DATABASE_URL, Env:DJANGO_DEBUG
```

The password is not echoed by `Read-Host`; avoid commands that print environment values. Render's internal database URL is for services in Render, not for your laptop.

## 5. Transfer existing SQLite records (optional)

If you want existing local users and project data on the new, empty PostgreSQL database:

1. Back up `db.sqlite3` as described above and run local migrations first.
2. Export the application data to a private file. The command keeps primary keys, which preserves foreign-key references:

   ```powershell
   python manage.py dumpdata --exclude=contenttypes --exclude=auth.permission --exclude=auth.group --exclude=admin.logentry --exclude=sessions.session --indent 2 --output .\data-export-initial.json
   ```

3. Keep the export out of Git and transfer it securely. It contains user and project data. The `.gitignore` excludes `data-export*.json`.
4. Only import into the **empty** PostgreSQL database after the Render migrations have completed and before anyone creates production records. Use a secure one-off command environment with the external PostgreSQL URL and the matching Django settings:

   ```powershell
   $env:DJANGO_DEBUG = "False"
   $env:DJANGO_SECRET_KEY = Read-Host "Enter the service DJANGO_SECRET_KEY"
   $env:ALLOWED_HOSTS = Read-Host "Enter the service hostname"
   $env:DATABASE_URL = Read-Host "Enter the external PostgreSQL URL"
   python manage.py loaddata .\data-export-initial.json
   Remove-Item Env:DJANGO_SECRET_KEY, Env:ALLOWED_HOSTS, Env:DATABASE_URL, Env:DJANGO_DEBUG
   ```

5. Verify the imported users, projects, memberships, tasks, comments, notifications and activity records through the live app. Store the export and database backup privately; delete them only after you have verified a separate backup.

Do not load the same export twice. If the production database already contains data, stop and plan a merge/restore with a database administrator instead of importing over it. SQLite backups cannot be used directly as a PostgreSQL database file; the export/import process is required.

## 6. Verify the live site

After deployment:

1. Open the Render URL and confirm `/health/` returns `{"status":"ok"}`.
2. Confirm that CSS is loaded, registration and login work, and logout returns to the sign-in page.
3. Create a test project, invite a second test user, create/assign a task, change its board status, add a comment, and verify activity/notifications.
4. Check calendar, search filters, and access restrictions using both a project member and a non-member account.
5. If you imported data, check the existing accounts and key records. Do not use a production account's password in a test.

The health endpoint checks database connectivity. It does not expose database details or require authentication.

## Optional SMTP configuration

SMTP is not needed by the current application. If a future feature sends email, choose an email provider, create credentials with that provider, and set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` as Render environment variables. Keep provider credentials out of Git. The app uses Django's console email backend when `EMAIL_HOST` is unset and Django SMTP when it is set.

## Troubleshooting

- **`DJANGO_SECRET_KEY must be set`**: set a private `DJANGO_SECRET_KEY` in the service environment. Render's blueprint generates one.
- **`DisallowedHost`**: set `ALLOWED_HOSTS` to the exact host or confirm Render supplied `RENDER_EXTERNAL_HOSTNAME`.
- **CSRF failure on the Render domain**: set `CSRF_TRUSTED_ORIGINS` to the full `https://your-service.onrender.com` origin (scheme included), with no trailing path.
- **Static files missing**: check the build log for `collectstatic`, confirm WhiteNoise is installed, and redeploy after correcting the failing build.
- **Database connection failure**: confirm the PostgreSQL service is running, `DATABASE_URL` is sourced from that database, and both services use the same region.
- **Migration failure**: inspect the migration log and resolve the schema issue before retrying. Do not use `flush`, drop the database, or reset migrations to recover.
- **Local startup failure after a dependency change**: activate the intended virtual environment and run `python -m pip install -r requirements.txt`.
- **Existing local database not found**: run commands from the project root and check for `db.sqlite3`; never replace it with an empty file to fix a connection error.

## Security and operations notes

- Production requires `DJANGO_DEBUG=False`, a secret key, valid allowed hosts, HTTPS, secure cookies, and PostgreSQL. The settings fail fast if production secret/host configuration is missing.
- Production migrations are additive and do not reset or delete existing records.
- SQLite is retained for local development. It is not recommended as the database for a multi-instance production web service.
- Render deployment, database connection, backups, SMTP, custom domains, and uploaded-file persistence have not been tested or configured from this workspace.
