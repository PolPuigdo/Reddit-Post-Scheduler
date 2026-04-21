<img width="1983" height="589" alt="reddit_scheduler_banner" src="https://github.com/user-attachments/assets/6816d11b-7ee0-4d23-b5c3-35a1a2e15425" />

>Automate Reddit posting with a Flask web app + a background worker that publishes using Playwright.

---

## 🚀 What this project does

- Create scheduled Reddit posts from a web UI.
- Store scheduled jobs in SQLite.
- Auto-publish posts when their scheduled time arrives.
- Publish immediately or cancel pending posts.
- Save logs and debug artifacts when something fails.

---

## 🧰 Stack

- `Python`
- `Flask`
- `SQLAlchemy`
- `Playwright` (browser automation)
- `SQLite`

---

## ✅ Prerequisites

- Python `3.10+` recommended
- `pip`
- Access to a Reddit account
- Chromium installed via Playwright

---

## ⚡ Quick start

### 1) Clone the repository

```bash
git clone <REPO_URL>
cd Reddit-Auto-Post-Raspberry
```

### 2) Create a virtual environment and install dependencies

On Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux / Raspberry Pi:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3) Install Chromium for Playwright

```bash
python -m playwright install chromium
```

> If you're on Raspberry Pi/Linux and system libraries are missing, try:
> `python -m playwright install --with-deps chromium`

### 4) Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Available variables:

| Variable | Default value | Description |
|---|---|---|
| `APP_HOST` | `0.0.0.0` | Flask server host |
| `APP_PORT` | `5000` | Web app port |
| `DEBUG` | `True` | Flask debug mode |
| `DATABASE_URL` | `sqlite:///data/app.db` | SQLite database URL |
| `MAX_CONTENT_LENGTH` | `10485760` | Upload size limit (bytes) |
| `LOG_FILE_PATH` | `logs/worker.log` | Worker log file |
| `PLAYWRIGHT_HEADLESS` | `False` | Run browser without UI |
| `PLAYWRIGHT_AUTH_FILE` | `playwright/.auth/reddit.json` | Saved Reddit session |
| `WORKER_POLL_SECONDS` | `30` | Worker polling interval (seconds) |
| `DEBUG_ARTIFACTS_DIR` | `logs/debug` | Screenshots/HTML on Playwright errors |

---

## 🔐 First Reddit login (required)

Before publishing, save an authenticated Reddit session:

```bash
python -m app.scripts.reddit_login
```

A browser window will open:

1. Log in to Reddit manually.
2. Return to the terminal and press `ENTER`.
3. Session state will be saved to `playwright/.auth/reddit.json`.

---

## ▶️ Run the app

Open **2 terminals** (with the virtual environment activated in both):

### Terminal A: Web app

```bash
python -m app.main
```

### Terminal B: Worker

```bash
python -m app.worker
```

Then open:

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 🧭 Recommended usage flow

1. Create a post from `Create new post`.
2. Fill in title, subreddit, date/time, and optionally image/text.
3. Save the post.
4. The worker publishes it when status is `pending` and time is due.
5. From the detail page, you can `Publish now` or `Cancel` while pending.

---

## 🖼️ Supported image formats

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

---

## 🩺 Quick troubleshooting

| Problem | Common cause | Fix |
|---|---|---|
| `Playwright authentication file not found` | Login script not run yet | Run `python -m app.scripts.reddit_login` |
| `Post` button is disabled | Reddit UI validation or captcha/protection page | Check `logs/debug/` and try `PLAYWRIGHT_HEADLESS=False` |
| Nothing gets published | Worker not running or no due posts | Start `python -m app.worker` and verify status/scheduled UTC |
| Image upload error | Unsupported format or invalid path | Use `jpg/jpeg/png/webp` and upload again |

---

## 📁 Project structure

```text
app/
  main.py                      # Flask web app
  worker.py                    # Polling-based auto publisher
  web/                         # Routes and templates
  services/                    # Publishing, logging, validation, storage logic
  repositories/                # Data access layer
  scripts/                     # Manual scripts (login/testing)
data/                          # SQLite DB and uploads (runtime-generated)
logs/                          # Logs and debug artifacts
playwright/.auth/              # Saved Reddit session
```

---

## 🛠️ Useful scripts

```bash
# Save Reddit session
python -m app.scripts.reddit_login

# Publish directly via script
python -m app.scripts.reddit_post <subreddit> "<title>" "<body>" "<image_path>"
```

---

## 📌 Notes

- The datetime from the form is converted internally to UTC.
- The repo ignores `data/`, `logs/`, and `.env` to avoid committing sensitive/local files.
- For 24/7 Raspberry deployment, running web + worker as services is recommended.
