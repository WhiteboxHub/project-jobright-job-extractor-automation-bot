#!/usr/bin/env python3
"""
Jobright Step 1: Extract Job URLs
==================================
Scrapes fresh job listings from jobright.ai based on keywords.
Saves results to jobright_jobs.json.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.logger import logger
from core.browser import browser_service
from strategies.custom.jobright_strategy import JobrightStrategy

def main():
    logger.info("🚀 Starting Jobright Step 1: Extract Job URLs")
    
    output_file = ROOT / "jobright_jobs.json"
    
    # Initialize browser
    driver = browser_service.start_browser()
    
    try:
        strategy = JobrightStrategy(driver)
        
        # Login if credentials available
        strategy.login()
        
        # Phase 1: Scroll and collect job listings
        logger.info("Phase 1: Collecting unique jobs across all keywords...")
        jobs = strategy.find_jobs()
        
        if not jobs:
            logger.warning("No jobs found during Step 1.")
            return
            
        # Add metadata and save
        payload = {
            "source": "jobright.ai",
            "step": 1,
            "updated": datetime.now().isoformat(),
            "count": len(jobs),
            "jobs": jobs
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Step 1 complete. Saved {len(jobs)} jobs to {output_file.name}")
        
    except Exception as e:
        logger.error(f"❌ Step 1 failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        browser_service.stop_browser()

if __name__ == "__main__":
    main()