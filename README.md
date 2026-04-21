# Jobright Engine 🤖

Automated job scraper for [Jobright.ai](https://jobright.ai).  
Scrapes job listings and extracts real ATS apply URLs — all in **one browser session**.

---

## How It Works

```
Login once
  │
  ├── Step 1: Scroll job search pages → extract job cards → save to JSON
  │
  └── Step 2: Open each job page → click Apply → capture ATS URL → update JSON
```

Both steps share **one Chrome browser and one session** — no re-login needed between steps.

---

## Project Structure

```
jobright-engine/
│
├── run_pipeline.py              ← 🚀 Main entry point (Step 1 + Step 2)
│
├── strategies/
│   ├── __init__.py
│   └── custom/
│       ├── __init__.py
│       └── jobright_strategy.py ← Core scraping logic (Step 1)
│
├── config/
│   └── jobright.json            ← Credentials + search keywords
│
├── jobright_jobs.json           ← Output: scraped jobs with ATS URLs
├── requirements.txt             ← Python dependencies
├── setup_venv.ps1               ← One-time venv setup script
├── .gitignore
└── README.md
```

---

## Setup

### 1. Create virtual environment
```powershell
.\setup_venv.ps1
```

### 2. Activate virtual environment
```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Configure credentials & keywords

Edit `config/jobright.json`:
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
  "random_pause_max_sec": 7.0,
  "step2_pause_min_sec": 2.0,
  "step2_pause_max_sec": 5.0
}
```

---

## Usage

### Full pipeline — scrape + extract ATS URLs
```powershell
python run_pipeline.py
```

### Full pipeline with visible browser (recommended for first run)
```powershell
python run_pipeline.py --visible
```

### Step 1 only — scrape job listings
```powershell
python run_pipeline.py --skip-step2
```

### Step 2 only — enrich existing `jobright_jobs.json`
```powershell
python run_pipeline.py --skip-step1
```

### Re-enrich all jobs (including already-enriched)
```powershell
python run_pipeline.py --skip-step1 --reprocess-all
```

### Test mode — collect 10 jobs, enrich first 5
```powershell
python run_pipeline.py --job-limit 10 --ats-limit 5 --visible
```

### Single keyword + location override
```powershell
python run_pipeline.py --keyword "Data Scientist" --location "New York"
```

---

## CLI Options

| Flag | Default | Description |
|---|---|---|
| `--visible` | off | Show browser window |
| `--headless` | off | Force headless mode |
| `--skip-step1` | off | Skip scraping, use existing JSON |
| `--skip-step2` | off | Skip ATS enrichment |
| `--job-limit N` | None | Max jobs to collect in Step 1 |
| `--ats-limit N` | None | Max jobs to enrich in Step 2 |
| `--reprocess-all` | off | Re-enrich jobs that already have `ats_url` |
| `--keyword TEXT` | from config | Override search keyword |
| `--location TEXT` | from config | Override location |
| `--output FILE` | `jobright_jobs.json` | Custom output file path |

---

## Output Format

`jobright_jobs.json` is updated after **every single job** (safe to interrupt with Ctrl+C):

```json
{
  "source": "jobright.ai",
  "step": 2,
  "updated": "2026-04-22T04:00:00",
  "count": 36,
  "jobs": [
    {
      "job_id": "69e6a2f8e0cd471b2f126e44",
      "title": "React Python Developer",
      "company": "Anagh Technologies Inc",
      "location": "United States",
      "city": null,
      "state": null,
      "job_type": "Contract",
      "work_mode": "Remote",
      "seniority": "Senior Level",
      "salary": null,
      "posted_ago": "1 hour ago",
      "jobright_url": "https://jobright.ai/jobs/info/69e6a2f8...",
      "ats_url": "https://boards.greenhouse.io/company/jobs/123456",
      "ats_platform": "greenhouse",
      "source_keywords": ["Python Developer"],
      "scraped_at": "2026-04-22T05:19:47"
    }
  ]
}
```

---

## ATS Platforms Detected

| Platform | Pattern matched |
|---|---|
| `greenhouse` | `boards.greenhouse.io`, `job-boards.greenhouse.io` |
| `workday` | `myworkdayjobs.com`, `workday.com` |
| `lever` | `jobs.lever.co` |
| `icims` | `*.icims.com` |
| `successfactors` | `*.successfactors.com`, `*.sapsf.com` |
| `smartrecruiters` | `*.smartrecruiters.com` |
| `ashby` | `*.ashbyhq.com` |
| `bamboohr` | `*.bamboohr.com` |
| `oraclecloud` | `*.oraclecloud.com` |
| `linkedin` | `linkedin.com/jobs` |
| `taleo` | `*.taleo.net` |
| `jobvite` | `*.jobvite.com` |
| `rippling` | `*.rippling.com` |
| `eightfold` | `*.eightfold.ai` |
| `paycom` | `*.paycom.com` |
| `breezy` | `*.breezy.hr` |
| `teamtailor` | `*.teamtailor.com` |
| `recruitee` | `*.recruitee.com` |
| `phenom` | `*.phenompeople.com` |

---

## ATS URL Extraction — 4 Layers

| Layer | Method | Speed |
|---|---|---|
| **1** | `Original Job Post` link on the job detail page | ⚡ Fastest |
| **2** | Direct `href` on the Apply `<a>` button | ⚡ Fast |
| **3** | Click Apply → dismiss modals → capture new tab URL | 🐢 Slower |
| **4** | Page source regex scan | 🐢 Fallback |

---

## Session Management

- Login happens **once** at startup
- Before every job in Step 2, the session is **verified** automatically
- If session expires mid-run, the engine **re-logs in** and retries the job
- All progress is **checkpointed** — safe to interrupt and resume

---

## Git Setup

```powershell
git init
git config user.name "Your Name"
git config user.email "your@email.com"
git add .
git commit -m "Initial commit"
```

---

## Dependencies

```
selenium>=4.10.0
webdriver-manager>=4.0.0
```

Install via:
```powershell
pip install -r requirements.txt
```
