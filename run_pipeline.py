"""
run_pipeline.py — Full Jobright pipeline in ONE process, ONE browser, ONE session
==================================================================================
Step 1: Login → scrape job listings (scroll + extract)
Step 2: Same browser → visit each job → click Apply → capture ATS URL

Usage:
  python run_pipeline.py                        # full pipeline, visible browser
  python run_pipeline.py --headless             # headless
  python run_pipeline.py --skip-step1           # only ATS enrichment
  python run_pipeline.py --skip-step2           # only scrape
  python run_pipeline.py --job-limit 10         # test: collect 10 jobs
  python run_pipeline.py --ats-limit 5          # test: enrich first 5 jobs
  python run_pipeline.py --reprocess-all        # re-enrich all ats_urls
"""

import argparse
import json
import os
import sys
import time
import random
import re
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# ── Project imports ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
from strategies.custom.jobright_strategy import JobrightStrategy, _load_jobright_config

# ── ATS helpers (inlined from step2_enrich_ats.py) ────────────────────────────

ATS_PATTERNS = [
    (r"lever\.co", "lever"),
    (r"greenhouse\.io", "greenhouse"),
    (r"successfactors\.com|sapsf\.com", "successfactors"),
    (r"myworkdayjobs\.com|workday\.com", "workday"),
    (r"smartrecruiters\.com", "smartrecruiters"),
    (r"icims\.com", "icims"),
    (r"jobvite\.com", "jobvite"),
    (r"taleo\.net", "taleo"),
    (r"workable\.com", "workable"),
    (r"bamboohr\.com", "bamboohr"),
    (r"ashbyhq\.com", "ashby"),
    (r"oraclecloud\.com", "oraclecloud"),
    (r"rippling\.com", "rippling"),
    (r"eightfold\.ai", "eightfold"),
    (r"linkedin\.com/jobs", "linkedin"),
    (r"careers\.google\.com", "google"),
    (r"adp\.com", "adp"),
    (r"paycom\.com", "paycom"),
    (r"breezy\.hr", "breezy"),
    (r"phenompeople\.com", "phenom"),
    (r"teamtailor\.com", "teamtailor"),
    (r"recruitee\.com", "recruitee"),
    (r"dover\.com", "dover"),
]

SKIP_DOMAINS = ("jobright.ai", "linkedin.com/share", "linkedin.com/feed",
                "twitter.com", "x.com", "facebook.com", "reddit.com")

ATS_RE = re.compile(
    r'https?://(?:[a-z0-9-]+\.lever\.co|boards\.greenhouse\.io'
    r'|[a-z0-9-]+\.greenhouse\.io|[a-z0-9-]+\.myworkdayjobs\.com'
    r'|[a-z0-9-]+\.workday\.com|[a-z0-9-]+\.successfactors\.com'
    r'|[a-z0-9-]+\.sapsf\.com|[a-z0-9-]+\.ashbyhq\.com'
    r'|[a-z0-9-]+\.smartrecruiters\.com|[a-z0-9-]+\.icims\.com'
    r'|[a-z0-9-]+\.jobvite\.com|[a-z0-9-]+\.taleo\.net'
    r'|apply\.workable\.com|[a-z0-9-]+\.bamboohr\.com'
    r'|[a-z0-9-]+\.oraclecloud\.com|[a-z0-9-]+\.eightfold\.ai'
    r')[/\w\-\.\?\=\&\%\#\@\+]*',
    re.IGNORECASE
)


def detect_platform(url):
    if not url: return None
    for pat, name in ATS_PATTERNS:
        if re.search(pat, url, re.I):
            return name
    return None


def is_ats_url(url):
    if not url or not url.startswith("http"): return False
    if any(d in url for d in SKIP_DOMAINS): return False
    path = url.split("?")[0].lower()
    if any(path.endswith(e) for e in (".pdf", ".png", ".jpg", ".zip")): return False
    if detect_platform(url): return True
    return any(k in url.lower() for k in
               ("/job/", "/jobs/", "/apply", "/careers/", "/opening/",
                "jobid=", "reqid=", "/position/"))


# ── Chrome driver ──────────────────────────────────────────────────────────────

def build_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--lang=en-US")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    d = webdriver.Chrome(options=opts)
    d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        window.chrome={runtime:{}};
    """})
    return d


# ── Session management ─────────────────────────────────────────────────────────

def is_logged_in(driver):
    """True if the Jobright session is active (checks cookies — no navigation)."""
    # 1. Fast cookie check — no page load needed
    try:
        cookies = {c["name"] for c in driver.get_cookies()}
        if any(kw in n.lower() for n in cookies
               for kw in ("token", "session", "auth", "jwt", "access")):
            return True
    except Exception:
        pass
    # 2. DOM check on current page (if jobright.ai is already loaded)
    try:
        if "jobright.ai" in driver.current_url:
            btns = driver.find_elements(
                By.XPATH,
                "//*[normalize-space(text())='SIGN IN' or normalize-space(text())='JOIN NOW']"
            )
            if btns and any(b.is_displayed() for b in btns):
                return False
            for xpath in [
                "//span[normalize-space(text())='Resume']",
                "//span[normalize-space(text())='Profile']",
                "//*[contains(@class,'avatar')]",
            ]:
                els = driver.find_elements(By.XPATH, xpath)
                if els and any(e.is_displayed() for e in els):
                    return True
    except Exception:
        pass
    return False


def do_login(driver, email, password):
    """Login via the SIGN IN modal on the Jobright homepage."""
    print(f"🔐 Logging in as {email}...")
    try:
        driver.get("https://jobright.ai")
        time.sleep(4)

        for xpath in [
            "//button[normalize-space(text())='SIGN IN']",
            "//a[normalize-space(text())='SIGN IN']",
            "//*[normalize-space(text())='SIGN IN']",
            "//*[normalize-space(text())='Sign In']",
        ]:
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath)))
                btn.click()
                print(f"  ✅ Clicked SIGN IN")
                time.sleep(3)
                break
            except Exception:
                continue

        email_field = None
        for xpath in [
            "//input[@type='email']",
            "//input[contains(@placeholder,'mail')]",
            "//input[contains(@name,'email')]",
            "//div[contains(@class,'modal')]//input[1]",
            "//form//input[1]",
        ]:
            try:
                email_field = WebDriverWait(driver, 6).until(
                    EC.visibility_of_element_located((By.XPATH, xpath)))
                break
            except Exception:
                continue

        if not email_field:
            print("  ❌ Email field not found")
            return False

        email_field.clear()
        email_field.send_keys(email)
        time.sleep(0.5)

        pw_field = None
        for xpath in ["//input[@type='password']",
                      "//input[contains(@placeholder,'assword')]"]:
            try:
                pw_field = driver.find_element(By.XPATH, xpath)
                break
            except Exception:
                continue

        if not pw_field:
            print("  ❌ Password field not found")
            return False

        pw_field.clear()
        pw_field.send_keys(password)
        time.sleep(0.5)

        for xpath in [
            "//button[@type='submit']",
            "//button[normalize-space(text())='SIGN IN']",
            "//button[contains(.,'SIGN IN')]",
        ]:
            try:
                sub = WebDriverWait(driver, 4).until(
                    EC.element_to_be_clickable((By.XPATH, xpath)))
                sub.click()
                print("  ✅ Login submitted")
                break
            except Exception:
                continue
        else:
            pw_field.send_keys("\n")

        time.sleep(5)
        print(f"  🌐 Post-login: {driver.current_url}")
        return True

    except Exception as e:
        print(f"  ❌ Login error: {e}")
        return False


def ensure_session(driver, email, password, max_retries=3, headless=False):
    """
    Re-login if session expired.
    If the driver itself is dead (ConnectionRefused), it attempts to restart the browser.
    """
    # 1. Check if driver is alive
    is_alive = False
    try:
        _ = driver.current_url
        is_alive = True
    except Exception:
        print("  ⚠️  Browser process appears dead (connection lost).")

    # 2. If dead, we MUST restart the driver
    if not is_alive:
        print("  🔄 Restarting browser...")
        try:
            driver.quit()
        except Exception:
            pass
        # We need a way to call build_driver again.
        # Since build_driver is global, we can just call it.
        try:
            new_driver = build_driver(headless=headless)
            # Update the caller's driver reference (Note: this only works if they use the return value)
            # But in Step 2 loop, we are passing the driver object.
            # We'll return the (potentially new) driver.
            if do_login(new_driver, email, password):
                return new_driver
            return None
        except Exception as e:
            print(f"  ❌ Failed to restart browser: {e}")
            return None

    # 3. If alive, check login status
    if is_logged_in(driver):
        return driver

    print("  ⚠️  Session expired — re-logging in...")
    for attempt in range(1, max_retries + 1):
        if do_login(driver, email, password):
            if is_logged_in(driver):
                print(f"  ✅ Re-login successful (attempt {attempt})")
                return driver
            print(f"  ⚠️  Login submitted but session not confirmed (attempt {attempt})")
            time.sleep(3)
        else:
            print(f"  ❌ Login attempt {attempt} failed")
            time.sleep(2)
    print("  ❌ Could not restore session after all retries")
    return None


# ── Step 2: ATS extraction helpers ────────────────────────────────────────────

def dismiss_modals(driver, timeout=3):
    """Dismiss post-Apply modals: Customize Resume, Autofill, Orion tour."""
    for xpath in [
        "//a[contains(normalize-space(.),'Apply Without Customizing')]",
        "//button[contains(normalize-space(.),'Apply Without Customizing')]",
        "//*[contains(normalize-space(.),'Apply without Customizing')]",
        "//a[contains(normalize-space(.),'Apply Manually')]",
        "//button[contains(normalize-space(.),'Apply Manually')]",
        "//button[normalize-space(text())='EXIT']",
        "//button[normalize-space(text())='Exit']",
        "//button[normalize-space(text())='Got it']",
        "//*[@aria-label='Close' or @aria-label='close']",
        "//button[normalize-space(text())='×']",
    ]:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath)))
            el.click()
            print(f"    🗙 Modal dismissed: '{el.text.strip()[:30]}'")
            time.sleep(1.5)
            return True
        except Exception:
            continue
    return False


def close_signup_modal(driver):
    """Close the 'Sign Up to Apply' modal that appears when not logged in."""
    for xpath in [
        "//button[@aria-label='Close' or @aria-label='close']",
        "//button[normalize-space(text())='×' or normalize-space(text())='✕']",
        "//*[contains(@class,'modal')]//button[1]",
        "//div[contains(@class,'modal')]//button",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            if els:
                els[0].click()
                time.sleep(1)
                return True
        except Exception:
            continue
    # Fallback: Escape
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
        return True
    except Exception:
        pass
    return False


def _scan_source(driver):
    try:
        src = driver.page_source
        for m in ATS_RE.findall(src):
            m = m.strip().rstrip('"\'')
            if "jobright.ai" not in m.lower() and is_ats_url(m):
                return m
    except Exception:
        pass
    return None


def get_ats_url(driver, job_id, jobright_url, email, password):
    """
    Extract the real ATS apply URL for one job.
    Uses the same browser session — no new browser started.
    """
    url = jobright_url or f"https://jobright.ai/jobs/info/{job_id}"
    main = driver.current_window_handle

    try:
        driver.get(url)
        time.sleep(random.uniform(3.5, 5.5))

        # Layer 1: "Original Job Post" direct link
        for xpath in [
            "//a[contains(normalize-space(.),'Original Job Post')]",
            "//a[contains(normalize-space(.),'Original Job')]",
            "//span[contains(.,'Original Job Post')]/ancestor::a",
        ]:
            try:
                el = WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((By.XPATH, xpath)))
                href = el.get_attribute("href") or ""
                if href and is_ats_url(href):
                    print(f"    ✅ [Original Job Post] {href}")
                    return {"ats_url": href, "ats_platform": detect_platform(href) or "unknown"}
            except Exception:
                continue

        # Layer 2: Find Apply button
        apply_btn = None
        for xpath in [
            "//button[contains(normalize-space(.),'APPLY NOW')]",
            "//a[contains(normalize-space(.),'APPLY NOW')]",
            "//button[contains(normalize-space(.),'APPLY WITH AUTOFILL')]",
            "//a[contains(normalize-space(.),'APPLY WITH AUTOFILL')]",
            "//button[contains(normalize-space(.),'Apply Now')]",
            "//a[contains(normalize-space(.),'Apply on Employer')]",
        ]:
            try:
                apply_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath)))
                print(f"    🔘 Apply: '{apply_btn.text.strip()[:30]}'")
                break
            except Exception:
                continue

        if not apply_btn:
            print("    ⚠️  No Apply button")
            return None

        # Direct href on <a>?
        if apply_btn.tag_name.lower() == "a":
            href = apply_btn.get_attribute("href") or ""
            if is_ats_url(href):
                print(f"    ✅ [Apply href] {href}")
                return {"ats_url": href, "ats_platform": detect_platform(href) or "unknown"}

        # Layer 3: Click → modal → new tab
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", apply_btn)
            time.sleep(0.5)
        except Exception:
            pass

        handles_before = set(driver.window_handles)

        try:
            apply_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", apply_btn)

        time.sleep(2.5)

        # Check for "Sign Up to Apply" (session lost mid-run)
        signup = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(text()),'Sign Up to Apply') "
            "or contains(normalize-space(text()),'Already a member')]"
        )
        if signup and any(el.is_displayed() for el in signup):
            print("    ⚠️  Sign Up modal — re-logging in...")
            close_signup_modal(driver)
            time.sleep(1)
            if ensure_session(driver, email, password):
                time.sleep(2)
                driver.get(url)
                time.sleep(random.uniform(3, 5))
                # Retry Apply once more
                for axpath in [
                    "//button[contains(normalize-space(.),'APPLY NOW')]",
                    "//a[contains(normalize-space(.),'APPLY NOW')]",
                    "//button[contains(normalize-space(.),'APPLY WITH AUTOFILL')]",
                ]:
                    try:
                        rb = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, axpath)))
                        hb2 = set(driver.window_handles)
                        try:
                            rb.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", rb)
                        time.sleep(2.5)
                        dismiss_modals(driver, 3)
                        time.sleep(1)
                        dismiss_modals(driver, 2)
                        time.sleep(1)
                        nh = [h for h in driver.window_handles if h not in hb2]
                        if nh:
                            driver.switch_to.window(nh[0])
                            time.sleep(3)
                            u2 = driver.current_url
                            driver.close()
                            driver.switch_to.window(main)
                            if is_ats_url(u2):
                                print(f"    ✅ [Retry/New Tab] {u2}")
                                return {"ats_url": u2, "ats_platform": detect_platform(u2) or "unknown"}
                        break
                    except Exception:
                        continue
            return None

        # Dismiss Customize Resume / Autofill / Orion modals
        dismiss_modals(driver, 3)
        time.sleep(1)
        dismiss_modals(driver, 2)
        time.sleep(1)

        # New tab opened?
        new_handles = [h for h in driver.window_handles if h not in handles_before]
        if new_handles:
            try:
                driver.switch_to.window(new_handles[0])
                time.sleep(3)
                ats = driver.current_url
                driver.close()
                driver.switch_to.window(main)
                if is_ats_url(ats):
                    print(f"    ✅ [New Tab] {ats}")
                    return {"ats_url": ats, "ats_platform": detect_platform(ats) or "unknown"}
                print(f"    ⚠️  New tab not ATS: {ats}")
            except Exception as te:
                print(f"    ⚠️  Tab error: {te}")
                try:
                    driver.switch_to.window(driver.window_handles[0])
                except Exception:
                    pass
        else:
            # Same-tab redirect
            time.sleep(2)
            cur = driver.current_url
            if is_ats_url(cur):
                print(f"    ✅ [Same-tab] {cur}")
                return {"ats_url": cur, "ats_platform": detect_platform(cur) or "unknown"}

        # Layer 4: Page source regex
        ats = _scan_source(driver)
        if ats:
            print(f"    ✅ [Page source] {ats}")
            return {"ats_url": ats, "ats_platform": detect_platform(ats) or "unknown"}

        return None

    except Exception as e:
        print(f"    ❌ Error: {e}")
        try:
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[0])
        except Exception:
            pass
        return None


# ── JSON helpers ───────────────────────────────────────────────────────────────

def save_jobs(filepath, jobs):
    tmp = filepath + ".tmp"
    payload = {
        "source":  "jobright.ai",
        "step":    2,
        "updated": datetime.now().isoformat(),
        "count":   len(jobs),
        "jobs":    jobs,
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, filepath)


def load_jobs(filepath):
    if not os.path.isfile(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f).get("jobs", [])


# ── Main pipeline ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Jobright full pipeline — one browser, one session")
    ap.add_argument("--output",        default="jobright_jobs.json")
    ap.add_argument("--visible",       action="store_true", help="Show browser window (default: headless)")
    ap.add_argument("--headless",      action="store_true", help="Force headless mode")
    ap.add_argument("--skip-step1",    action="store_true", help="Skip scraping, use existing JSON")
    ap.add_argument("--skip-step2",    action="store_true", help="Skip ATS enrichment")
    ap.add_argument("--job-limit",     type=int, default=None, help="Max jobs to collect in Step 1")
    ap.add_argument("--ats-limit",     type=int, default=None, help="Max jobs to enrich in Step 2")
    ap.add_argument("--reprocess-all", action="store_true",  help="Re-enrich jobs that already have ats_url")
    ap.add_argument("--keyword",       type=str, default=None, help="Override search keyword")
    ap.add_argument("--location",      type=str, default=None, help="Override location")
    args = ap.parse_args()
    # --visible takes priority over --headless
    headless = args.headless and not args.visible

    output_file = args.output
    start_time  = datetime.now()

    # Load config + credentials
    config = _load_jobright_config()
    creds  = config.get("credentials", {})
    email    = creds.get("email", "")
    password = creds.get("password", "")

    if args.keyword:
        config["search_keywords"] = [args.keyword]
    if args.location:
        config["location"] = args.location

    print("=" * 62)
    print("  🚀 Jobright Pipeline — ONE browser, ONE session")
    print(f"  Output  : {output_file}")
    print(f"  Visible : {args.visible or not headless}")
    print(f"  Step 1  : {'SKIP' if args.skip_step1 else 'RUN'}")
    print(f"  Step 2  : {'SKIP' if args.skip_step2 else 'RUN'}")
    print("=" * 62)

    driver = None
    try:
        print("\n🚀 Starting Chrome...")
        driver = build_driver(headless=headless)

        # ── Login once ────────────────────────────────────────────────────
        if email and password:
            do_login(driver, email, password)
            time.sleep(2)
        else:
            print("⚠️  No credentials found in config/jobright.json")

        # ── Step 1: Scrape ────────────────────────────────────────────────
        jobs = []
        if not args.skip_step1:
            print("\n" + "=" * 62)
            print("  📋 Step 1 — Scraping job listings")
            print("=" * 62)

            strategy = JobrightStrategy(driver=driver, config_override=config)
            strategy._is_logged_in = True  # already logged in above

            try:
                new_jobs = strategy.find_jobs()
            except Exception as e:
                print(f"\n❌ Step 1 failed during find_jobs: {e}")
                new_jobs = []

            if args.job_limit:
                new_jobs = new_jobs[:args.job_limit]
                print(f"  ✂️  Limited to {len(new_jobs)} jobs")

            # Merge with existing file
            existing = load_jobs(output_file)
            existing_ids = {j.get("job_id") for j in existing if j.get("job_id")}
            fresh = [j for j in new_jobs if j.get("job_id") not in existing_ids]
            print(f"  📥 {len(existing)} existing + {len(fresh)} new = {len(existing)+len(fresh)} total")
            jobs = existing + fresh
            save_jobs(output_file, jobs)
            print(f"  💾 Saved {len(jobs)} jobs → {output_file}")
        else:
            print("\n⏭️  Skipping Step 1")
            jobs = load_jobs(output_file)
            print(f"  📂 Loaded {len(jobs)} jobs from {output_file}")

        # ── Step 2: ATS enrichment ─────────────────────────────────────────
        if not args.skip_step2 and jobs:
            print("\n" + "=" * 62)
            print("  🔗 Step 2 — Extracting ATS apply URLs")
            print("=" * 62)

            if args.reprocess_all:
                pending_idx = list(range(len(jobs)))
            else:
                # Treat missing key AND explicit null both as pending
                pending_idx = [
                    i for i, j in enumerate(jobs)
                    if "ats_url" not in j or j["ats_url"] is None
                ]

            if args.ats_limit:
                pending_idx = pending_idx[:args.ats_limit]

            already_done = len(jobs) - len(pending_idx) if not args.reprocess_all else 0
            print(f"  Pending: {len(pending_idx)}  |  Already done: {already_done}")

            ok = fail = consecutive_session_failures = 0
            MAX_CONSECUTIVE_SESSION_FAILURES = 5  # abort if session keeps failing

            for n, idx in enumerate(pending_idx, 1):
                job   = jobs[idx]
                jid   = job.get("job_id", "")
                jurl  = job.get("jobright_url") or job.get("url") or \
                        f"https://jobright.ai/jobs/info/{jid}"
                title = job.get("title", "?")

                print(f"\n  [{n}/{len(pending_idx)}] {title}")

                # Verify session before every job (only checks cookies, no nav)
                updated_driver = ensure_session(driver, email, password, headless=headless)
                if not updated_driver:
                    consecutive_session_failures += 1
                    print(f"    ❌ Cannot restore session ({consecutive_session_failures}/{MAX_CONSECUTIVE_SESSION_FAILURES}) — skipping")
                    fail += 1
                    if consecutive_session_failures >= MAX_CONSECUTIVE_SESSION_FAILURES:
                        print(f"\n  🚫 Session unrecoverable after {MAX_CONSECUTIVE_SESSION_FAILURES} consecutive failures. Aborting Step 2.")
                        break
                    continue
                else:
                    driver = updated_driver  # update local reference
                    consecutive_session_failures = 0  # reset on success

                result = get_ats_url(driver, jid, jurl, email, password)

                if result:
                    jobs[idx]["ats_url"]      = result["ats_url"]
                    jobs[idx]["ats_platform"] = result["ats_platform"]
                    ok += 1
                    print(f"    🏷  Platform: {result['ats_platform']}")
                else:
                    jobs[idx]["ats_url"]      = None
                    jobs[idx]["ats_platform"] = None
                    fail += 1

                save_jobs(output_file, jobs)
                pause = random.uniform(2.5, 5)
                print(f"    ⏳ {pause:.1f}s pause...")
                time.sleep(pause)

            print(f"\n  ✅ Step 2 done — Success: {ok}  |  Failed: {fail}")
        else:
            print("\n⏭️  Skipping Step 2")

        # ── Summary ────────────────────────────────────────────────────────
        elapsed = datetime.now() - start_time
        mins, secs = divmod(int(elapsed.total_seconds()), 60)
        enriched = sum(1 for j in jobs if j.get("ats_url"))

        print("\n" + "=" * 62)
        print(f"  ✅ Pipeline Complete")
        print(f"  Total jobs  : {len(jobs)}")
        print(f"  Enriched    : {enriched} / {len(jobs)}")
        print(f"  Elapsed     : {mins}m {secs}s")
        print(f"  Output      : {output_file}")
        print("=" * 62)

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted — results saved.")
    except Exception as e:
        import traceback
        print(f"\n❌ Fatal: {e}")
        traceback.print_exc()
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            print("🔒 Browser closed.")


if __name__ == "__main__":
    main()
