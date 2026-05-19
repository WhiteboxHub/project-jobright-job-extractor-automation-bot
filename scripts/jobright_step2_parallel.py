#!/usr/bin/env python3
"""
Step 2 Parallel — Extract ATS URLs using multiprocessing (2-3 workers).

PERFORMANCE
───────────
  Serial:   5-15 min for 100 jobs (1 browser, sequential)
  Parallel: 3-8 min for 100 jobs (2 browsers, concurrent)

STEALTH-FOCUSED
───────────────
  • Only 2-3 workers (conservative, mimics multiple human users)
  • Each worker has separate Chrome profile
  • Maintains same random delays as serial version
  • Resume-safe: shared job queue, atomic file writes

CHECKPOINT / RESUME
───────────────────
  Progress saved after EVERY job (by coordinator process).
  Re-run with same command to resume from where stopped.
"""

import argparse
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Allow running from project root
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.logger import logger

# ── Shared state ──────────────────────────────────────────────────────────────

_shutdown_event = None  # multiprocessing.Event


def _handle_signal(sig, frame):
    """Signal handler for graceful shutdown."""
    global _shutdown_event
    if _shutdown_event:
        logger.warning("Signal received — shutting down workers")
        _shutdown_event.set()


# ── Worker process ────────────────────────────────────────────────────────────

def _worker_process(
    worker_id: int,
    job_queue: mp.Queue,
    result_queue: mp.Queue,
    shutdown_event: mp.Event,
    headless: bool,
):
    """
    Worker process: extract ATS URLs from jobs.
    Runs in separate process with own Chrome instance and isolated profile.
    """
    # Import inside worker to avoid pickle issues
    from core.browser import browser_service
    from strategies.custom.jobright_strategy import JobrightStrategy, _load_jobright_config
    from config.settings import settings

    if headless:
        settings.HEADLESS = True

    # Create worker-specific Chrome profile
    original_profile = settings.chrome_profile_path
    worker_profile = f"{original_profile}_worker{worker_id}"
    settings.CHROME_USER_DATA_DIR = worker_profile

    # Load config to check credentials
    config = _load_jobright_config()
    creds  = config.get("credentials", {})
    email    = creds.get("email", "")
    password = creds.get("password", "")

    driver = None
    processed = 0

    try:
        logger.info(f"[Worker {worker_id}] Starting browser (profile: {worker_profile})")
        driver = browser_service.start_browser()
        strategy = JobrightStrategy(driver=driver, config_override=config)

        # Log in before taking jobs from queue
        if email and password:
            logged_in = strategy.login()
            if not logged_in:
                logger.error(f"[Worker {worker_id}] Login failed — cannot extract ATS links without account context.")
                return
            logger.info(f"[Worker {worker_id}] Login successful. Ready to process jobs.")
            time.sleep(2)
        else:
            logger.warning(f"[Worker {worker_id}] No credentials found — processing without login (expects sign-up modals).")

        while not shutdown_event.is_set():
            try:
                # Get job from queue (timeout to check shutdown periodically)
                job = job_queue.get(timeout=1.0)

                if job is None:  # Sentinel: no more jobs
                    break

                job_id = job.get("job_id") or job.get("external_id")
                logger.info(f"[Worker {worker_id}] Processing job {job_id}")

                # Extract ATS URL using existing strategy (6-layer)
                ats_data = strategy._get_ats_link_from_job_page(job_id)

                # Return result
                result = {
                    "job_id": job_id,
                    "ats_url": ats_data["ats_url"] if ats_data else None,
                    "ats_platform": ats_data["ats_platform"] if ats_data else None,
                }
                result_queue.put(result)
                processed += 1

                # Human-like delay between jobs (same as serial strategy pacing)
                strategy._random_human_pause(
                    "between ATS jobs",
                    strategy._step2_pause_lo,
                    strategy._step2_pause_hi,
                )

            except mp.queues.Empty:
                continue  # Timeout, check shutdown and retry
            except Exception as e:
                logger.error(f"[Worker {worker_id}] Error processing job: {e}")
                result_queue.put({"job_id": job.get("job_id"), "ats_url": None, "ats_platform": None})

        logger.info(f"[Worker {worker_id}] Processed {processed} jobs")

    except Exception as e:
        logger.critical(f"[Worker {worker_id}] Fatal error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if driver:
            try:
                browser_service.stop_browser()
            except Exception:
                pass

        # Clean up worker profile
        import shutil
        try:
            if os.path.exists(worker_profile):
                shutil.rmtree(worker_profile)
        except Exception:
            pass


# ── Coordinator ───────────────────────────────────────────────────────────────

def _load_jobs(path: str) -> tuple[dict, list[dict]]:
    """Load JSON and return (metadata, jobs)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {}, data
    jobs = data.get("jobs", [])
    meta = {k: v for k, v in data.items() if k != "jobs"}
    return meta, jobs


def _save_jobs(path: str, meta: dict, jobs: list[dict]) -> None:
    """Atomic save using temp file."""
    tmp = path + ".tmp"
    payload = {
        **meta,
        "step": 2,
        "updated": datetime.now().isoformat(),
        "count": len(jobs),
        "jobs": jobs,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 2 Parallel: Extract ATS URLs with multiprocessing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", default="jobright_jobs.json",
        help="Input JSON from Step 1",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file (default: overwrite input)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process only first N jobs",
    )
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Number of parallel workers (default: 2, max 3 recommended)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browsers in headless mode",
    )
    args = parser.parse_args()

    if args.workers > 3:
        logger.warning(f"⚠️  {args.workers} workers may trigger bot detection. Recommended max: 3")

    input_path = args.input
    output_path = args.output or args.input

    # ── Load jobs ─────────────────────────────────────────────────────────────
    if not os.path.isfile(input_path):
        print(f"❌ Input file not found: {input_path}", file=sys.stderr)
        return 1

    meta, jobs = _load_jobs(input_path)

    if not jobs:
        print("❌ No jobs in input file", file=sys.stderr)
        return 1

    # Ensure job_id + url exists
    for j in jobs:
        jid = j.get("job_id") or j.get("external_id")
        url = j.get("jobright_url") or j.get("url")
        if not jid and url and "jobs/info/" in str(url):
            jid = str(url).rstrip("/").split("jobs/info/")[-1].split("?")[0]
        if not url and jid:
            url = f"https://jobright.ai/jobs/info/{jid}"
        if jid:
            j["job_id"] = jid
        if url:
            j["jobright_url"] = url
            j.setdefault("url", url)

    # ── Filter pending jobs ───────────────────────────────────────────────────
    limit = args.limit if args.limit else len(jobs)
    to_process = jobs[:limit]

    pending = [j for j in to_process if not j.get("ats_url")]
    already_done = len(to_process) - len(pending)

    print()
    print("=" * 70)
    print(f"📋 Total jobs       : {len(jobs)}")
    print(f"⏭️  Already done     : {already_done}")
    print(f"🔄 Pending          : {len(pending)}")
    print(f"👷 Workers          : {args.workers}")
    print(f"💾 Output           : {output_path}")
    print("=" * 70)
    print()

    if not pending:
        print("✅ All jobs already processed!")
        return 0

    # ── Setup multiprocessing ─────────────────────────────────────────────────
    global _shutdown_event
    _shutdown_event = mp.Event()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    job_queue = mp.Queue()
    result_queue = mp.Queue()

    # Fill job queue
    for job in pending:
        job_queue.put(job)

    # Add sentinels (one per worker)
    for _ in range(args.workers):
        job_queue.put(None)

    # Start workers
    workers = []
    for i in range(args.workers):
        p = mp.Process(
            target=_worker_process,
            args=(i, job_queue, result_queue, _shutdown_event, args.headless),
        )
        p.start()
        workers.append(p)

    # ── Collect results ───────────────────────────────────────────────────────
    print(f"⚙️  Workers started. Processing {len(pending)} jobs...\n")

    completed = 0
    start_time = time.time()

    try:
        while completed < len(pending):
            try:
                result = result_queue.get(timeout=1.0)

                # Update job in-place
                job_id = result["job_id"]
                for j in jobs:
                    if j.get("job_id") == job_id:
                        j["ats_url"] = result["ats_url"]
                        j["ats_platform"] = result["ats_platform"]
                        break

                completed += 1

                # Save checkpoint after every job
                _save_jobs(output_path, meta, jobs)

                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(pending) - completed) / rate if rate > 0 else 0

                logger.info(
                    f"Progress: {completed}/{len(pending)} "
                    f"({completed*100//len(pending)}%) "
                    f"| Rate: {rate:.1f} jobs/min "
                    f"| ETA: {remaining/60:.1f} min"
                )

            except mp.queues.Empty:
                # Check if workers are still alive
                if not any(w.is_alive() for w in workers):
                    break

    except KeyboardInterrupt:
        logger.warning("⚠️  Interrupted by user")
        _shutdown_event.set()

    finally:
        # Wait for workers to finish
        for w in workers:
            w.join(timeout=5)
            if w.is_alive():
                w.terminate()

        # Final save
        _save_jobs(output_path, meta, jobs)

        elapsed = time.time() - start_time
        print()
        print("=" * 70)
        print(f"✅ Completed: {completed}/{len(pending)} jobs")
        print(f"⏱️  Time: {elapsed/60:.1f} minutes")
        print(f"📈 Rate: {completed/(elapsed/60):.1f} jobs/min")
        print(f"💾 Saved: {output_path}")
        print("=" * 70)

    return 0


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    mp.freeze_support()
    sys.exit(main())
