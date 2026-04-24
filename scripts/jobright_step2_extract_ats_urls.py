#!/usr/bin/env python3
"""
Jobright Step 2: Extract ATS URLs
"""

import json
import sys
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.logger import logger
from core.browser import browser_service
from strategies.custom.jobright_strategy import JobrightStrategy, _load_jobright_config

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=str(ROOT / "jobright_jobs.json"))
    parser.add_argument("--output", default=str(ROOT / "jobright_jobs.json"))
    parser.add_argument("--limit",  type=int, default=None)
    args = parser.parse_args()

    logger.info("Starting Jobright Step 2: Extract ATS URLs")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            jobs = data.get("jobs", [])
    except Exception as e:
        logger.error(f"Failed to read input file: {e}")
        return

    if not jobs:
        logger.warning("No jobs to process in Step 2.")
        return

    # Load config to get credentials
    config = _load_jobright_config()
    creds  = config.get("credentials", {})
    email    = creds.get("email", "")
    password = creds.get("password", "")

    driver = browser_service.start_browser()

    try:
        # ── CRITICAL: Login before any ATS extraction ──────────────────────
        if email and password:
            strategy = JobrightStrategy(driver=driver, config_override=config)
            logged_in = strategy.login()
            if not logged_in:
                logger.error("Login failed — ATS extraction will see 'Sign Up' modals. Aborting.")
                return
            logger.info("Login successful. Starting ATS extraction.")
            time.sleep(2)
        else:
            logger.warning("No credentials in config — proceeding without login (expect null ATS URLs).")
            strategy = JobrightStrategy(driver=driver, config_override=config)

        enriched_jobs = strategy.enrich_jobs_with_ats_links(
            jobs,
            limit=args.limit,
            output_file=args.output,
        )

        enriched = sum(1 for j in enriched_jobs if j.get("ats_url"))
        logger.info(f"Step 2 complete. {enriched}/{len(enriched_jobs)} jobs have ATS URLs.")

    except Exception as e:
        logger.error(f"Step 2 failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        browser_service.stop_browser()

if __name__ == "__main__":
    main()
