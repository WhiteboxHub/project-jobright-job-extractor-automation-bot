"""
Jobright Website Scheduler Integration

Flow
-----
1. Task Scheduler runs this script
2. Script calls website API to check due schedules
3. If workflow is due → run pipeline
4. Update logs and next_run_at
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

# Signal to all child processes that this run was launched by the scheduler.
os.environ["SCHEDULER_LAUNCHED"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_jobright_pipeline import run_pipeline
from core.logger import logger
from core.auth_service import BaseAPIClient

WORKFLOW_KEY = "jobright-engine"
WORKFLOW_ID = 13

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_api_client():
    return BaseAPIClient()

def get_orchestrator_endpoint():
    return "orchestrator"

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _to_utc_mysql(dt: datetime) -> str:
    if dt.tzinfo is None:
        import time as _time
        import calendar
        local_epoch = calendar.timegm(dt.timetuple())
        dt = datetime.utcfromtimestamp(local_epoch)
    else:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def get_next_run_from_cron(cron_expression: str, timezone_str: str = "America/Los_Angeles") -> str:
    now = datetime.now()
    
    try:
        from croniter import croniter
        import pytz
        tz = pytz.timezone(timezone_str)
        now_local = datetime.now(tz)
        cron = croniter(cron_expression, now_local)
        next_run = cron.get_next(datetime)
        utc_str = _to_utc_mysql(next_run)
        logger.info(f"Next run calculated via croniter: {next_run} -> UTC: {utc_str}")
        return utc_str
    except ImportError:
        logger.warning("croniter/pytz not installed. Using built-in fallback.")
    except Exception as e:
        logger.warning(f"croniter failed ({e}). Falling back to built-in parser.")

    try:
        parts = cron_expression.strip().split()
        if len(parts) >= 2:
            hour_field   = parts[1]
            minute_field = parts[0]

            hours  = sorted([int(h.strip()) for h in hour_field.split(",") if h.strip().isdigit()])
            minute = int(minute_field) if minute_field.isdigit() else 0

            today = now.date()
            for h in hours:
                candidate = datetime(today.year, today.month, today.day, h, minute, 0)
                if candidate > now:
                    utc_str = _to_utc_mysql(candidate)
                    logger.info(f"Next run calculated via built-in parser: {candidate} -> UTC: {utc_str}")
                    return utc_str

            tomorrow = today + timedelta(days=1)
            next_run = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hours[0], minute, 0)
            utc_str = _to_utc_mysql(next_run)
            logger.info(f"Next run calculated via built-in parser (tomorrow): {next_run} -> UTC: {utc_str}")
            return utc_str
    except Exception as e:
        logger.warning(f"Built-in cron parser failed ({e}). Using +1 day fallback.")

    fallback = now + timedelta(days=1)
    utc_str = _to_utc_mysql(fallback)
    logger.warning(f"Using fallback next_run_at: {utc_str}")
    return utc_str

def get_schedule_from_website():
    try:
        client = get_api_client()
        response = client.get(f"{get_orchestrator_endpoint()}/schedules/due")
        if response.status_code == 200:
            schedules = response.json()
            for s in schedules:
                if s.get("automation_workflow_id") == WORKFLOW_ID:
                    return s
        return None
    except Exception as e:
        logger.error(f"Failed to fetch schedule: {e}")
        return None

def lock_schedule(schedule_id):
    try:
        client = get_api_client()
        response = client.post(
            f"{get_orchestrator_endpoint()}/schedules/{schedule_id}/lock", json={}
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to lock schedule: {e}")
        return False

def unlock_schedule(schedule_id, cron_expression: str = None, timezone_str: str = "America/Los_Angeles"):
    try:
        client = get_api_client()
        now_utc = _utc_now()

        if cron_expression:
            next_run_str = get_next_run_from_cron(cron_expression, timezone_str)
        else:
            next_run_str = _to_utc_mysql(now_utc + timedelta(days=1))
            logger.warning("No cron expression provided. Used +1 day fallback.")

        payload = {
            "next_run_at": next_run_str,
            "last_run_at": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "is_running":  0,
        }

        logger.info(f"Unlocking schedule {schedule_id} → next_run_at: {next_run_str}")

        response = client.put(
            f"{get_orchestrator_endpoint()}/schedules/{schedule_id}",
            json=payload,
        )
        if response.status_code == 200:
            logger.info(f"Schedule {schedule_id} unlocked successfully.")
            return True
        logger.error(f"unlock_schedule failed: {response.status_code} {response.text[:300]}")
        return False
    except Exception as e:
        logger.error(f"Failed to unlock schedule: {e}")
        return False

def create_log(workflow_id, schedule_id, run_id):
    try:
        client = get_api_client()
        payload = {
            "workflow_id": workflow_id,
            "schedule_id": schedule_id,
            "run_id":      run_id,
            "status":      "running",
            "started_at":  _utc_now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        response = client.post(f"{get_orchestrator_endpoint()}/logs", json=payload)
        if response.status_code in (200, 201):
            data = response.json()
            log_id = data.get("id")
            logger.info(f"Log created → id={log_id}, run_id={run_id}")
            return log_id
        logger.error(f"create_log failed: {response.status_code} {response.text[:300]}")
        return None
    except Exception as e:
        logger.error(f"Failed to create log: {e}")
        return None

def update_log(log_id, status, records_processed=0, error=None, execution_metadata=None):
    try:
        client = get_api_client()
        payload = {
            "status":            status,
            "finished_at":       _utc_now().strftime("%Y-%m-%d %H:%M:%S"),
            "records_processed": records_processed,
        }
        if error:
            payload["error_summary"] = str(error)
        if execution_metadata:
            payload["execution_metadata"] = execution_metadata
        response = client.put(
            f"{get_orchestrator_endpoint()}/logs/{log_id}",
            json=payload,
        )
        if response.status_code == 200:
            logger.info(f"Log {log_id} updated → status={status}, records_processed={records_processed}")
            return True
        logger.error(f"update_log failed: {response.status_code} {response.text[:300]}")
        return False
    except Exception as e:
        logger.error(f"Failed to update log: {e}")
        return False

def debug_schedule():
    try:
        client = BaseAPIClient()
        logger.info("── Fetching ALL schedules ──────────────────────────────")
        r = client.get("orchestrator/schedules")
        if r.status_code == 200:
            schedules = r.json()
            logger.info(f"Total schedules in DB: {len(schedules)}")
            for s in schedules:
                logger.info(
                    f"  id={s.get('id')}  workflow_id={s.get('automation_workflow_id')}  "
                    f"is_running={s.get('is_running')}  "
                    f"next_run_at={s.get('next_run_at')}  "
                    f"cron={s.get('cron_expression')}"
                )
        else:
            logger.error(f"GET /schedules failed: {r.status_code} {r.text}")

        logger.info("── Fetching DUE schedules ──────────────────────────────")
        r2 = client.get("orchestrator/schedules/due")
        if r2.status_code == 200:
            due = r2.json()
            logger.info(f"Due schedules right now: {len(due)}")
            for s in due:
                logger.info(f"  {s}")
        else:
            logger.error(f"GET /schedules/due failed: {r2.status_code} {r2.text}")
    except Exception as e:
        logger.error(f"debug_schedule failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# main()
# ─────────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
        exist_ok=True,
    )

    parser = argparse.ArgumentParser(description="Jobright Scheduler")
    parser.add_argument("--force", action="store_true", help="Run the pipeline even if no schedule is currently due.")
    parser.add_argument("--debug-schedule", action="store_true", help="Print orchestrator schedule details and exit.")
    args = parser.parse_args()

    if args.debug_schedule:
        debug_schedule()
        return

    logger.info("Jobright Scheduler Heartbeat - Polling Orchestrator")

    schedule = None
    api_reachable = True
    try:
        schedule = get_schedule_from_website()
    except Exception as e:
        logger.warning(f"Failed to connect to orchestrator API: {e}")
        api_reachable = False

    if not schedule:
        if not api_reachable:
            logger.warning("Orchestrator API unreachable.")
        else:
            logger.info("No schedule due.")

        if not args.force:
            return

        logger.info("--force provided. Proceeding with pipeline run.")
    else:
        logger.info(
            f"Schedule due → id={schedule.get('id')}, "
            f"cron='{schedule.get('cron_expression')}', "
            f"tz={schedule.get('timezone')}"
        )

    schedule_id  = schedule.get("id") if schedule else None
    workflow_id  = schedule.get("automation_workflow_id") if schedule else WORKFLOW_ID
    cron_expr    = schedule.get("cron_expression", "0 9 * * 1") if schedule else "0 9 * * 1"
    timezone_str = schedule.get("timezone", "America/Los_Angeles") if schedule else "America/Los_Angeles"

    if schedule_id:
        if not lock_schedule(schedule_id):
            logger.warning("Could not lock schedule — proceeding anyway.")

    run_id = str(uuid.uuid4())
    log_id = create_log(workflow_id, schedule_id, run_id) if schedule_id else None

    try:
        logger.info("Running Jobright Pipeline")
        results = run_pipeline([])

        jobs_processed = results.get("jobs_saved", 0) if results else 0
        execution_metadata = None
        if results:
            execution_metadata = {
                "jobs_saved":  results.get("jobs_saved"),
                "jobs_found":  results.get("jobs_found"),
                "timestamp":   results.get("timestamp"),
                "workflow":    WORKFLOW_KEY,
                "forced_run":  not bool(schedule),
            }

        if log_id:
            update_log(
                log_id,
                status="success" if results.get("status") == "success" else "failed",
                records_processed=jobs_processed,
                execution_metadata=execution_metadata,
            )

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if log_id:
            update_log(log_id, "failed", error=e)

    finally:
        if schedule_id:
            unlock_schedule(schedule_id, cron_expression=cron_expr, timezone_str=timezone_str)
        logger.info("Scheduler Finished")

if __name__ == "__main__":
    main()
