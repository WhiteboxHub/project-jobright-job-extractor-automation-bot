import time
from core.logger import logger

class CaptchaHandler:
    def __init__(self, driver, timeout=120):
        self.driver = driver
        self.timeout = timeout
    
    def wait_for_captcha_solution(self, custom_timeout=None):
        timeout = custom_timeout if custom_timeout is not None else self.timeout
        print(f"\n{'='*120}")
        print("🔒 CAPTCHA DETECTED!")
        print(f"Please solve the CAPTCHA within {timeout} seconds...")
        print(f"{'='*120}\n")
        logger.info(f"CAPTCHA detected - waiting {timeout} seconds for manual solution")
        for remaining in range(timeout, 0, -1):
            if remaining % 10 == 0 or remaining <= 5:
                print(f"\rTime remaining: {remaining} seconds... ", end='', flush=True)
            time.sleep(1)
        print("\n\n✓ Timeout reached - proceeding...")
        time.sleep(2)
    
    def wait_for_captcha_interactive(self):
        print(f"\n{'='*60}")
        print("🔒 CAPTCHA DETECTED!")
        print("Once solved, press ENTER in this console to continue...")
        print(f"{'='*60}\n")
        try:
            input("👉 Press ENTER after solving CAPTCHA... ")
            time.sleep(1)
        except KeyboardInterrupt:
            raise
