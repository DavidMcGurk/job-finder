# Job Finder

A completely free, scheduled job-search and CV-matching system that uses **Adzuna + local embeddings + deterministic Python matching + free-tier SMTP email**.

The application searches Adzuna for relevant job listings, ranks them against your CV using a hybrid, explainable scoring system (local sentence-transformer embeddings + title/skill/location/recency heuristics), and emails you a concise digest of the best new matches. It runs locally from the command line and automatically via GitHub Actions on a cron schedule.

> **Important:** The ranking score is a **heuristic matching score**, not a genuine probability of getting an interview. It indicates how well a job listing aligns with your configured profile — it does not predict interview success.

---

## How this repository is meant to be used

This repository is a **public template**. It contains no personal data, no CVs, and no secrets — only example configurations and the application code. It is designed to be forked into a **private repository** where you store your real configuration, CV, and GitHub Actions secrets.

```
Public template repo (this repo)          Private fork (your personal repo)
┌─────────────────────────────┐           ┌─────────────────────────────┐
│  src/job_finder/            │           │  src/job_finder/            │
│  tests/                     │           │  tests/                     │
│  config/*.example.yaml      │           │  config/config.yaml    ← real config
│  .github/workflows/         │           │  config/cv.pdf         ← real CV
│  README.md                  │           │  .github/workflows/         │
│  pyproject.toml             │           │  GitHub Actions secrets ← API keys
│                             │           │                             │
│  No personal data.          │           │  Personal data lives here.  │
│  Safe to share.             │           │  Never made public.         │
└─────────────────────────────┘           └─────────────────────────────┘
```

**Why two repos?** Your CV and job preferences are personal data. The public template lets you share the code and accept improvements from others, while the private fork keeps your personal information separate. Secrets (API keys, SMTP credentials) are stored as GitHub Actions secrets in the private fork and never touch the repository.

### Setting up your private fork

1. **Fork or clone this repo to a new private repository** on GitHub.
2. **Add your personal files** (these are gitignored in the template, so un-ignore them in your fork):
   ```bash
   # In your private fork, remove these lines from .gitignore:
   #   config/config.yaml
   #   config/cv.pdf
   #   data/

   cp config/config.example.yaml config/config.yaml
   # Edit config/config.yaml with your real job titles, skills, exclusions, cities
   # Place your CV at config/cv.pdf
   ```
3. **Add GitHub Actions secrets** (see [GitHub Actions](#github-actions) below).
4. **Run it** — either locally or via the scheduled GitHub Actions workflow.

### Pulling upstream changes

When the public template is updated, pull changes into your private fork:

```bash
git remote add upstream https://github.com/DavidMcGurk/job-finder.git
git fetch upstream
git merge upstream/main
```

Your personal config and CV won't be affected by upstream merges.

---

## Architecture overview

```
Adzuna API
  ↓
Normalisation (raw API → internal Job model)
  ↓
Deduplication (by job ID)
  ↓
Hard filtering (exclusion terms, seniority)
  ↓
Local embeddings (sentence-transformers/all-MiniLM-L6-v2)
  ↓
Hybrid scoring (semantic + title + skill + location + recency)
  ↓
Explainable ranking (strengths/concerns per job)
  ↓
SQLite state (seen-job tracking)
  ↓
Email digest (HTML + plain text via SMTP)
```

### Modules

| Module | Responsibility |
|--------|---------------|
| [config.py](src/job_finder/config.py) | YAML configuration loading, typed config dataclasses, env-var secrets |
| [models.py](src/job_finder/models.py) | Internal `Job`, `ScoredJob`, `ComponentScores` data models |
| [adzuna.py](src/job_finder/adzuna.py) | Adzuna API client with retries, pagination, response parsing |
| [cv.py](src/job_finder/cv.py) | PDF text extraction, candidate embedding text construction |
| [embeddings.py](src/job_finder/embeddings.py) | Local sentence-transformer model, batched embedding, cosine similarity |
| [matching.py](src/job_finder/matching.py) | Title similarity, skill matching, location compatibility, exclusion filtering |
| [ranking.py](src/job_finder/ranking.py) | Hybrid weighted scoring, explanation generation |
| [database.py](src/job_finder/database.py) | SQLite seen-job tracking |
| [email.py](src/job_finder/email.py) | HTML/plain-text email generation, SMTP sending |
| [pipeline.py](src/job_finder/pipeline.py) | End-to-end orchestration |
| [__main__.py](src/job_finder/__main__.py) | CLI entry point |

---

## Prerequisites

- Python 3.14+
- [uv](https://astral.sh/uv/)
- [pre-commit](https://pre-commit.com/) (optional, for development)

---

## Local setup

```bash
# Clone the repository
git clone https://github.com/DavidMcGurk/job-finder.git
cd job-finder

# Install dependencies
uv sync

# Install pre-commit hooks (optional)
uv run pre-commit install
```

---

## Configuration

### 1. Create your config file

Copy the example config and customise it:

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` with your search queries, candidate profile, and matching preferences. See [config.example.yaml](config/config.example.yaml) for all options.

### 2. Set environment variables for secrets

All secrets are read from environment variables — never put them in config files:

```bash
# Adzuna API credentials
export ADZUNA_APP_ID="your_app_id"
export ADZUNA_APP_KEY="your_app_key"

# SMTP credentials (for email)
export SMTP_HOST="smtp.example.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_username"
export SMTP_PASSWORD="your_password"
export EMAIL_FROM="from@example.com"
export EMAIL_TO="to@example.com"
```

You can also specify the config file path via `JOB_FINDER_CONFIG`:

```bash
export JOB_FINDER_CONFIG="/path/to/config.yaml"
```

### 3. Obtain Adzuna API credentials

1. Sign up for a free Adzuna developer account at [https://developer.adzuna.com/](https://developer.adzuna.com/)
2. Create a new application to get your `app_id` and `app_key`
3. Set them as environment variables (`ADZUNA_APP_ID` and `ADZUNA_APP_KEY`)

The free tier provides sufficient API calls for personal weekly job searches.

### 4. Configure your candidate profile

Edit the `candidate` section in `config/config.yaml`:

- **name**: Your name
- **location**: Countries, cities, and whether you're open to remote work
- **titles**: Job titles you're interested in (used for title similarity matching)
- **skills.must_have**: Skills that must appear in the job (stronger weight)
- **skills.desirable**: Skills that improve the match score
- **exclusions**: Terms that cause a job to be filtered out (e.g., "sales", "manager")
- **cv_path**: Path to your CV PDF file

### 5. Provide your CV

Place your CV as a PDF file (e.g., `config/cv.pdf`) and set the path in your config:

```yaml
candidate:
  cv_path: config/cv.pdf
```

The CV is processed locally — it is never sent to any external API.

---

## Running locally

### Full run (fetch, match, rank, update state, send email)

```bash
uv run python -m job_finder
```

### Dry run (no database changes, no email)

```bash
uv run python -m job_finder --dry-run
```

### Skip email only

```bash
uv run python -m job_finder --no-email
```

### Limit results

```bash
uv run python -m job_finder --limit 5
```

### Custom config path

```bash
uv run python -m job_finder --config /path/to/config.yaml
```

### Verbose logging

```bash
uv run python -m job_finder --verbose
```

### Help

```bash
uv run python -m job_finder --help
```

---

## SMTP configuration

The email provider is generic SMTP — any free-tier SMTP provider works. Here are two popular options:

### Brevo (formerly Sendinblue)

1. Sign up at [https://www.brevo.com/](https://www.brevo.com/)
2. Go to SMTP & API settings to get your SMTP credentials
3. Set environment variables:

```bash
export SMTP_HOST="smtp-relay.brevo.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_login@example.com"
export SMTP_PASSWORD="your_smtp_key"
export EMAIL_FROM="from@example.com"
export EMAIL_TO="to@example.com"
```

### Gmail (App Password)

1. Enable 2-factor authentication on your Google account
2. Generate an App Password at [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Set environment variables:

```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_email@gmail.com"
export SMTP_PASSWORD="your_app_password"
export EMAIL_FROM="your_email@gmail.com"
export EMAIL_TO="your_email@gmail.com"
```

---

## GitHub Actions

The workflow in [.github/workflows/job-finder.yml](.github/workflows/job-finder.yml) runs the job finder weekly on a cron schedule. **This is designed to run in your private fork**, where your real `config/config.yaml` and `config/cv.pdf` are committed.

### Configure GitHub Actions secrets

Go to your **private** repository → Settings → Secrets and variables → Actions → New repository secret, and add:

| Secret | Description |
|--------|-------------|
| `ADZUNA_APP_ID` | Your Adzuna app ID |
| `ADZUNA_APP_KEY` | Your Adzuna app key |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP server port (e.g., 587) |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_TO` | Recipient email address |

### Scheduled execution

The workflow runs on `workflow_dispatch` (manual trigger) and on a cron schedule (`0 8 * * 1` — weekly on Mondays at 08:00 UTC). Edit the cron expression in the workflow file to change the schedule.

### State persistence

GitHub-hosted runners are ephemeral, so the SQLite database (which tracks seen jobs) is persisted between runs using **GitHub Actions cache**. The database file (`data/job_finder.db`) is saved to and restored from the cache on each run. This approach:

- **Pros**: Simple, transparent, no external services, free for small files
- **Cons**: Cache entries can be evicted after 7 days of non-use; if the cache is missed, previously seen jobs may reappear in the digest

For a private repository, an alternative is to commit the database file back to the repo (the workflow has `contents: write` permission). This is more reliable but exposes the seen-job history in the repo.

---

## Scoring system

The hybrid scoring system combines five normalised components:

| Component | Default weight | Description |
|----------|---------------|-------------|
| Semantic similarity | 50% | Cosine similarity between candidate and job embeddings |
| Title similarity | 20% | Token overlap (Jaccard) between job title and candidate titles |
| Skill matching | 15% | Must-have and desirable skill matching with alias support |
| Location compatibility | 10% | City/country/remote matching |
| Recency | 5% | How recently the job was posted |

Weights are configurable in `config.yaml` under `matching.weights`. The final score is presented as 0–100.

Each ranked job includes algorithmically generated strengths and concerns (no LLM is used).

---

## Privacy considerations

- Your CV is processed **entirely locally** — it is never sent to any external API
- The embedding model runs locally via `sentence-transformers`
- No LLM or paid AI API is used
- Credentials are read from environment variables / GitHub Secrets, never from config files
- The real CV and personal configuration are gitignored in the public template; commit them only to your private fork
- HTML in email output is properly escaped to prevent injection
- Job URLs are validated before rendering as links
- Full CV text is never logged

---

## Known limitations

- Only Adzuna is supported as a job source (no LinkedIn, Indeed, or direct company APIs)
- Only PDF CVs are supported in v1
- Skill matching is keyword-based (with alias support) — it determines whether a skill appears in the job description, not whether the candidate truly possesses it
- Location matching is text-based, not geospatial
- The seen-job database may reset if the GitHub Actions cache is evicted
- The scoring is a heuristic matching score, not a prediction of interview success
- Seniority filtering is conservative and based on job title keywords only

---

## Development

### Run tests

```bash
uv run python -m pytest tests/ -v
```

### Run pre-commit

```bash
uv run pre-commit run --all-files
```

### Run type checks

```bash
uv run mypy src/
```

### Run linter

```bash
uv run flake8 --max-line-length=120 src/ tests/
```

### Format code

```bash
uv run black --line-length=120 --target-version py314 src/ tests/
```
