<div align="center">

# Jobright Engine

**High-performance, parallelized job discovery and ATS link extraction for [Jobright.ai](https://jobright.ai)**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![Selenium](https://img.shields.io/badge/Selenium-4.10%2B-green?logo=selenium)](https://selenium.dev)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>

---

## Overview

Jobright Engine is a decoupled, enterprise-grade browser automation pipeline that crawls, extracts, normalizes, and ingests job listings from Jobright.ai into backend databases. 

1. **Step 1 (Discovery)**: Scrapes fresh job listings from Jobright.ai based on configurable keywords and locations.
2. **Step 2 (ATS Extraction)**: Parallelized multi-threaded Chrome workers navigate to each job page to extract company Applicant Tracking System (ATS) URLs.
3. **Step 3 (Grouping)**: Aggregates and groups job listings dynamically by ATS platform (e.g. Greenhouse, Workday, Lever).
4. **Step 4 (Ingestion)**: Cleans, sanitizes, and streams the jobs in batches to the website backend API.

---

## High-Performance Parallel Architecture

```
                                ┌─────────────────────────────┐
                                │  run_jobright_pipeline.py   │
                                └──────────────┬──────────────┘
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       ▼                                               ▼
         ┌───────────────────────────┐                   ┌───────────────────────────┐
         │          Step 1           │                   │          Step 2           │
         │  (jobright_step1_...)     │                   │  (jobright_step2_para...) │
         │  Scrapes fresh listings    │                   │  Parallel Multi-Workers   │
         └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                       │                                               │
                       │ (saves jobright_jobs.json)                    │ (isolated worker profiles)
                       └───────────────────────┬───────────────────────┘
                                               ▼
                                 ┌───────────────────────────┐
                                 │          Step 3           │
                                 │  (jobright_step3_...)     │
                                 │  Group by ATS platform    │
                                 └─────────────┬─────────────┘
                                               │
                                               ▼
                                 ┌───────────────────────────┐
                                 │          Step 4           │
                                 │  (jobright_step4_...)     │
                                 │  Clean & bulk Ingest      │
                                 └───────────────────────────┘
```

*   **Isolated User Profiles**: Each parallel worker runs in its own isolated Chrome profile path (e.g. `chrome_profile_worker0`) to avoid write locks and cookie collision.
*   **Dynamic Work Queue**: Distributes pending jobs dynamically via a shared multiprocessing queue to maximize CPU core utilization.
*   **Fail-safe Checkpoints**: Atomically dumps progress to disk after *every* single job enrichment, making the pipeline completely resume-safe.
*   **Automatic Stale Clearing**: Pipeline automatically strips legacy `ats_url` and `ats_platform` keys from `jobright_jobs.json` when fresh scraping starts, or on-demand using `--reprocess-all`.

---

## Project Structure

```
project-jobright-job-extractor-automation-bot/
│
├── config/
│   └── jobright.json            # Search keywords, credentials, and location settings
│
├── core/
│   ├── auth_service.py          # Stateless backend API client and JWT authentication
│   ├── browser.py               # Chrome Selenium driver configurations & initialization
│   ├── email_reporter.py        # Automated email summaries with markdown tables
│   └── logger.py                # Console/File log wrappers with formatting
│
├── docs/
│   ├── FILE_STRUCTURE.md        # Deep dive into directory locations
│   └── ORGANIZATION_SUMMARY.md  # Structural parity verification mapping
│
├── scripts/
│   ├── jobright_step1_extract_urls.py   # Step 1: Scrapes job search listings
│   ├── jobright_step2_parallel.py       # Step 2: Multi-process ATS URL extraction
│   ├── jobright_step3_combine_by_ats.py # Step 3: Groups results by ATS platforms
│   └── jobright_step4_ingest_to_api.py  # Step 4: Normalizes and batch streams to API
│
├── run_jobright_pipeline.py     # Pipeline Coordinator — Orchestrates Steps 1 to 4
├── jobright_scheduler.py        # Website integration & task scheduler
├── CLAUDE.md                    # Standard Operating Guidelines (LLM manual)
├── CHANGES.md                   # Bot structural migration logs
├── .env                         # Local secrets & API endpoints (Ignored by Git)
├── jobright_jobs.json           # Crawled and enriched job listings
├── jobright_by_ats.json         # Structured and grouped job metadata
├── setup_venv.ps1               # One-click Windows virtual environment initializer
└── README.md
```

---

## Prerequisites

*   Python 3.10+
*   Google Chrome browser installed locally
*   A valid [Jobright.ai](https://jobright.ai) account

---

## Setup

### Step 1: Create Virtual Environment
Run the one-click virtual environment setup script (Windows PowerShell):
```powershell
.\setup_venv.ps1
```

### Step 2: Activate Environment
```powershell
.\venv\Scripts\Activate.ps1
```

### Step 3: Configure Credentials & Options
Create a `.env` file in the project root:
```env
JOBRIGHT_EMAIL=your_email@gmail.com
JOBRIGHT_PASSWORD=your_password
AUTH_USERNAME=your_backend_api_username
AUTH_PASSWORD=your_backend_api_password
API_BASE_URL=https://api.yourbackend.com/
```

Adjust keywords or platform delays in `config/jobright.json`:
```json
{
  "credentials": {
    "email": "your_email@gmail.com",
    "password": "your_password"
  },
  "search_keywords": [
    "Data Scientist",
    "Machine Learning Engineer",
    "Software Engineer"
  ],
  "location": "United States",
  "random_pause_min_sec": 3.0,
  "random_pause_max_sec": 7.0
}
```

---

## Usage

### Root Coordinator (Run Full Pipeline)
Executes Steps 1 to 4 in order. Handles automated browser session cleanups and profile locks cleanly:
```powershell
python run_jobright_pipeline.py
```

*   **Specify parallel worker count**:
    ```powershell
    python run_jobright_pipeline.py --workers 3
    ```
*   **Run headless (without showing browser windows)**:
    ```powershell
    python run_jobright_pipeline.py --headless
    ```
*   **Reprocess all existing jobs (re-run ATS extraction)**:
    ```powershell
    python run_jobright_pipeline.py --reprocess-all
    ```
*   **Resume Step 2 (Skip Step 1 scrape)**:
    ```powershell
    python run_jobright_pipeline.py --skip-step1
    ```
*   **Limit to first N jobs for a quick pipeline verification run**:
    ```powershell
    python run_jobright_pipeline.py --limit 10
    ```

---

## Step-by-Step CLI Execution (Individual Control)

*   **Step 1: Extract Job Search URLs**
    ```powershell
    python scripts/jobright_step1_extract_urls.py
    ```
*   **Step 2: High-Performance Multi-Process ATS Extractor**
    ```powershell
    # Run with 2 workers in headless mode
    python scripts/jobright_step2_parallel.py --workers 2 --headless
    
    # Process only the first 20 jobs
    python scripts/jobright_step2_parallel.py --limit 20
    ```
*   **Step 3: Combine and Group jobs by ATS platform**
    ```powershell
    python scripts/jobright_step3_combine_by_ats.py
    ```
*   **Step 4: Clean and Batch Ingest to Database API**
    ```powershell
    python scripts/jobright_step4_ingest_to_api.py
    ```

---

## Pipeline Coordinator Argument Reference

| Flag | Default | Description |
|---|---|---|
| `--workers N` | `2` | Number of parallel worker threads in Step 2 |
| `--headless` | `False` | Launch worker browsers in headless mode |
| `--skip-step1` | `False` | Skip discovery, reuse existing `jobright_jobs.json` |
| `--skip-step2` | `False` | Skip ATS extraction |
| `--skip-step3` | `False` | Skip platform grouping |
| `--skip-step4` | `False` | Skip API bulk ingestion |
| `--limit N` | `None` | Limit total jobs enriched in Step 2 |
| `--reprocess-all`| `False` | Strip and re-extract all previously resolved ATS URLs |
| `--no-email` | `False` | Skip sending markdown email report |

---

## Supported ATS Platforms

The parser automatically detects, extracts, and resolves redirects for all major Applicant Tracking Systems:

*   **Greenhouse** (`boards.greenhouse.io`)
*   **Workday** (`*.myworkdayjobs.com`)
*   **Lever** (`jobs.lever.co`)
*   **Workable** (`apply.workable.com`)
*   **SmartRecruiters** (`*.smartrecruiters.com`)
*   **Jobvite** (`*.jobvite.com`)
*   **Ashby** (`*.ashbyhq.com`)
*   **BambooHR** (`*.bamboohr.com`)
*   **Taleo** (`*.taleo.net`)
*   **Rippling** (`*.rippling.com`)
*   **iCIMS** (`*.icims.com`)
*   **Paycom** (`*.paycom.com`)

---

## License

MIT © 2026 Sairam
