#!/usr/bin/env python3
"""
Jobright Step 3: Combine by ATS Platform
=========================================
Groups enriched jobs from Step 2 by their detected ATS platform.
Saves results to jobright_by_ats.json.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.logger import logger

def categorize_jobs_by_ats(jobs):
    """Group jobs by their detected ATS platform."""
    by_platform = {}
    for j in jobs:
        platform = (j.get("ats_platform") or "unknown").strip().lower() or "unknown"
        if platform not in by_platform:
            by_platform[platform] = []
        
        # Build a clean entry for this platform list
        entry = {
            "job_id": j.get("job_id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "jobright_url": j.get("jobright_url") or j.get("url"),
            "ats_url": j.get("ats_url"),
            "ats_platform": platform,
            "city": j.get("city"),
            "state": j.get("state"),
            "job_type": j.get("job_type"),
            "work_mode": j.get("work_mode"),
            "seniority": j.get("seniority"),
            "salary": j.get("salary"),
            "posted_ago": j.get("posted_ago"),
            "scraped_at": j.get("scraped_at")
        }
        by_platform[platform].append(entry)
    return by_platform

def main():
    parser = argparse.ArgumentParser(description="Combine jobs by ATS platform.")
    parser.add_argument("--input", default=str(ROOT / "jobright_jobs.json"), help="Path to input jobs JSON")
    parser.add_argument("--output", default=str(ROOT / "jobright_by_ats.json"), help="Path to output by_ats JSON")
    args = parser.parse_args()

    logger.info("🚀 Starting Jobright Step 3: Combine by ATS Platform")
    
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
        logger.warning("No jobs found to categorize in Step 3.")
        return

    # Categorize
    by_ats = categorize_jobs_by_ats(jobs)
    
    # Prepare payload
    payload = {
        "source": "jobright.ai",
        "updated": datetime.now().isoformat(),
        "platforms": sorted(by_ats.keys()),
        "by_ats": by_ats
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    logger.info(f"✅ Step 3 complete. Categorized {len(jobs)} jobs into {len(by_ats)} platforms.")
    for p in sorted(by_ats.keys()):
        logger.info(f"   - {p}: {len(by_ats[p])} jobs")

if __name__ == "__main__":
    main()
