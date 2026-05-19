# File Structure

Organized repository layout for the Jobright Job Extractor.

```
project-jobright-job-extractor-automation-bot/
│
├── config/                          # Configuration files
│   ├── jobright.json               # Search params (keywords, location, credentials)
│   └── settings.py                 # Pydantic settings (env vars)
│
├── core/                            # Infrastructure (browser, auth, logging)
│   ├── auth_service.py             # API authentication
│   ├── browser.py                  # Browser lifecycle (start/stop/cleanup)
│   ├── captcha_handler.py          # CAPTCHA detection/handling
│   ├── email_reporter.py           # Email job reports
│   ├── human_behavior.py           # Mouse jitter, random pauses
│   ├── logger.py                   # Centralized logging
│   ├── proxy_manager.py            # Proxy rotation
│   └── safe_actions.py             # Safe click/type with retries
│
├── strategies/                      # Scraping strategies
│   └── custom/
│       ├── __init__.py
│       └── jobright_strategy.py    # Main strategy
│
├── scripts/                         # Pipeline steps
│   ├── jobright_step1_extract_urls.py           # Step 1: Scrape job title search results
│   ├── jobright_step2_extract_ats_urls.py       # Step 2: Extract ATS URLs (serial)
│   ├── jobright_step2_parallel.py               # Step 2: Parallel (2-3 workers)
│   ├── jobright_step3_combine_by_ats.py         # Step 3: Group by ATS platform
│   └── jobright_step4_ingest_to_api.py          # Step 4: Clean and send to API
│
├── tests/                           # Test suite
│   ├── __init__.py
│   ├── README.md                   # Test documentation
│   ├── run_all_tests.py            # Test runner
│   ├── test_resume_logic.py        # Checkpoint/resume tests
│   ├── test_sanitization.py        # URL/company name cleaning tests
│   ├── test_timezone_fix.py        # Scheduler timezone tests
│   └── test_validators.py          # URL validation tests
│
├── docs/                            # Documentation
│   ├── FILE_STRUCTURE.md           # This file
│   └── ORGANIZATION_SUMMARY.md     # Reorganization migration history
│
├── run_jobright_pipeline.py         # Main entry point (orchestrator)
├── jobright_scheduler.py            # Scheduled runs (cron integration)
│
├── CLAUDE.md                        # Operating manual (LLM instructions)
├── README.md                        # User-facing documentation
├── requirements.txt                 # Python dependencies
├── .env                             # Secrets (not committed)
└── .gitignore
```

---

## Directory Purposes

### `config/`
**Contains**: Pydantic settings (`settings.py`), and the user parameters file (`jobright.json`), which stores search keywords, preferred execution mode settings, and login credentials.

---

### `core/`
**Contains**: Stateless infrastructure utilities that handle browser launch flags, Undetected Chromedriver coordination, proxies, safety delays, logging patterns, and target orchestrator backend requests.

---

### `strategies/`
**Contains**: The active Selenium scraping and DOM parsing engine (`jobright_strategy.py`). It coordinates infinite page scrolls, authenticates into account pages, and executes multi-layer fallbacks to discover final direct ATS application links.

---

### `scripts/`
**Contains**: thin CLI wrappers that execute one of the 4 key steps of the pipeline, using the strategies and core layers to read, enrich, segment, or post listings.

---

### `tests/`
**Contains**: The complete test suite discoverable by `run_all_tests.py` to assert the stability of parsing, resume steps, time offsets, and validators.
