"""
Jobright.ai Scraper Strategy
Mirrors HiringCafeStrategy architecture exactly:
  - Same Selenium + human behavior approach
  - Same multi-layer ATS URL extraction (6 layers)
  - Same infinite scroll + checkpoint/resume pattern
  - Same blocked-page detection fingerprinting
  - Same keyword boolean filtering

Job link pattern  : <a href="/jobs/info/{job_id}">...</a>
Apply button      : "Apply on Employer Site" / "APPLY NOW" → opens ATS in new tab
"""

import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import quote, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from core.logger import logger
from core.browser import browser_service
from core.safe_actions import SafeActions
from core.human_behavior import HumanBehavior

# ─────────────────────────────────────────────────────────────────────────────
# SELECTORS
# ─────────────────────────────────────────────────────────────────────────────

# Jobright job listing links: /jobs/info/{job_id}
# Using partial match for robustness (handles absolute/relative URLs)
JOB_LINK_SELECTOR = 'a[href*="/jobs/info/"]'

# Apply button on job detail page (opens ATS in new tab)
APPLY_NOW_BUTTON_XPATH = """
//button[@id='apply-now-button-id']
| //a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply now')]
| //a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply on employer')]
| //button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]
| //a[@class and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]
"""

APPLY_BUTTON_FALLBACK_XPATHS = [
    "//button[contains(@class, 'index_applyButton')]",
    "//a[contains(@class, 'index_applyButton')]",
    "//a[@aria-label and contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
    "//*[@data-testid and contains(translate(@data-testid,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'apply')]",
    "//button[contains(@id, 'apply-button')]",
    "//button[contains(@class, 'apply')]",
    "//a[@target='_blank' and not(contains(@href,'jobright.ai')) and starts-with(@href,'http')]",
    "//a[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view job')]",
]

ORIGINAL_JOB_POST_LINK_XPATH = "//a[contains(@class, 'index_origin') or contains(., 'Original Job Post')]"

# ─────────────────────────────────────────────────────────────────────────────
# ATS PLATFORM DETECTION  (same list as Hiring Cafe)
# ─────────────────────────────────────────────────────────────────────────────

ATS_PLATFORM_PATTERNS = [
    (r"lever\.co|jobs\.lever\.", "lever"),
    (r"greenhouse\.io|boards\.greenhouse|jobs\.greenhouse|job-boards\.greenhouse", "greenhouse"),
    (r"sapsf\.com|successfactors\.com", "successfactors"),
    (r"workday\.com|myworkdayjobs\.com|wd\d+\.myworkdayjobs\.com", "workday"),
    (r"adp\.com|workforcenow\.adp\.com", "adp"),
    (r"smartrecruiters\.com", "smartrecruiters"),
    (r"icims\.com", "icims"),
    (r"jobvite\.com", "jobvite"),
    (r"taleo\.net|taleocdn", "taleo"),
    (r"apply\.workable\.com|workable\.com", "workable"),
    (r"bamboohr\.com", "bamboohr"),
    (r"paycom\.com", "paycom"),
    (r"paychex\.com", "paychex"),
    (r"ultipro\.com", "ultipro"),
    (r"linkedin\.com/jobs", "linkedin"),
    (r"indeed\.com", "indeed"),
    (r"ashbyhq\.com", "ashby"),
    (r"recruitee\.com", "recruitee"),
    (r"teamtailor\.com", "teamtailor"),
    (r"personio\.com", "personio"),
    (r"oraclecloud\.com", "oraclecloud"),
    (r"applytojob\.com", "applytojob"),
    (r"brassring\.com", "brassring"),
    (r"rippling\.com", "rippling"),
    (r"paylocity\.com", "paylocity"),
    (r"breezy\.hr", "breezy"),
    (r"jazz\.co", "jazz"),
    (r"pinpointrecruitment\.com", "pinpoint"),
    (r"dover\.com", "dover"),
    (r"phenompeople\.com", "phenom"),
    (r"careers\.google\.com/jobs|careers\.google\.com/intl", "google"),
    (r"jobs\.apple\.com", "apple"),
    (r"microsoft\.com/.*careers", "microsoft"),
    (r"workdayjobs\.com", "workday"),
    (r"eightfold\.ai", "eightfold"),
    (r"oracle\.com/careers", "oracle"),
    (r"careers\.jobright\.ai", "jobright_direct"),
]

# Regex to find ATS URLs in raw page source
ATS_URL_REGEX = re.compile(
    r'https?://(?:'
    r'[a-z0-9-]+\.lever\.co'
    r'|jobs\.lever\.co'
    r'|boards\.greenhouse\.io'
    r'|[a-z0-9-]+\.greenhouse\.io'
    r'|jobs\.greenhouse\.io'
    r'|job-boards\.greenhouse\.io'
    r'|[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com'
    r'|[a-z0-9-]+\.myworkdayjobs\.com'
    r'|[a-z0-9-]+\.workday\.com'
    r'|[a-z0-9-]+\.successfactors\.com'
    r'|[a-z0-9-]+\.sapsf\.com'
    r'|[a-z0-9-]+\.ashbyhq\.com'
    r'|jobs\.ashbyhq\.com'
    r'|[a-z0-9-]+\.smartrecruiters\.com'
    r'|jobs\.smartrecruiters\.com'
    r'|[a-z0-9-]+\.icims\.com'
    r'|[a-z0-9-]+\.jobvite\.com'
    r'|[a-z0-9-]+\.taleo\.net'
    r'|apply\.workable\.com'
    r'|[a-z0-9-]+\.workable\.com'
    r'|[a-z0-9-]+\.bamboohr\.com'
    r'|[a-z0-9-]+\.recruitee\.com'
    r'|[a-z0-9-]+\.teamtailor\.com'
    r'|[a-z0-9-]+\.personio\.com'
    r'|[a-z0-9-]+\.rippling\.com'
    r'|[a-z0-9-]+\.paylocity\.com'
    r'|[a-z0-9-]+\.breezy\.hr'
    r'|[a-z0-9-]+\.jazz\.co'
    r'|app\.jazz\.co'
    r'|[a-z0-9-]+\.applytojob\.com'
    r'|[a-z0-9-]+\.brassring\.com'
    r'|[a-z0-9-]+\.oraclecloud\.com'
    r'|[a-z0-9-]+\.phenompeople\.com/(?:careers|jobs)'
    r'|[a-z0-9-]+\.dover\.com'
    r'|[a-z0-9-]+\.pinpointrecruitment\.com'
    r'|[a-z0-9-]+\.eightfold\.ai'
    r')[/\w\-\.\?\=\&\%\#\@\+]*',
    re.IGNORECASE
)

# Blocked/empty page fingerprints (update after observing real blocked responses)
BLOCKED_PAGE_SIZES = {5000, 6000}   # update with real values from observation
BLOCKED_DIV_COUNT  = {10, 12}       # update with real values
BLOCKED_LINK_COUNT = 3              # update with real values

NON_ATS_URL_DOMAINS = (
    "reddit.com", "twitter.com", "x.com", "facebook.com",
    "linkedin.com/share", "linkedin.com/feed",
    "t.co", "wa.me", "telegram.me", "whatsapp.com",
)

NON_JOB_PATH_SEGMENTS = (
    "/eeo", "/diversity", "/inclusion", "/accessibility",
    "/privacy", "/terms", "/legal", "/cookie", "/sitemap",
    "/about", "/contact", "/press", "/news", "/blog",
    "/faq", "/help", "/support", "/login", "/register",
    "/sign-in", "/sign-up", "/subscribe",
)

# File extensions that are never job application URLs
NON_JOB_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx",
                       ".png", ".jpg", ".jpeg", ".gif", ".zip")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _job_id_from_href(href: str) -> str | None:
    """Extract job_id from href like '/jobs/info/69a9715b7f9271426f8850a5'."""
    if not href:
        return None
    match = re.search(r"/jobs/info/([a-zA-Z0-9_-]+)", href)
    return match.group(1) if match else None


def detect_ats_platform(url: str) -> str | None:
    if not url:
        return None
    url_lower = url.lower()
    for pattern, platform in ATS_PLATFORM_PATTERNS:
        if re.search(pattern, url_lower):
            return platform
    return None


def is_likely_ats_url(url: str) -> bool:
    """Strict check — return True only for real job posting URLs."""
    if not url or not url.strip().startswith("http"):
        return False

    url_stripped = url.strip()
    url_lower = url_stripped.lower()

    if "jobright.ai" in url_lower:
        return False

    for domain in NON_ATS_URL_DOMAINS:
        if domain in url_lower:
            return False

    path_part = url_lower.split("?")[0].split("#")[0]
    if any(path_part.endswith(ext) for ext in NON_JOB_EXTENSIONS):
        return False

    for segment in NON_JOB_PATH_SEGMENTS:
        if segment in url_lower:
            return False

    parsed = urlparse(url_stripped)
    path = parsed.path.rstrip("/")
    path_depth = len([p for p in path.split("/") if p])

    if path_depth == 0:
        return False
    if path_depth == 1 and not detect_ats_platform(url_stripped):
        return False

    if detect_ats_platform(url_stripped):
        return True

    job_path_keywords = (
        "/job/", "/jobs/", "/job-detail", "/jobdetail", "/jobboard",
        "/apply/", "/apply?", "/careers/job", "/career/job",
        "/opening/", "/openings/", "/opportunity/", "/opportunities/",
        "/req/", "/requisition/", "/vacancy/", "/vacancies/",
        "/position/", "/positions/", "/listing/", "/listings/",
        "jobid=", "jobId=", "job_id=", "referenceid=", "reqid=",
    )
    if any(kw in url_lower for kw in job_path_keywords):
        return True

    return False


def _load_jobright_config() -> dict:
    """Load config from config/jobright.json. Returns {} if missing."""
    try:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "config", "jobright.json",
        )
        if os.path.isfile(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load jobright config: {e}")
    return {}


def _build_search_url(keyword: str, base_url: str = "https://jobright.ai") -> str:
    """
    Build Jobright search URL.
    Pattern: https://jobright.ai/jobs/{keyword-slug}-jobs
    e.g.   : https://jobright.ai/jobs/python-developer-jobs
             https://jobright.ai/jobs/python-developer-jobs-in-united-states
    """
    slug = keyword.strip().lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug).strip('-')
    return f"{base_url}/jobs/{slug}-jobs"


def _build_search_url_with_location(
    keyword: str,
    location: str = "",
    base_url: str = "https://jobright.ai",
) -> str:
    """
    Use Jobright's actual search endpoint which returns ALL matching jobs
    (vs. slug URLs which only return ~7 cached results).
    Pattern: https://jobright.ai/jobs/search?value={keyword}&searchType=job_title&country=US
    """
    encoded_kw = quote(keyword.strip(), safe="")
    return f"{base_url}/jobs/search?value={encoded_kw}&searchType=job_title&country=US"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN STRATEGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class JobrightStrategy:
    """
    Jobright.ai scraper strategy.

    Mirrors HiringCafeStrategy exactly:
      Phase 1 — Search + infinite scroll → collect job IDs + card metadata
      Phase 2 — Visit each job detail page → extract ATS URL (6 layers)
      Output  — JSON with checkpoint/resume support
    """

    def __init__(
        self,
        driver,
        config_override: dict | None = None,
    ):
        config = config_override or _load_jobright_config()

        # Keywords
        if config.get("search_keywords"):
            keywords = [str(k).strip() for k in config["search_keywords"] if str(k).strip()]
        elif config.get("search_keyword"):
            keywords = [str(config["search_keyword"]).strip()]
        else:
            env_kw = os.environ.get("JOBRIGHT_SEARCH_KEYWORD", "").strip()
            keywords = [env_kw] if env_kw else ["Software Engineer"]

        # Credentials
        self._credentials = config.get("credentials", {})
        self._is_logged_in = False
        self._search_keywords = keywords or ["Software Engineer"]
        self._location = config.get("location", "").strip()

        self.driver = driver
        self.base_url = "https://jobright.ai"
        
        # Core components
        self.safe = SafeActions(driver)
        self.human = HumanBehavior(driver)

        # Timing settings
        self._random_pause_lo    = float(config.get("random_pause_min_sec", 3.0))
        self._random_pause_hi    = float(config.get("random_pause_max_sec", 7.0))
        self._scroll_step_lo     = float(config.get("scroll_step_min_sec", 1.5))
        self._scroll_step_hi     = float(config.get("scroll_step_max_sec", 3.5))
        self._step2_pause_lo     = float(config.get("step2_pause_min_sec", 2.0))
        self._step2_pause_hi     = float(config.get("step2_pause_max_sec", 5.0))
        self._step2_page_lo      = float(config.get("step2_page_settle_min_sec", 2.0))
        self._step2_page_hi      = float(config.get("step2_page_settle_max_sec", 4.0))
        self._step2_shuffle      = bool(config.get("step2_shuffle_pending", False))
        self._step2_break_every  = int(config.get("step2_break_every_n", 20))
        self._step2_long_break_lo= float(config.get("step2_long_break_min_sec", 15.0))
        self._step2_long_break_hi= float(config.get("step2_long_break_max_sec", 30.0))
        self._step2_mouse_jitter = bool(config.get("step2_mouse_jitter", False))

        logger.info(
            f"JobrightStrategy initialized "
            f"(keywords={self._search_keywords}, location='{self._location}')"
        )

    def login(self) -> bool:
        """
        Perform Jobright.ai login.
        Multi-strategy: navigate to /login page → fill form → submit → verify cookie.
        """
        if not self._credentials or not self._credentials.get("email"):
            print("ℹ️ No credentials found in config — skipping login.")
            return False

        email    = self._credentials["email"]
        password = self._credentials["password"]

        try:
            logger.info(f"🔐 Attempting login for {email}...")

            # ── Check if already logged in first ──────────────────────────────
            self.driver.get(self.base_url)
            time.sleep(3)
            
            is_logged_in = False
            for av_xpath in [
                "//*[contains(@class,'avatar')]",
                "//button[contains(@aria-label,'account')]",
                "//img[contains(@alt,'avatar')]",
                "//*[contains(@class,'Sidebar_sidebar')]//div[contains(@class,'index_user')]",
            ]:
                if self.driver.find_elements(By.XPATH, av_xpath):
                    is_logged_in = True
                    break
            
            if is_logged_in:
                logger.info("✅ Already logged in (session active)")
                self._is_logged_in = True
                return True

            # ── Strategy 1: navigate directly to the login page ───────────────
            self.driver.get(f"{self.base_url}/login")
            time.sleep(3)

            # If redirected (already logged in / no /login route) try homepage modal
            if "/login" not in self.driver.current_url.lower():
                logger.info("[LOGIN] /login redirected — trying homepage SIGN IN modal...")
                self.driver.get(self.base_url)
                time.sleep(2)
                # Look for any SIGN IN / Log In link
                for xpath in [
                    "//*[normalize-space(text())='SIGN IN']",
                    "//*[normalize-space(text())='Sign In']",
                    "//*[normalize-space(text())='Log In']",
                    "//a[contains(@href,'/login')]",
                ]:
                    try:
                        btn = WebDriverWait(self.driver, 4).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        btn.click()
                        time.sleep(2)
                        break
                    except Exception:
                        continue

            # ── Fill email ────────────────────────────────────────────────────
            email_field = None
            for email_xpath in [
                "//input[@type='email']",
                "//input[contains(@placeholder,'mail')]",
                "//input[contains(@name,'email')]",
                "//input[contains(@id,'email')]",
            ]:
                try:
                    email_field = WebDriverWait(self.driver, 6).until(
                        EC.presence_of_element_located((By.XPATH, email_xpath))
                    )
                    break
                except Exception:
                    continue

            if not email_field:
                logger.error("❌ Login failed: email input not found")
                return False

            email_field.clear()
            email_field.send_keys(email)
            time.sleep(0.8)

            # ── Fill password ─────────────────────────────────────────────────
            pw_field = None
            for pw_xpath in [
                "//input[@type='password']",
                "//input[contains(@placeholder,'assword')]",
                "//input[contains(@name,'password')]",
            ]:
                try:
                    pw_field = self.driver.find_element(By.XPATH, pw_xpath)
                    break
                except Exception:
                    continue

            if not pw_field:
                logger.error("❌ Login failed: password input not found")
                return False

            pw_field.clear()
            pw_field.send_keys(password)
            time.sleep(0.8)

            # ── Submit ────────────────────────────────────────────────────────
            submitted = False
            for sub_xpath in [
                "//button[@type='submit']",
                "//button[.//span[normalize-space(text())='SIGN IN']]",
                "//button[normalize-space(text())='SIGN IN']",
                "//button[normalize-space(text())='Sign In']",
                "//button[normalize-space(text())='Log In']",
            ]:
                try:
                    sub_btn = WebDriverWait(self.driver, 4).until(
                        EC.element_to_be_clickable((By.XPATH, sub_xpath))
                    )
                    sub_btn.click()
                    submitted = True
                    break
                except Exception:
                    continue

            if not submitted:
                logger.info("[LOGIN] Submit button not found — pressing Enter on password field")
                pw_field.send_keys("\n")

            # ── Verify login ──────────────────────────────────────────────────
            # Wait up to 10s for a logged-in indicator:
            # - URL changes away from /login
            # - A cookie containing 'token' or 'session' appears
            # - An avatar / logout link appears
            time.sleep(5)
            cookies = {c["name"]: c["value"] for c in self.driver.get_cookies()}
            has_auth_cookie = any(
                kw in name.lower()
                for name in cookies
                for kw in ("token", "session", "auth", "jwt", "access")
            )
            logged_in_url = "/login" not in self.driver.current_url.lower()

            # Check for user avatar / profile indicator in DOM
            has_avatar = False
            for av_xpath in [
                "//*[contains(@class,'avatar')]",
                "//*[contains(@class,'user-info')]",
                "//*[contains(@class,'profile')]",
                "//button[contains(@aria-label,'account')]",
                "//img[contains(@alt,'avatar')]",
            ]:
                try:
                    self.driver.find_element(By.XPATH, av_xpath)
                    has_avatar = True
                    break
                except Exception:
                    pass

            if has_auth_cookie or (logged_in_url and has_avatar):
                self._is_logged_in = True
                print(f"✅ Login successful (cookie={has_auth_cookie}, url_ok={logged_in_url}, avatar={has_avatar})")
                return True
            else:
                # Treat as logged-in anyway — form was submitted, proceed optimistically
                print("⚠️ Login verification uncertain — proceeding optimistically")
                self._is_logged_in = True
                return True

        except Exception as e:
            print(f"❌ Login failed: {e}")
            import traceback; traceback.print_exc()
            return False

    def _apply_date_filter(self) -> bool:
        """
        Apply 'Last 24 hours' date filter.
        Must be called BEFORE _scroll_until_end() so only filtered jobs load.
        Uses only text-based XPaths — no absolute paths that break on DOM changes.
        """
        MAX_ATTEMPTS = 3

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                # Step 1: Open the Date Posted dropdown
                date_btn_xpaths = [
                    "//button[.//span[contains(text(),'Date Posted')]]",
                    "//button[contains(normalize-space(.),'Date Posted')]",
                    "//span[normalize-space(text())='Date Posted']",
                    "//*[contains(normalize-space(text()),'Date Posted')]",
                ]
                clicked_filter = False
                for xpath in date_btn_xpaths:
                    try:
                        btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        btn.click()
                        time.sleep(1.5)
                        clicked_filter = True
                        print(f"  [DateFilter] Opened dropdown (attempt {attempt})")
                        break
                    except Exception:
                        continue

                if not clicked_filter:
                    print(f"  [DateFilter] Dropdown not found (attempt {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(2)
                    continue

                # Step 2: Click the 24-hour radio — text-based only, no absolute XPath
                radio_xpaths = [
                    "//label[contains(., 'Past 24 hours')]",
                    "//span[contains(text(), 'Past 24 hours')]",
                    "//label[contains(normalize-space(.),'24')]",
                    "//span[contains(normalize-space(text()),'24 hour')]",
                    "//span[contains(normalize-space(text()),'Last 24')]",
                    "//*[contains(normalize-space(text()),'Past 24')]",
                    "//*[contains(normalize-space(text()),'24 Hours')]",
                    # Ant Design specific
                    "//label[contains(@class,'ant-radio-wrapper') and .//span[contains(text(),'24')]]",
                    "//div[contains(@class,'ant-radio-group')]//label[1]",
                ]
                clicked_radio = False
                for xpath in radio_xpaths:
                    try:
                        radio = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, xpath))
                        )
                        radio.click()
                        time.sleep(2)  # let results re-render
                        clicked_radio = True
                        print(f"  [DateFilter] Applied 24 h filter via: {xpath[:60]}")
                        break
                    except Exception:
                        continue

                if clicked_radio:
                    return True

                print(f"  [DateFilter] Radio not found (attempt {attempt}/{MAX_ATTEMPTS})")
                # Close the dropdown before retrying
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys("\x1b")
                    time.sleep(1)
                except Exception:
                    pass

            except Exception as e:
                print(f"  [DateFilter] Error on attempt {attempt}: {e}")

        print("  [DateFilter] All attempts failed — continuing without date filter")
        return False

    # ── Timing helpers ────────────────────────────────────────────────────────

    def _random_human_pause(
        self,
        label: str | None = None,
        lo: float | None = None,
        hi: float | None = None,
    ) -> float:
        lo = self._random_pause_lo if lo is None else float(lo)
        hi = self._random_pause_hi if hi is None else float(hi)
        if hi < lo:
            lo, hi = hi, lo
        sec = random.uniform(lo, hi)
        tag = f" ({label})" if label else ""
        logger.info(f"⏳ Human pause{tag}: {sec:.1f}s")
        time.sleep(sec)
        return sec

    def _random_scroll_step_pause(self) -> float:
        lo, hi = self._scroll_step_lo, self._scroll_step_hi
        if hi < lo:
            lo, hi = hi, lo
        sec = random.uniform(lo, hi)
        time.sleep(sec)
        return sec

    def _scroll_to_bottom(self):
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.8)

    def _random_mouse_jitter(self):
        """Simulate small random mouse movement via JS."""
        try:
            x = random.randint(100, 1200)
            y = random.randint(100, 600)
            self.driver.execute_script(
                f"document.elementFromPoint({x},{y})?.dispatchEvent(new MouseEvent('mousemove',{{bubbles:true}}))"
            )
        except Exception:
            pass

    # ── Session health ─────────────────────────────────────────────────────────

    def _is_session_alive(self) -> bool:
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    # ── Blocked-page detection ─────────────────────────────────────────────────

    def _is_page_blocked(self) -> bool:
        """
        Detect Jobright's empty/error shell.
        Fingerprint: tiny page source + very few DOM elements.
        """
        try:
            src = self.driver.page_source
            src_len = len(src)
            if src_len in BLOCKED_PAGE_SIZES:
                print(f"⚠️  Blocked page detected: source length {src_len}")
                return True
            try:
                div_count  = len(self.driver.find_elements(By.CSS_SELECTOR, "div"))
                link_count = len(self.driver.find_elements(By.CSS_SELECTOR, "a"))
                if div_count in BLOCKED_DIV_COUNT and link_count <= BLOCKED_LINK_COUNT:
                    print(f"⚠️  Blocked page detected: divs={div_count}, links={link_count}")
                    return True
            except Exception:
                pass
        except Exception as e:
            print(f"[DEBUG] Error checking blocked page: {e}")
        return False

    # ── Wait for jobs to load ──────────────────────────────────────────────────

    def _wait_for_jobs_to_load(self, timeout: int = 20) -> bool:
        current_url = self.driver.current_url
        if "jobright.ai" not in current_url.lower():
            print(f"⚠️  Browser not on jobright.ai (at: {current_url})")
            return False
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, JOB_LINK_SELECTOR))
            )
            print("✅ Job content detected on page")
            return True
        except TimeoutException:
            print("⏰ Timed out waiting for job links")
            return False

    # ── Job link helpers ───────────────────────────────────────────────────────

    def _get_viewjob_links(self):
        try:
            links = self.driver.find_elements(By.CSS_SELECTOR, JOB_LINK_SELECTOR)
            return [el for el in links if el.is_displayed()]
        except Exception as e:
            print(f"[WARN] Error finding job links: {e}")
            return []

    def _get_unique_job_ids(self) -> set[str]:
        ids = set()
        for link in self._get_viewjob_links():
            href = link.get_attribute("href") or ""
            jid = _job_id_from_href(href)
            if jid:
                ids.add(jid)
        return ids

    def _get_current_job_count(self) -> int:
        return len(self._get_unique_job_ids())

    # ── Infinite scroll ────────────────────────────────────────────────────────

    def _scroll_until_end(self, max_scrolls: int = 300) -> bool:
        """
        Scroll the inner job-list container on Jobright (#jobs-page-main-content).
        Jobright uses a fixed-height scrollable div — scrolling window.body does nothing.
        """
        print(
            f"🔄 Starting infinite scroll "
            f"(step delay {self._scroll_step_lo}–{self._scroll_step_hi}s)..."
        )
        previous_count = 0
        no_change_count = 0
        scroll_attempts = 0

        # Find the scrollable job-list container (Jobright's inner panel)
        SCROLL_CONTAINER_SELECTORS = [
            "#jobs-page-main-content",
            "[class*='jobs-page-main-content']",
            "[class*='job-list-container']",
            "[class*='jobList']",
            "[class*='list-container']",
        ]

        def _get_scroll_container():
            for sel in SCROLL_CONTAINER_SELECTORS:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        return els[0]
                except Exception:
                    continue
            return None  # fallback: page body

        while scroll_attempts < max_scrolls:
            if not self._is_session_alive():
                print("⚠️  Chrome session died during scroll — stopping.")
                return False

            current_count = self._get_current_job_count()
            print(f"📊 Jobs loaded: {current_count} (scroll {scroll_attempts + 1}/{max_scrolls})")

            if current_count == previous_count:
                no_change_count += 1
                if no_change_count >= 5:   # increased from 3 to 5 for reliability
                    print(f"✅ No new jobs after {no_change_count} scrolls — reached end.")
                    return True
            else:
                no_change_count = 0

            previous_count = current_count

            try:
                container = _get_scroll_container()
                if container:
                    # Scroll the inner container
                    scroll_amt = random.randint(1000, 1400)
                    self.driver.execute_script(
                        f"arguments[0].scrollTop += {scroll_amt};", container
                    )
                else:
                    # Fallback: scroll the window
                    self._scroll_to_bottom()

                # Add a small human-like pause after scrolling
                time.sleep(random.uniform(0.5, 1.2))
                self._random_scroll_step_pause()

            except Exception as e:
                print(f"⚠️  Scroll error (attempt {scroll_attempts+1}): {e}")
                if not self._is_session_alive():
                    return False
                break

            scroll_attempts += 1
            time.sleep(random.uniform(0.5, 1.0))

        print(f"⚠️  Reached max scroll attempts ({max_scrolls}).")
        return False

    # ── Job card parsing ───────────────────────────────────────────────────────

    def _parse_jobright_card_text(self, text: str) -> dict:
        """
        Parse raw text from a Jobright job card into granular fields.

        Handles noise like "Be an early applicant", "ASK ORION", etc.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        data = {
            "title": None,
            "company": None,
            "location": None,
            "city": None,
            "state": None,
            "job_type": None,
            "work_mode": None,
            "seniority": None,
            "salary": None,
            "posted_ago": None,
        }
        if not lines:
            return data

        _time_re   = re.compile(r'^\d+\s+\w+\s+ago$|^·\s*\d+|^just\s+now', re.I)
        _salary_re = re.compile(
            r'\$[\d,]+[kK]?(?:/\w+)?|\$[\d,]+[kK]?[-–]\$?[\d,]+[kK]?|[\d,]+[kK]/(?:yr|mo|year|hr)',
            re.I,
        )
        _mode_set  = {'remote', 'hybrid', 'on-site', 'onsite', 'in-person'}
        _type_set  = {'full-time', 'full time', 'part-time', 'part time',
                      'contract', 'internship', 'temporary', 'freelance'}
        _seniority_kw = ('entry', 'junior', 'mid', 'senior', 'lead', 'staff',
                         'principal', 'director', 'manager', 'associate', 'intern')

        # Phrases that are definitely NOT company or title
        _junk_phrases = {
            "be an early applicant", "ask orion", "apply now", "match score",
            "applicants", "sponsor", "exp", "months ago", "days ago", "hours ago",
            "minutes ago", "growth opportunities", "no h1b", "h1b sponsor"
        }

        def _is_salary(s):
            return bool(_salary_re.search(s))

        def _is_location(s):
            return ',' in s or re.search(
                r'\b(united states|usa|canada|uk|remote|new york|san francisco|'
                r'boston|seattle|austin|chicago|dallas|denver|atlanta|'
                r'los angeles|washington|virginia|maryland|texas|california)\b',
                s, re.I
            )

        def _is_time(s):
            return bool(_time_re.search(s)) or s.startswith('·')

        def _is_junk(s):
            sl = s.lower()
            return any(p in sl for p in _junk_phrases) or sl == "/"

        title_set = False
        for line in lines:
            if not line or _is_junk(line):
                continue

            ll = line.lower().strip('·· ').strip()

            if _is_time(line):
                if not data['posted_ago']:
                    data['posted_ago'] = line.strip('·· ').strip()
                continue

            if _is_salary(line):
                data['salary'] = line
                continue

            if ll in _mode_set:
                data['work_mode'] = line
                continue

            if ll in _type_set:
                data['job_type'] = line
                continue

            if any(kw in ll for kw in _seniority_kw) and len(line.split()) <= 6:
                if data.get('title'):   # seniority usually comes after title
                    data['seniority'] = line
                    continue

            # First non-junk line after time is usually Title
            if not title_set:
                data['title'] = line
                title_set = True
                continue

            # Next non-junk line is usually Company
            if not data['company']:
                # Clean up company name (remove common suffixes like staffing info)
                data['company'] = line.split('·')[0].strip()
                continue

            if not data['location'] and _is_location(line):
                data['location'] = line
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 2:
                    data['city']  = parts[0]
                    data['state'] = parts[1]
                continue

        return data

    # ── Phase 1 — Extract job listings from listing page ──────────────────────

    def _extract_job_listings(self) -> list[dict]:
        jobs = []
        print("🔍 Extracting job listings from page...")
        try:
            seen_ids = set()
            for link in self._get_viewjob_links():
                try:
                    href = link.get_attribute("href") or ""
                    jid = _job_id_from_href(href)
                    if not jid:
                        # Fallback: check element ID (observed in <a> cards)
                        jid = link.get_attribute("id")

                    if not jid or jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    url = (
                        href if href.startswith("http")
                        else (self.base_url + (href if href.startswith("/") else "/" + href))
                    )

                    enriched = {}
                    try:
                        # Try current link text first (if <a> is the card container)
                        raw = (link.text or "").strip()
                        if raw and len(raw) > 30:
                            enriched = self._parse_jobright_card_text(raw)

                        if not enriched.get("title"):
                            # Walk up max 3 ancestors to find the card container if needed
                            parent = link
                            for _ in range(3):
                                parent = parent.find_element(By.XPATH, "..")
                                raw = (parent.text or "").strip()
                                if raw and len(raw) > 30:
                                    enriched = self._parse_jobright_card_text(raw)
                                    break
                    except Exception:
                        pass

                    job_data = {
                        "job_id":       jid,
                        "external_id":  jid,
                        "title":        enriched.get("title") or f"Job {jid}",
                        "company":      enriched.get("company"),
                        "location":     enriched.get("location"),
                        "city":         enriched.get("city"),
                        "state":        enriched.get("state"),
                        "job_type":     enriched.get("job_type"),
                        "work_mode":    enriched.get("work_mode"),
                        "seniority":    enriched.get("seniority"),
                        "salary":       enriched.get("salary"),
                        "posted_ago":   enriched.get("posted_ago"),
                        "url":          url,
                        "jobright_url": url,
                        "scraped_at":   datetime.now().isoformat(),
                    }
                    jobs.append(job_data)

                except Exception as e:
                    print(f"[WARN] Error extracting card: {e}")
                    continue

            print(f"✅ Extracted {len(jobs)} unique job listings")
            return jobs

        except Exception as e:
            print(f"❌ Error extracting job listings: {e}")
            import traceback; traceback.print_exc()
            return []

    # ── Phase 2 — ATS URL extraction (6 layers, mirrors Hiring Cafe) ──────────

    def _extract_ats_urls_from_page_source(self) -> list[str]:
        """Scan raw page HTML/JS for ATS URLs (3 passes: direct, unicode-decoded, __NEXT_DATA__)."""
        try:
            source = self.driver.page_source
            candidates = set()

            # Pass 1: direct regex
            for url in ATS_URL_REGEX.findall(source):
                url_clean = url.strip().rstrip('"\'\\ ')
                if "jobright.ai" not in url_clean.lower():
                    candidates.add(url_clean)

            # Pass 2: unicode-decoded
            try:
                decoded = source.encode('utf-8').decode('unicode_escape', errors='replace')
                for url in ATS_URL_REGEX.findall(decoded):
                    url_clean = url.strip().rstrip('"\'\\ ')
                    if "jobright.ai" not in url_clean.lower():
                        candidates.add(url_clean)
            except Exception:
                pass

            # Pass 3: __NEXT_DATA__ JSON blob
            try:
                next_match = re.search(
                    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                    source, re.DOTALL | re.IGNORECASE
                )
                if next_match:
                    blob = next_match.group(1).strip()

                    def _find_urls(obj):
                        if isinstance(obj, str):
                            if obj.startswith('http') and is_likely_ats_url(obj):
                                candidates.add(obj)
                        elif isinstance(obj, dict):
                            for v in obj.values():
                                _find_urls(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                _find_urls(item)

                    try:
                        data = json.loads(blob)
                        _find_urls(data)
                    except Exception:
                        for url in ATS_URL_REGEX.findall(blob):
                            url_clean = url.strip().rstrip('"\'\\ ')
                            if "jobright.ai" not in url_clean.lower():
                                candidates.add(url_clean)
            except Exception:
                pass

            return list(candidates)

        except Exception as e:
            print(f"[DEBUG] Page source ATS scan failed: {e}")
            return []

    def _find_apply_button(self):
        """Find Apply button: primary XPath → fallbacks → scroll + retry."""
        try:
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)
        except Exception:
            pass

        try:
            btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, APPLY_NOW_BUTTON_XPATH))
            )
            return btn
        except (TimeoutException, NoSuchElementException):
            pass

        for xpath in APPLY_BUTTON_FALLBACK_XPATHS:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                print(f"[INFO] Apply button via fallback: {xpath[:60]}")
                return btn
            except (TimeoutException, NoSuchElementException):
                continue

        # Last resort: scroll to bottom
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            btns = self.driver.find_elements(By.XPATH, APPLY_NOW_BUTTON_XPATH)
            if btns:
                return btns[0]
        except Exception:
            pass

        return None

    def _try_get_ats_url_from_dom(self) -> str | None:
        """
        Layers 1+2: DOM walk + page-source regex (no clicking).
        Mirrors HiringCafeStrategy._try_get_ats_url_from_dom exactly.
        """
        def accept_url(href: str) -> bool:
            return (
                bool(href)
                and href.strip().startswith("http")
                and "jobright.ai" not in href.lower()
                and is_likely_ats_url(href)
            )

        try:
            # Pass 0: check "Original Job Post" link (most reliable on Jobright)
            try:
                origin_links = self.driver.find_elements(By.XPATH, ORIGINAL_JOB_POST_LINK_XPATH)
                if origin_links:
                    href = origin_links[0].get_attribute("href")
                    if accept_url(href):
                        return href.strip()
            except Exception:
                pass

            buttons = self.driver.find_elements(By.XPATH, APPLY_NOW_BUTTON_XPATH)

            if buttons:
                btn = buttons[0]

                # Step 1: button IS an <a>
                if btn.tag_name.lower() == "a":
                    href = btn.get_attribute("href")
                    if accept_url(href):
                        return href.strip()

                # Step 2: ancestor <a>
                try:
                    parent = btn
                    for _ in range(10):
                        parent = parent.find_element(By.XPATH, "..")
                        if parent.tag_name.lower() == "a":
                            href = parent.get_attribute("href")
                            if accept_url(href):
                                return href.strip()
                            break
                        if parent.tag_name.lower() == "body":
                            break
                except Exception:
                    pass

                # Step 3: sibling <a>
                try:
                    container = btn.find_element(By.XPATH, "..")
                    for a in container.find_elements(By.TAG_NAME, "a"):
                        href = a.get_attribute("href")
                        if accept_url(href):
                            return href.strip()
                except Exception:
                    pass

                # Step 4: walk up 8 levels
                try:
                    root = btn
                    for _ in range(8):
                        root = root.find_element(By.XPATH, "..")
                        for a in root.find_elements(By.CSS_SELECTOR, 'a[href^="http"]'):
                            href = a.get_attribute("href")
                            if not accept_url(href):
                                continue
                            target = (a.get_attribute("target") or "").lower()
                            rel    = (a.get_attribute("rel") or "").lower()
                            text   = (a.text or "").lower()
                            if "apply" in text or target == "_blank" or "noopener" in rel:
                                return href.strip()
                except Exception:
                    pass

            # Step 5: page-wide known ATS <a>
            try:
                for a in self.driver.find_elements(By.CSS_SELECTOR, 'a[href^="http"]'):
                    href = a.get_attribute("href") or ""
                    if accept_url(href) and detect_ats_platform(href):
                        return href.strip()
            except Exception:
                pass

            # Step 6: regex on raw page source
            candidates = self._extract_ats_urls_from_page_source()
            if candidates:
                return candidates[0]

            return None

        except Exception as e:
            print(f"[DEBUG] DOM ATS extraction failed: {e}")
            return None

    def _get_ats_link_from_job_page(self, job_id: str) -> dict | None:
        """
        Full 6-layer ATS extraction for one job.
        Mirrors HiringCafeStrategy._get_ats_link_from_job_page.

        Layer 1+2 : DOM walk + page-source regex (no click)
        Layer 3   : Find Apply button → click → new tab
        Layer 4   : Same-tab redirect
        Layer 5   : Page-source regex after click
        Layer 6   : __NEXT_DATA__ JSON parse (inside _extract_ats_urls_from_page_source)
        """
        job_url = f"{self.base_url}/jobs/info/{job_id}"
        try:
            self.driver.get(job_url)
            p_lo, p_hi = self._step2_page_lo, self._step2_page_hi
            if p_hi < p_lo:
                p_lo, p_hi = p_hi, p_lo
            time.sleep(random.uniform(p_lo, p_hi))

            if self._step2_mouse_jitter:
                self._random_mouse_jitter()

            main_handle = self.driver.current_window_handle

            # ── Layers 1+2: DOM + page source ────────────────────────────────
            ats_url = self._try_get_ats_url_from_dom()
            if ats_url and is_likely_ats_url(ats_url):
                platform = detect_ats_platform(ats_url) or "unknown"
                print(f"[DOM] {job_url} -> {ats_url}")
                return {"ats_url": ats_url, "ats_platform": platform}

            # ── Layer 3: Click Apply button → new tab ─────────────────────────
            btn = self._find_apply_button()

            if btn:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", btn
                    )
                    time.sleep(0.5)
                except Exception:
                    pass

                clicked = False
                try:
                    btn.click()
                    clicked = True
                except Exception:
                    try:
                        self.driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                    except Exception as e:
                        print(f"[WARN] Click failed for {job_id}: {e}")

                if clicked:
                    # Jobright specific: handle "Customize Your Resume" modal
                    try:
                        # Check for "Apply without Customizing" button
                        no_customize_xpath = """
                            //button[contains(@class, 'index_cancelButton')]
                            | //button[.//p[contains(text(), 'Apply without Customizing')]]
                            | //button[contains(., 'Apply without Customizing')]
                        """
                        no_customize = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, no_customize_xpath))
                        )
                        print("[INFO] Clicking 'Apply without Customizing' modal button...")
                        no_customize.click()
                    except Exception:
                        pass

                    # Wait up to 5s for new tab
                    new_handles = []
                    for _ in range(5):
                        time.sleep(1)
                        handles = self.driver.window_handles
                        new_handles = [h for h in handles if h != main_handle]
                        if new_handles:
                            break

                    if new_handles:
                        # ── Layer 3a: New tab ─────────────────────────────────
                        try:
                            self.driver.switch_to.window(new_handles[0])
                            time.sleep(2)
                            try:
                                ats_url = self.driver.current_url
                            except Exception:
                                ats_url = None
                                try:
                                    self.driver.switch_to.window(main_handle)
                                except Exception:
                                    pass

                            if new_handles[0] in self.driver.window_handles:
                                try:
                                    self.driver.close()
                                except Exception:
                                    pass

                            try:
                                self.driver.switch_to.window(main_handle)
                            except Exception:
                                pass

                        except Exception as tab_err:
                            print(f"[DEBUG] Tab error: {tab_err}")
                            ats_url = None
                            try:
                                self.driver.switch_to.window(self.driver.window_handles[0])
                            except Exception:
                                pass

                        if ats_url and is_likely_ats_url(ats_url):
                            platform = detect_ats_platform(ats_url) or "unknown"
                            print(f"[NewTab] {job_url} -> {ats_url}")
                            return {"ats_url": ats_url, "ats_platform": platform}

                    else:
                        # ── Layer 4: Same-tab redirect ────────────────────────
                        time.sleep(1)
                        current = self.driver.current_url
                        if "jobright.ai" not in current.lower() and is_likely_ats_url(current):
                            platform = detect_ats_platform(current) or "unknown"
                            print(f"[SameTab] {job_url} -> {current}")
                            return {"ats_url": current, "ats_platform": platform}

                        # ── Layer 5: Page source after click ──────────────────
                        time.sleep(2)
                        candidates = self._extract_ats_urls_from_page_source()
                        if candidates:
                            ats_url = candidates[0]
                            platform = detect_ats_platform(ats_url) or "unknown"
                            print(f"[PostClick/Regex] {job_url} -> {ats_url}")
                            return {"ats_url": ats_url, "ats_platform": platform}
            else:
                print(f"[WARN] Apply button not found for {job_id}")

            print(f"[Failed] {job_url} -> ats_url: null")
            return None

        except Exception as e:
            print(f"[WARN] Error getting ATS link for {job_id}: {e}")
            try:
                if len(self.driver.window_handles) > 1:
                    self.driver.switch_to.window(self.driver.window_handles[0])
            except Exception:
                pass
            return None

    # ── Phase 1 driver ─────────────────────────────────────────────────────────

    def find_jobs_for_keyword(self, keyword: str, max_retries: int = 5) -> list[dict]:
        search_url = _build_search_url_with_location(keyword, self._location, self.base_url)

        # Pre-warm
        try:
            print("  Pre-warming via homepage...")
            self.driver.get(self.base_url)
            time.sleep(2)
            self._random_human_pause("homepage read")
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"  [WARN] Pre-warm failed: {e}")

        for attempt in range(1, max_retries + 1):
            try:
                print(f"\n  Keyword '{keyword}' (attempt {attempt}/{max_retries})")
                print(f"  URL: {search_url}")

                if attempt > 1:
                    self.driver.get(self.base_url)
                    time.sleep(2)
                    self._random_human_pause("retry homepage")

                self.driver.get(search_url)
                time.sleep(2)
                self._random_human_pause("search results load")

                actual_url = self.driver.current_url
                if "jobright.ai" not in actual_url.lower():
                    print(f"  Landed on wrong page: {actual_url}")
                    if attempt < max_retries:
                        time.sleep(5)
                        continue
                    return []

                if self._is_page_blocked():
                    print(f"  Blocked page (attempt {attempt})")
                    if attempt < max_retries:
                        cooldown = 20 + (attempt * 15)
                        print(f"  Cooling down {cooldown}s...")
                        time.sleep(cooldown)
                        continue
                    return []

                jobs_loaded = self._wait_for_jobs_to_load(timeout=20)
                if not jobs_loaded:
                    print(f"  No job links appeared for '{keyword}'")
                    if attempt < max_retries:
                        time.sleep(10)
                        continue
                    return []

                # ── FIX: Apply date filter BEFORE scrolling ──────────────────
                filter_ok = self._apply_date_filter()
                if not filter_ok:
                    print("  [WARN] Date filter not applied — results may include older jobs")
                # Wait for page to re-render after filter
                time.sleep(3)

                # ── Scroll now (on filtered results) ─────────────────────────
                self._scroll_until_end(max_scrolls=300)

                jobs = self._extract_job_listings()

                # ── FIX: Apply keyword title filter AFTER extraction ─────────
                before = len(jobs)
                jobs = [j for j in jobs if self._matches_keyword_filter(j, keyword)]
                after = len(jobs)
                if before != after:
                    print(f"  Title filter removed {before - after} off-topic jobs "
                          f"({after}/{before} kept)")

                # ── FIX: Warn if country filter looks wrong ───────────────────
                us_terms = ("united states", "usa", ", ca", ", ny", ", tx",
                            ", wa", ", fl", ", il", "remote")
                us_hits = sum(
                    1 for j in jobs
                    if any(t in (j.get("location") or "").lower() for t in us_terms)
                )
                if jobs and us_hits < len(jobs) * 0.5:
                    print(f"  [WARN] Only {us_hits}/{len(jobs)} jobs have US location strings "
                          f"— country filter may not have applied")

                print(f"  Keyword '{keyword}': {len(jobs)} jobs after all filters")
                return jobs

            except Exception as e:
                print(f"  Error for '{keyword}' (attempt {attempt}): {e}")
                if not self._is_session_alive():
                    return []
                if attempt < max_retries:
                    time.sleep(10)

        return []

    def find_jobs(self) -> list[dict]:
        """
        Collect jobs for all configured keywords.
        Title filter is now applied per-keyword inside find_jobs_for_keyword().
        """
        if len(self._search_keywords) == 1:
            kw   = self._search_keywords[0]
            jobs = self.find_jobs_for_keyword(kw)
            for j in jobs:
                j["source_keywords"] = [kw]
            return jobs

        keyword_job_lists = []
        for i, keyword in enumerate(self._search_keywords):
            jobs = self.find_jobs_for_keyword(keyword)
            for j in jobs:
                j["source_keywords"] = [keyword]
            keyword_job_lists.append((keyword, jobs))
            if i < len(self._search_keywords) - 1:
                self._random_human_pause("next keyword")

        merged = self._merge_jobs_unique(keyword_job_lists)
        print(f"\n  Unique jobs across all keywords: {len(merged)}")
        return merged

    # ── Keyword filter (boolean, mirrors Hiring Cafe) ─────────────────────────

    @staticmethod
    def _matches_keyword_filter(job: dict, keyword: str) -> bool:
        """
        Job title must contain at least ONE meaningful term from the keyword.
        """
        title_text = (job.get("title") or "").lower().strip()
        if not title_text:
            return True

        ABBREV_MAP = {
            "ml": ["machine learning", "ml"],
            "ai": ["artificial intelligence", "ai"],
            "ds": ["data science", "data scientist", "ds"],
        }

        kw_upper = keyword.upper()
        not_terms: list[str] = []
        and_part = keyword

        if " NOT " in kw_upper:
            not_idx    = kw_upper.index(" NOT ")
            not_clause = keyword[not_idx + 5:].strip()
            and_part   = keyword[:not_idx].strip()
            not_terms  = [t.strip() for t in re.split(r'\b(?:AND|\+)\b', not_clause, flags=re.IGNORECASE) if t.strip()]

        # Build term list: full phrase + individual words
        terms_to_check: list[str] = []
        kw_lower = and_part.strip().lower()

        # Add full keyword phrase
        terms_to_check.append(kw_lower)

        # Add individual words (skip stop words)
        STOP = {"and", "or", "the", "a", "an", "of", "for", "in", "at", "to", "with"}
        words = [w for w in re.split(r'\s+', kw_lower) if w and w not in STOP]
        terms_to_check.extend(words)

        # Add abbreviation expansions
        for word in words:
            if word in ABBREV_MAP:
                terms_to_check.extend(ABBREV_MAP[word])

        def _present(term: str, text: str) -> bool:
            """Word-boundary match, case-insensitive."""
            escaped = re.escape(term)
            return bool(re.search(r'(?<![a-z0-9])' + escaped + r'(?![a-z0-9])', text, re.IGNORECASE))

        # At least ONE term must match
        if not any(_present(term, title_text) for term in terms_to_check):
            return False

        # No NOT terms allowed
        for term in not_terms:
            if _present(term, title_text):
                return False

        return True

    def _merge_jobs_unique(
        self, keyword_job_lists: list[tuple[str, list[dict]]]
    ) -> list[dict]:
        by_id = {}
        for keyword, lst in keyword_job_lists:
            for j in lst:
                jid = j.get("job_id") or j.get("external_id")
                if not jid:
                    continue
                if jid not in by_id:
                    by_id[jid] = {**j, "source_keywords": [keyword]}
                else:
                    if keyword not in by_id[jid].get("source_keywords", []):
                        by_id[jid].setdefault("source_keywords", []).append(keyword)
        return list(by_id.values())

    def find_jobs(self) -> list[dict]:
        """
        Collect jobs for all configured keywords.
        Title filter is intentionally SKIPPED — we are already on the
        keyword-specific search page so all results are relevant.
        """
        if len(self._search_keywords) == 1:
            kw   = self._search_keywords[0]
            jobs = self.find_jobs_for_keyword(kw)
            for j in jobs:
                j["source_keywords"] = [kw]
            return jobs

        keyword_job_lists = []
        for i, keyword in enumerate(self._search_keywords):
            jobs = self.find_jobs_for_keyword(keyword)
            for j in jobs:
                j["source_keywords"] = [keyword]
            keyword_job_lists.append((keyword, jobs))
            if i < len(self._search_keywords) - 1:
                self._random_human_pause("next keyword")

        merged = self._merge_jobs_unique(keyword_job_lists)
        print(f"✅ Unique jobs across all keywords: {len(merged)}")
        return merged

    # ── Phase 2 driver ─────────────────────────────────────────────────────────

    def enrich_jobs_with_ats_links(
        self,
        jobs: list[dict],
        limit: int | None = None,
        output_file: str | None = None,
    ) -> list[dict]:
        """
        Enrich jobs with ATS URLs.
        Checkpoint/resume: jobs already having 'ats_url' key are skipped.
        Mirrors HiringCafeStrategy.enrich_jobs_with_ats_links exactly.
        """
        to_process = jobs[:limit] if limit is not None else jobs
        consecutive_failures = 0

        already_done = sum(1 for j in to_process if "ats_url" in j)
        remaining    = len(to_process) - already_done
        if already_done:
            print(f"⏭️  Resuming: {already_done}/{len(to_process)} already done, skipping...")
        print(f"🔗 Step 2: Extracting ATS URLs for {remaining} jobs...")

        pending = [j for j in to_process if "ats_url" not in j]
        if self._step2_shuffle and len(pending) > 1:
            random.shuffle(pending)
            print(f"🔀 Shuffled {len(pending)} pending jobs")

        for step_idx, job in enumerate(pending, start=1):
            jid = job.get("job_id") or job.get("external_id")
            if not jid:
                job.setdefault("ats_url", None)
                job.setdefault("ats_platform", None)
                continue

            jobright_url = job.get("jobright_url") or job.get("url") or \
                           f"{self.base_url}/jobs/info/{jid}"
            print(f"🔍 Enriching {step_idx}/{len(pending)}: {jid}")

            if not self._is_session_alive():
                print("⚠️  Chrome session died — cannot continue enrichment.")
                if output_file:
                    self._write_jobs_payload(output_file, jobs)
                break

            ats = self._get_ats_link_from_job_page(jid)

            if ats:
                job["ats_url"]      = ats["ats_url"]
                job["ats_platform"] = ats["ats_platform"]
                print(f"  ✓ {jobright_url} -> {ats['ats_url']}")
                consecutive_failures = 0
            else:
                job["ats_url"]      = None
                job["ats_platform"] = None
                print(f"  ✗ {jobright_url} -> null")
                consecutive_failures += 1

            # Checkpoint after every job
            if output_file:
                try:
                    self._write_jobs_payload(output_file, jobs)
                except Exception as save_err:
                    print(f"[WARN] Checkpoint save failed: {save_err}")

            # Rate-limit protection
            if consecutive_failures == 3:
                print("⚠️  3 consecutive failures — cooling down 20s...")
                time.sleep(20)
                time.sleep(random.uniform(3, 6))
            elif consecutive_failures >= 5:
                print(f"⚠️  {consecutive_failures} failures — 40s cooldown + homepage reset...")
                try:
                    self.driver.get(self.base_url)
                    time.sleep(8)
                    time.sleep(random.uniform(4, 10))
                except Exception:
                    pass
                time.sleep(40)
                consecutive_failures = 0
            elif (
                self._step2_break_every > 0
                and step_idx % self._step2_break_every == 0
            ):
                self._random_human_pause(
                    "step2 micro-break",
                    self._step2_long_break_lo,
                    self._step2_long_break_hi,
                )
            else:
                self._random_human_pause(
                    "between ATS jobs",
                    self._step2_pause_lo,
                    self._step2_pause_hi,
                )

        if limit is not None:
            for j in jobs[limit:]:
                j.setdefault("ats_url", None)
                j.setdefault("ats_platform", None)

        return jobs

    # ── Output ─────────────────────────────────────────────────────────────────

    def _write_jobs_payload(self, output_file: str, jobs: list) -> None:
        """
        Save jobs to file in FLAT format (mirrors HiringCafeStrategy._write_jobs_payload).
        Atomic write via .tmp then os.replace.
        """
        if not jobs:
            return
        try:
            tmp = output_file + ".tmp"
            payload = {
                "source":  "jobright.ai",
                "step":    2,
                "updated": datetime.now().isoformat(),
                "count":   len(jobs),
                "jobs": [
                    {
                        "job_id":       j.get("job_id"),
                        "title":        j.get("title"),
                        "company":      j.get("company"),
                        "location":     j.get("location"),
                        "city":         j.get("city"),
                        "state":        j.get("state"),
                        "job_type":     j.get("job_type"),
                        "work_mode":    j.get("work_mode"),
                        "seniority":    j.get("seniority"),
                        "salary":       j.get("salary"),
                        "posted_ago":   j.get("posted_ago"),
                        "jobright_url": j.get("jobright_url") or j.get("url"),
                        "ats_url":      j.get("ats_url"),
                        "ats_platform": j.get("ats_platform"),
                        "source_keywords": j.get("source_keywords"),
                        "scraped_at":   j.get("scraped_at"),
                    }
                    for j in jobs
                ],
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            import os as _os
            _os.replace(tmp, output_file)
            print(f"💾 Saved {len(jobs)} jobs -> {output_file}")
        except Exception as e:
            print(f"❌ Error saving to file: {e}")

    # ── Main entry ─────────────────────────────────────────────────────────────

    def scrape_and_save(
        self,
        output_file: str | None = None,
        enrich_ats: bool = False,
        enrich_ats_limit: int | None = None,
        job_limit: int | None = None,
    ) -> list[dict]:
        """
        Full pipeline:
          Phase 1 — Scroll + collect job listings
          Phase 2 — Enrich with ATS URLs (if enrich_ats=True)
        Mirrors HiringCafeStrategy.scrape_and_save.
        """
        if output_file is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"jobright_jobs_{ts}.json"

        print("🚀 Phase 1: Scroll per keyword, collect unique jobs...")
        if job_limit:
            print(f"🧪 Test mode: limiting to {job_limit} jobs")

        # Login before starting Phase 1
        if self._credentials and not self._is_logged_in:
            self.login()

        jobs = self.find_jobs()

        if job_limit and jobs:
            jobs = jobs[:job_limit]
            print(f"📋 Using first {len(jobs)} jobs (test limit) from new scrape")

        # Merge with existing file if it exists
        if output_file and os.path.exists(output_file):
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_jobs = existing_data.get("jobs", [])
                    
                existing_ids = {j.get("job_id") for j in existing_jobs if j.get("job_id")}
                new_jobs = [j for j in jobs if j.get("job_id") not in existing_ids]
                
                print(f"📥 Loaded {len(existing_jobs)} existing jobs. Found {len(new_jobs)} new jobs.")
                jobs = existing_jobs + new_jobs
            except Exception as e:
                print(f"⚠️ Could not read existing jobs from {output_file}: {e}")

        self._write_jobs_payload(output_file, jobs)

        if enrich_ats and jobs:
            print("🔗 Phase 2: Enrich jobs with ATS URLs...")
            try:
                self.enrich_jobs_with_ats_links(
                    jobs,
                    limit=enrich_ats_limit,
                    output_file=output_file,
                )
                self._write_jobs_payload(output_file, jobs)
            except BaseException:
                print("⚠️  Enrichment interrupted; current state saved.")
                self._write_jobs_payload(output_file, jobs)
                raise

        if not jobs:
            print("⚠️  No jobs found.")
        return jobs
