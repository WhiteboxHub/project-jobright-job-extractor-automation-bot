# CLAUDE.md

Repository operating manual for AI-assisted development of the Jobright Job Extractor.

---

## Repository Purpose

Job scraping pipeline: Jobright.ai → ATS enrichment → API ingestion.

**Architecture**: 4-stage checkpoint pipeline with bot-detection evasion.
**Core constraint**: Evade Cloudflare and sign-up/login walls on Jobright.

---

## Operating Commands

### Running the Pipeline

```bash
# Run the complete pipeline (Steps 1 to 4)
python run_jobright_pipeline.py

# Run step 1 only (Scrape job list from Jobright)
python scripts/jobright_step1_extract_urls.py

# Run step 2 only (Serial ATS enrichment)
python scripts/jobright_step2_extract_ats_urls.py --limit 20

# Run step 2 in parallel (2 workers, concurrent browser instances)
python scripts/jobright_step2_parallel.py --workers 2

# Run step 3 only (Group by ATS platforms)
python scripts/jobright_step3_combine_by_ats.py

# Run step 4 only (API Ingestion - dry run)
python scripts/jobright_step4_ingest_to_api.py --dry-run
```

### Running Tests

```bash
# Run all tests
python tests/run_all_tests.py

# Run individual test files
python tests/test_validators.py
python tests/test_sanitization.py
python tests/test_resume_logic.py
python tests/test_timezone_fix.py
```

---

## Engineering Guidelines

### 1. Philosophy & Code Style
*   **Simple & Explicit**: Prioritize explicit loops and clear conditions over nested, magic code or list comprehensions.
*   **Checkpoint-Safe**: Progress is saved atomically after *every single job* process to ensure that interruptions do not lose progress.
*   **Evasion First**: Maintain random human behavior simulations, including mouse jitters, scroll steps, and organic delays between page loads.

### 2. Error Handling & Stability
*   **Fail Fast**: Raise explicit `ValueError` at pipeline boundaries when inputs are missing.
*   **Catch and Handle**: Selenium operations must catch custom exceptions (`TimeoutException`, `NoSuchElementException`) and clean up the active browser handles in a `finally` block.
*   **No Silent Failures**: Unhandled exceptions should be logged with stack traces, and tasks must unlock scheduler entries.

### 3. File Operations
*   Always use UTF-8 encoding when reading/writing files:
    ```python
    with open(path, "r", encoding="utf-8") as f:
    ```
*   Implement atomic file writes using `.tmp` files and `os.replace` to prevent corrupted outputs upon unexpected kills.
