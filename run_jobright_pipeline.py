#!/usr/bin/env python3
"""
Jobright — Full Pipeline Coordinator
=====================================
Orchestrates the 4-step pipeline for Jobright.ai:

  Step 1 → Scrape fresh job listings (jobright_jobs.json)
  Step 2 → Extract ATS URLs (checkpoint/resume safe)
  Step 3 → Group by ATS platform (jobright_by_ats.json)
  Step 4 → Bulk ingestion to backend API
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
JOBS_FILE   = ROOT / "jobright_jobs.json"
BY_ATS_FILE = ROOT / "jobright_by_ats.json"

STEP1 = SCRIPTS_DIR / "jobright_step1_extract_urls.py"
STEP2 = SCRIPTS_DIR / "jobright_step2_extract_ats_urls.py"
STEP3 = SCRIPTS_DIR / "jobright_step3_combine_by_ats.py"
STEP4 = SCRIPTS_DIR / "jobright_step4_ingest_to_api.py"

# ── Helpers ───────────────────────────────────────────────────────────────────
def _banner(msg: str, char: str = "=") -> None:
    print(f"\n{char * 80}")
    print(f"  {msg}")
    print(f"{char * 80}")

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _run_step(label: str, script: Path, extra_args: list = []) -> bool:
    """Run a step script as subprocess. Returns True on success."""
    if not script.exists():
        print(f"❌ Script not found: {script}")
        return False
        
    cmd = [sys.executable, str(script)] + extra_args
    print(f"\n▶  {label}")
    print(f"   Command : {' '.join(str(a) for a in cmd)}")
    print(f"   Started : {_now()}")
    print()
    
    start = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - start
    
    m, s = int(elapsed // 60), int(elapsed % 60)
    duration = f"{m}m {s}s" if m else f"{s}s"
    
    if result.returncode == 0:
        print(f"\n   ✅ {label} finished in {duration}")
        return True
    else:
        print(f"\n   ❌ {label} FAILED (exit {result.returncode}) after {duration}")
        return False

def _load_jobs(path: Path) -> tuple[dict, list]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {}, data
        jobs = data.get("jobs", [])
        meta = {k: v for k, v in data.items() if k != "jobs"}
        return meta, jobs
    except Exception:
        return {}, []

# ── Main ──────────────────────────────────────────────────────────────────────
def run_pipeline(args_list=None) -> dict:
    parser = argparse.ArgumentParser(description="Jobright Pipeline Coordinator")
    parser.add_argument("--skip-step1", action="store_true", help="Skip fresh scrape, use existing JSON")
    parser.add_argument("--skip-step2", action="store_true", help="Skip ATS extraction")
    parser.add_argument("--skip-step3", action="store_true", help="Skip platform grouping")
    parser.add_argument("--skip-step4", action="store_true", help="Skip API ingestion")
    parser.add_argument("--limit", type=int, help="Limit jobs processed in Step 2")
    parser.add_argument("--no-email", action="store_true", help="Skip sending email report")
    parser.add_argument("--force", action="store_true", help="Force run (used by scheduler)")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--reprocess-all", action="store_true", help="Force re-extraction of all jobs in Step 2")
    args = parser.parse_args(args_list)

    if args.visible:
        os.environ["HEADLESS"] = "false"
    elif args.headless:
        os.environ["HEADLESS"] = "true"

    total_start = time.time()
    _banner("JOBRIGHT PIPELINE START", "=")
    
    results = {}

    # ─────────────────────────────────────────────────────────
    # STEP 1: SCRAPE
    # ─────────────────────────────────────────────────────────
    if not args.skip_step1:
        if not _run_step("Step 1: Extract Job URLs", STEP1):
            return {"status": "error", "error": "Step 1 failed", "jobs_saved": 0, "jobs_found": 0, "timestamp": _now()}
        results["step1"] = "ok"
    else:
        print("⏭️  Skipping Step 1 (using existing jobs file)")
        results["step1"] = "skipped"

    # ─────────────────────────────────────────────────────────
    # STEP 2: ENRICH (ATS URLS)
    # ─────────────────────────────────────────────────────────
    if not args.skip_step2:
        step2_args = []
        if args.limit:
            step2_args += ["--limit", str(args.limit)]
        if args.visible:
            step2_args.append("--visible")
        elif args.headless:
            step2_args.append("--headless")
        if args.reprocess_all:
            step2_args.append("--reprocess-all")
        
        if not _run_step("Step 2: Extract ATS URLs", STEP2, step2_args):
            results["step2"] = "failed"
        else:
            results["step2"] = "ok"
    else:
        print("⏭️  Skipping Step 2")
        results["step2"] = "skipped"

    # ─────────────────────────────────────────────────────────
    # STEP 3: COMBINE (GROUP BY ATS)
    # ─────────────────────────────────────────────────────────
    if not args.skip_step3:
        if not _run_step("Step 3: Combine by ATS", STEP3):
            results["step3"] = "failed"
        else:
            results["step3"] = "ok"
    else:
        print("⏭️  Skipping Step 3")
        results["step3"] = "skipped"

    # ─────────────────────────────────────────────────────────
    # STEP 4: INGEST (API)
    # ─────────────────────────────────────────────────────────
    if not args.skip_step4:
        if not _run_step("Step 4: Ingest to API", STEP4):
            results["step4"] = "failed"
        else:
            results["step4"] = "ok"
    else:
        print("⏭️  Skipping Step 4")
        results["step4"] = "skipped"

    # ─────────────────────────────────────────────────────────
    # EMAIL REPORTING
    # ─────────────────────────────────────────────────────────
    if not args.no_email:
        try:
            print("\n📧 Sending email report...")
            from core.email_reporter import email_reporter
            email_reporter.send_report(str(BY_ATS_FILE))
        except Exception as e:
            print(f"⚠️ Email report failed: {e}")

    total_elapsed = time.time() - total_start
    m, s = int(total_elapsed // 60), int(total_elapsed % 60)
    _banner(f"JOBRIGHT PIPELINE COMPLETE (Total time: {m}m {s}s)", "=")
    
    # Calculate stats for the orchestrator
    jobs_count, jobs_with_ats = 0, 0
    if JOBS_FILE.exists():
        _, all_jobs = _load_jobs(JOBS_FILE)
        jobs_count = len(all_jobs)
        jobs_with_ats = sum(1 for j in all_jobs if j.get("ats_url"))
        
    status = "success"
    if results.get("step1") == "failed" or results.get("step3") == "failed":
        status = "failed"
        
    return {
        "status": status,
        "jobs_saved": jobs_with_ats,
        "jobs_found": jobs_count,
        "timestamp": _now()
    }

if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    res = run_pipeline()
    sys.exit(1 if res.get("status") in ["error", "failed"] else 0)
