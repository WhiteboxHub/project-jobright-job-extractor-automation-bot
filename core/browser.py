import os
import sys
import time
try:
    import fcntl
    _HAS_FCNTL = True
except Exception:
    _HAS_FCNTL = False

uc = None
from config.settings import settings
from core.logger import logger
from core.proxy_manager import proxy_manager

_LAUNCHED_BY_SCHEDULER = os.environ.get("SCHEDULER_LAUNCHED", "0") == "1"


def _get_chrome_version():
    """Retrieves the installed Chrome version on Windows or Linux."""
    if sys.platform == "win32":
        import winreg
        paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon", "version"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
        ]
        for root, path, value_name in paths:
            try:
                key = winreg.OpenKey(root, path)
                version, _ = winreg.QueryValueEx(key, value_name)
                major_version = int(version.split('.')[0])
                logger.info(f"Detected Chrome version: {major_version} (from {path})")
                return major_version
            except Exception:
                continue
    
    try:
        import subprocess
        output = subprocess.check_output(["google-chrome", "--version"], stderr=subprocess.STDOUT).decode()
        major_version = int(output.split()[2].split('.')[0])
        return major_version
    except Exception:
        pass

    logger.warning("Could not detect Chrome version dynamically; using default 146.")
    return 146


class BrowserService:
    def __init__(self):
        self.driver = None
        self.lock_file = None

    def _acquire_lock(self):
        """Ensures only one instance touches the profile. fcntl not available on Windows."""
        profile_path = settings.chrome_profile_path
        os.makedirs(profile_path, exist_ok=True)
        lock_path = os.path.join(profile_path, "profile.lock")

        self.lock_file = None
        if not _HAS_FCNTL:
            logger.info("fcntl not available on this platform; skipping profile locking.")
            return

        self.lock_file = open(lock_path, 'w')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.info(f"Acquired lock on profile: {profile_path}")
        except IOError:
            logger.critical(f"Could not acquire lock on {lock_path}. Is another instance running?")
            raise RuntimeError("Browser profile is locked by another process.")

    def _release_lock(self):
        if not _HAS_FCNTL:
            return
        if self.lock_file:
            try:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
            except Exception:
                pass
            self.lock_file.close()
            logger.info("Released profile lock.")

    def _apply_scheduler_flags(self, options) -> None:
        flags = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-service-autorun",
            "--password-store=basic",
            "--lang=en-US",
            "--accept-lang=en-US",
        ]

        if sys.platform != "win32":
            flags += [
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
            ]

        for f in flags:
            options.add_argument(f)

        if settings.HEADLESS:
            options.add_argument("--window-size=1920,1080")
        else:
            options.add_argument("--start-maximized")

        if _LAUNCHED_BY_SCHEDULER:
            logger.info("Scheduler-mode: applied anti-detection Chrome flags.")

    @staticmethod
    def _force_kill_chrome():
        """Kill all running Chrome and ChromeDriver processes to clear stale sessions."""
        import subprocess
        for proc in ("chrome.exe", "chromedriver.exe"):
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", proc],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        time.sleep(2)

    def start_browser(self):
        self._acquire_lock()

        try:
            import undetected_chromedriver as uc_local
            global uc
            uc = uc_local
        except ModuleNotFoundError as e:
            logger.warning(f"undetected_chromedriver import failed: {e}. Falling back to selenium webdriver.")
            uc = None

        if uc:
            options = uc.ChromeOptions()
        else:
            from selenium.webdriver import ChromeOptions
            options = ChromeOptions()

        options.add_argument(f"--user-data-dir={settings.chrome_profile_path}")

        proxy_arg = proxy_manager.get_proxy_option()
        if proxy_arg:
            options.add_argument(proxy_arg)

        if settings.HEADLESS:
            options.add_argument("--headless=new")

        self._apply_scheduler_flags(options)

        if uc:
            chrome_version = _get_chrome_version()
            try:
                self.driver = uc.Chrome(
                    options=options,
                    use_subprocess=True,
                    version_main=chrome_version,
                )
                logger.info(f"Browser started successfully (undetected-chromedriver v{chrome_version}).")
            except Exception as e:
                logger.warning(
                    f"uc.Chrome attempt 1 failed (v{chrome_version}): {e}\n"
                    "Force-killing stale Chrome processes and retrying..."
                )
                self._force_kill_chrome()
                try:
                    self.driver = uc.Chrome(
                        options=options,
                        use_subprocess=True,
                        version_main=chrome_version,
                    )
                    logger.info(f"Browser started on retry (undetected-chromedriver v{chrome_version}).")
                except Exception as e2:
                    logger.error(
                        f"uc.Chrome attempt 2 also failed (v{chrome_version}): {e2}\n"
                        "Falling back to webdriver-manager."
                    )

        if not self.driver:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service as ChromeService
                from webdriver_manager.chrome import ChromeDriverManager

                service = ChromeService(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
                logger.info("Browser started successfully (webdriver-manager fallback).")
            except Exception as e3:
                logger.error(f"Failed to start browser with fallback: {e3}")
                self._release_lock()
                raise

        if not self.driver:
            self._release_lock()
            raise RuntimeError(
                "BrowserService.start_browser() failed: driver is None after all attempts. "
            )

        if not settings.HEADLESS:
            try:
                self.driver.maximize_window()
            except Exception as e:
                logger.warning(f"Could not maximize window: {e}")

        return self.driver

    def stop_browser(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")
            finally:
                self.driver = None
        
        self._release_lock()

browser_service = BrowserService()
