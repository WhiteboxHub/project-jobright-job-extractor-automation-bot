# Recent Changes

Summary of all repository organization, testing, and concurrent execution improvements for Jobright.

## Overview
- **Reorganization**: Aligned the files and directory structures with the modular layers of Hiring Cafe.
- **Tests**: Created a modular test suite (`tests/` directory) with 5 test suites.
- **Parallel processing**: Implemented high-performance multiprocessing ATS extraction.
- **Stealth**: Standardized scheduler flags and browser evasion configurations.

---

## 1. Directory Structure Organization
Organized folders to cleanly separate configuration, stateless core helpers, scraping strategies, thin script wrappers, test validations, and design documents:
*   `config/`: Search options (`jobright.json`), environments (`settings.py`).
*   `core/`: Stateless helpers (driver lifecycle, API auth client, logging, email report).
*   `strategies/`: Crawling strategies (`jobright_strategy.py`).
*   `scripts/`: Step CLI execution scripts.
*   `tests/`: QA validation and regression test suites.
*   `docs/`: Architecture guides and layout summaries.

---

## 2. Advanced Multi-Process Step 2
*   Created `scripts/jobright_step2_parallel.py` to process the extraction of ATS links concurrently using multiple workers (default 2, recommended max 3).
*   Each worker process operates with isolated user data profile directories to avoid file handle locks.
*   Uses a shared task Queue to fetch jobs dynamically and reports results back to a coordinate saver to update progress JSON atomically.

---

## 3. Automated Test Suite (`tests/` folder)
*   `run_all_tests.py`: Central discoverer and runner.
*   `test_validators.py`: Checks for valid ATS domain mappings and job URL parsers.
*   `test_sanitization.py`: Validates URL fixes, company name resolution, and junk filters.
*   `test_resume_logic.py`: Asserts checkpoint skips for completed or max-attempted jobs.
*   `test_timezone_fix.py`: Ensures PST-to-UTC scheduler offsets work.
