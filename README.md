<div align="center">

# Jobright Engine

**Automated job discovery and ATS link extraction for [Jobright.ai](https://jobright.ai)**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Selenium](https://img.shields.io/badge/Selenium-4.10%2B-green?logo=selenium)](https://selenium.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

## Overview

Jobright Engine is a browser automation pipeline that:

1. **Scrapes** job listings from Jobright.ai using configurable keywords and locations
2. **Extracts** the real company ATS (Applicant Tracking System) apply URL from each job listing
3. **Persists** all results to a structured JSON file, checkpointing after every job

The entire pipeline runs in a **single Chrome session** — login happens once and is maintained throughout both steps, eliminating session-loss issues.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   run_pipeline.py                    │
│                                                      │
│  1. Build Chrome Driver                              │
│  2. Login (once)                                     │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  STEP 1 — Job Discovery                      │   │
│  │  jobright_strategy.py                        │   │
│  │  • Search by keywords + location             │   │
│  │  • Scroll & extract job cards                │   │
│  │  • Merge with existing jobright_jobs.json    │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  STEP 2 — ATS URL Enrichment                 │   │
│  │  run_pipeline.py (inline)                    │   │
│  │  • Navigate to each job page                 │   │
│  │  • Layer 1: "Original Job Post" link         │   │
│  │  • Layer 2: Apply button href                │   │
│  │  • Layer 3: Click → dismiss modals → new tab │   │
│  │  • Layer 4: Page source regex fallback       │   │
│  │  • Auto re-login on session expiry           │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  3. Save jobright_jobs.json  (per-job checkpoint)    │
└─────────────────────────────────────────────────────┘
```

---

## Project Structure

```
jobright-engine/
│
├── run_pipeline.py              # Entry point — runs full pipeline
│
├── strategies/
│   ├── __init__.py
│   └── custom/
│       ├── __init__.py
│       └── jobright_strategy.py # Step 1: job discovery & scraping
│
├── config/
│   └── jobright.json            # Search config (keywords, location, timing)
│
├── .env                         # Credentials (never commit this)
├── .gitignore
├── jobright_jobs.json           # Output — enriched job listings
├── requirements.txt             # Python dependencies
├── setup_venv.ps1               # One-time virtual environment setup
└── README.md
```

---

## Prerequisites

- Python 3.10+
- Google Chrome browser
- A [Jobright.ai](https://jobright.ai) account

---

## Setup

### Step 1 — Create the virtual environment

```powershell
.\setup_venv.ps1
```

### Step 2 — Activate it

```powershell
.\venv\Scripts\Activate.ps1
```

### Step 3 — Configure credentials

Edit `.env`:
```env
JOBRIGHT_EMAIL=your@email.com
JOBRIGHT_PASSWORD=yourpassword
```

Edit `config/jobright.json` to set your search preferences:
```json
{
  "credentials": {
    "email": "your@email.com",
    "password": "yourpassword"
  },
  "search_keywords": [
    "Python Developer",
    "AI Engineer",
    "Machine Learning Engineer"
  ],
  "location": "United States",
  "random_pause_min_sec": 3.0,
  "random_pause_max_sec": 7.0
}
```

---

## Usage

### Full pipeline — scrape jobs then extract ATS URLs

```powershell
python run_pipeline.py --visible
```

### Step 1 only — scrape job listings, no enrichment

```powershell
python run_pipeline.py --skip-step2 --visible
```

### Step 2 only — enrich an existing `jobright_jobs.json`

```powershell
python run_pipeline.py --skip-step1 --visible
```

### Re-enrich all jobs (override previously found ATS URLs)

```powershell
python run_pipeline.py --skip-step1 --reprocess-all --visible
```

### Quick test — scrape 10 jobs, enrich first 5

```powershell
python run_pipeline.py --job-limit 10 --ats-limit 5 --visible
```

### Run fully headless (no browser window)

```powershell
python run_pipeline.py --headless
```

---

## CLI Reference

| Flag | Default | Description |
|---|---|---|
| `--visible` | `False` | Show the Chrome browser window |
| `--headless` | `False` | Run Chrome without a window |
| `--skip-step1` | `False` | Skip scraping, use existing JSON |
| `--skip-step2` | `False` | Skip ATS enrichment |
| `--job-limit N` | `None` | Collect at most N jobs in Step 1 |
| `--ats-limit N` | `None` | Enrich at most N jobs in Step 2 |
| `--reprocess-all` | `False` | Re-enrich even already-enriched jobs |
| `--keyword TEXT` | from config | Override search keyword |
| `--location TEXT` | from config | Override location |
| `--output FILE` | `jobright_jobs.json` | Custom output file path |

> **Note:** `--visible` takes priority over `--headless` if both are specified.

---

## Output

`jobright_jobs.json` is written after **every single job** processed, making it safe to interrupt and resume at any time.

```json
{
  "source": "jobright.ai",
  "step": 2,
  "updated": "2026-04-22T04:00:00",
  "count": 36,
  "jobs": [
    {
      "job_id": "69e6a2f8e0cd471b2f126e44",
      "title": "Senior Python Developer",
      "company": "Acme Corp",
      "location": "New York, NY",
      "city": "New York",
      "state": "NY",
      "job_type": "Full-time",
      "work_mode": "Remote",
      "seniority": "Senior Level",
      "salary": "$130K/yr - $160K/yr",
      "posted_ago": "2 hours ago",
      "jobright_url": "https://jobright.ai/jobs/info/69e6a2f8...",
      "ats_url": "https://boards.greenhouse.io/acmecorp/jobs/7890123",
      "ats_platform": "greenhouse",
      "source_keywords": ["Python Developer"],
      "scraped_at": "2026-04-22T05:19:47"
    }
  ]
}
```

---

## Supported ATS Platforms

| Platform | Domain Pattern |
|---|---|
| Greenhouse | `boards.greenhouse.io` |
| Workday | `*.myworkdayjobs.com` |
| Lever | `jobs.lever.co` |
| iCIMS | `*.icims.com` |
| SAP SuccessFactors | `*.successfactors.com` |
| SmartRecruiters | `*.smartrecruiters.com` |
| Ashby | `*.ashbyhq.com` |
| BambooHR | `*.bamboohr.com` |
| Oracle Cloud | `*.oraclecloud.com` |
| Eightfold | `*.eightfold.ai` |
| LinkedIn | `linkedin.com/jobs` |
| Taleo | `*.taleo.net` |
| Jobvite | `*.jobvite.com` |
| Workable | `apply.workable.com` |
| Rippling | `*.rippling.com` |
| Paycom | `*.paycom.com` |
| Breezy HR | `*.breezy.hr` |
| Phenom People | `*.phenompeople.com` |
| Teamtailor | `*.teamtailor.com` |
| Recruitee | `*.recruitee.com` |

---

## Session Reliability

| Feature | Behavior |
|---|---|
| **Single login** | Logs in once at startup — session shared across all jobs |
| **Session monitoring** | Checks login status before every job in Step 2 |
| **Auto re-login** | Automatically re-authenticates if session expires mid-run |
| **Modal handling** | Dismisses "Customize Resume", "Autofill", and Orion tour modals |
| **Checkpoint saving** | Saves after every job — safe to Ctrl+C and resume |

---

## Git

```powershell
# Initial setup
git config user.name "Your Name"
git config user.email "your@email.com"

# First commit
git add .
git commit -m "Initial commit"

# Push to remote
git remote add origin https://github.com/yourusername/jobright-engine.git
git push -u origin main
```

> ⚠️ The `.env` and `jobright_jobs.json` files are in `.gitignore` and will **not** be committed.

---

## Dependencies

```
selenium>=4.10.0
webdriver-manager>=4.0.0
```

```powershell
pip install -r requirements.txt
```

---

## License

MIT © 2026 Sairam
