# SkillBridge

SkillBridge is a Django application for candidate profiles, job applications, recruiter screening, interview scheduling and review, subscriptions, feedback, and staff administration.

## Requirements

- Python 3.11 or newer
- `pip`
- A Stripe **test-mode** secret key only if you want to test Pro checkout

SQLite is used locally, so a separate database server is not required.

## 1. Open the project

```bash
cd /Users/jamie/Desktop/draft/skillbridge
```

If the project is stored elsewhere, replace that path with your project folder. Run all following commands from the folder containing `manage.py`.

## 2. Create and activate a virtual environment

macOS or Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv venv
venv\Scripts\Activate.ps1
```

The terminal should display `(venv)` after activation.

## 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If Django reports `ModuleNotFoundError: No module named 'django'`, confirm that `(venv)` appears in the terminal and run the installation command again.

## 4. Create the environment file

```bash
cp .env.example .env
```

The application works without Stripe for normal local development. Never commit `.env` or share its secret values.

For Stripe test checkout, edit `.env` and set:

```dotenv
STRIPE_SECRET_KEY=sk_test_your_test_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_test_webhook_secret
STRIPE_PRICE_ID=
PRO_PLAN_AMOUNT_CENTS=900
PRO_PLAN_CURRENCY=sgd
```

Important:

- Use an `sk_test_` secret key, never an `sk_live_` key during development.
- The publishable `pk_test_` key is not required by this project because checkout is created on the Django server and completed on Stripe Checkout.
- `STRIPE_PRICE_ID` is optional. When blank, SkillBridge uses the configured amount and currency.
- `STRIPE_WEBHOOK_SECRET` is required for testing webhook events.

## 5. Apply database migrations

```bash
python manage.py migrate
```

This creates or updates the local `db.sqlite3` database.

When model code is intentionally changed during development, create and apply a migration with:

```bash
python manage.py makemigrations
python manage.py migrate
```

Do not run `makemigrations` merely to start an unchanged copy of the project; the required migration files are already included.

## 6. Create an administrator

```bash
python manage.py createsuperuser
```

Enter the requested username, email, and password. Staff administration is available at:

```text
http://127.0.0.1:8000/administration/login/
```

The standard Django admin is not the main SkillBridge administration interface.

## 7. Run the development server

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

Stop the server with `Control+C`.

## 8. Run checks and tests

Run Django's configuration check:

```bash
python manage.py check
```

Check that models do not have missing migrations:

```bash
python manage.py makemigrations --check --dry-run
```

Run the complete test suite:

```bash
python manage.py test
```

Run one test module, for example:

```bash
python manage.py test employers.test_interview_workflow
```

## Stripe test workflow

1. Add the Stripe `sk_test_` secret key to `.env`.
2. Restart `python manage.py runserver` after changing `.env`.
3. Sign in as a candidate or recruiter.
4. Open **My plans** and choose **Subscribe to Pro**.
5. Complete the hosted Stripe test checkout.
6. Return to SkillBridge and confirm that the plan shows **Pro active**.

For webhook testing, forward Stripe test events to:

```text
http://127.0.0.1:8000/payments/stripe/webhook/
```

Put the webhook signing secret generated for that endpoint into `STRIPE_WEBHOOK_SECRET`, then restart the server.

## Email during local development

The default email backend prints password-reset and notification emails in the server terminal. No SMTP account is required.

To send real email, configure the `EMAIL_*` values documented in `.env.example` and change:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

## Uploaded files and local data

- Local database: `db.sqlite3`
- Uploaded resumes and profile images: `media/`
- Static source files: `static/`
- Collected production static files: `staticfiles/`

Do not commit `.env`, `db.sqlite3`, uploaded personal files, API keys, or payment secrets.

## Common commands

```bash
# Activate the environment on macOS/Linux
source venv/bin/activate

# Start the app
python manage.py runserver

# Apply migrations
python manage.py migrate

# Create an administrator
python manage.py createsuperuser

# Run all tests
python manage.py test

# Leave the virtual environment
deactivate
```

## Troubleshooting

### Django is not installed

```text
ModuleNotFoundError: No module named 'django'
```

Activate the virtual environment and install the requirements:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
```

### `manage.py` cannot be found

You are in the wrong folder. Change into the project directory first:

```bash
cd /Users/jamie/Desktop/draft/skillbridge
```

### A migration error appears

```bash
python manage.py showmigrations
python manage.py migrate
```

### Stripe checkout is unavailable

Confirm that:

- `.env` is inside the same folder as `manage.py`.
- `STRIPE_SECRET_KEY` begins with `sk_test_`.
- The server was restarted after editing `.env`.
- The key has no quotation marks or extra spaces.

### Port 8000 is already in use

Run Django on another port:

```bash
python manage.py runserver 8001
```

Then open `http://127.0.0.1:8000/`.
