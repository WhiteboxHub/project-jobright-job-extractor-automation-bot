import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, ElementClickInterceptedException
from core.logger import logger
from core.human_behavior import HumanBehavior

class SafeActions:
    def __init__(self, driver):
        self.driver = driver
        self.human = HumanBehavior(driver)
        
    def _random_sleep(self, min_s=2.1, max_s=4.5):
        HumanBehavior.random_delay(min_s, max_s)

    def _micro_move(self, element):
        try:
            action = ActionChains(self.driver)
            action.move_to_element(element)
            x_offset = random.randint(1, 10)
            y_offset = random.randint(1, 10)
            action.move_by_offset(x_offset, y_offset)
            action.perform()
        except Exception:
            pass

    def safe_click(self, selector, by=By.CSS_SELECTOR, timeout=10, retries=3):
        attempt = 0
        while attempt < retries:
            try:
                element = self.driver.find_element(by, selector)
                self._micro_move(element)
                self._random_sleep(0.5, 1.5)
                try:
                    element.click()
                    return True
                except ElementClickInterceptedException:
                    try:
                        self.driver.execute_script("arguments[0].click();", element)
                        return True
                    except Exception:
                        time.sleep(1)
                        attempt += 1
                        continue
            except StaleElementReferenceException:
                time.sleep(1)
                attempt += 1
            except NoSuchElementException:
                return False
            except Exception as e:
                logger.error(f"Unexpected error clicking {selector}: {e}")
                return False
        return False

    def safe_type(self, selector, text, by=By.CSS_SELECTOR, retries=3):
        attempt = 0
        while attempt < retries:
            try:
                element = self.driver.find_element(by, selector)
                element.clear()
                self._random_sleep(0.3, 0.7)
                self.human.human_type(element, text)
                return True
            except StaleElementReferenceException:
                time.sleep(1)
                attempt += 1
            except Exception as e:
                logger.error(f"Error typing in {selector}: {e}")
                return False
        return False

    def check_exists(self, selector, by=By.CSS_SELECTOR):
        try:
            self.driver.find_element(by, selector)
            return True
        except NoSuchElementException:
            return False
