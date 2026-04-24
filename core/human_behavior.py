"""
Human Behavior Simulation Module

Provides utilities to simulate human-like interactions with web forms:
- Random delays between actions
- Typing with variable speed
- Mouse movements before clicks
- Smooth scrolling to elements
"""

import random
import time
from selenium.webdriver.common.action_chains import ActionChains
from core.logger import logger


class HumanBehavior:
    """Simulates human-like browser behavior to avoid detection"""
    
    def __init__(self, driver):
        self.driver = driver
    
    @staticmethod
    def random_delay(min_seconds=1, max_seconds=3):
        """
        Random delay between actions to simulate human thinking/reading time
        
        Args:
            min_seconds: Minimum delay in seconds
            max_seconds: Maximum delay in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        logger.debug(f"Human delay: {delay:.2f}s")
    
    @staticmethod
    def typing_delay():
        """
        Delay between keystrokes (50-150ms)
        Simulates natural typing rhythm
        
        Returns:
            Random delay between 0.05 and 0.15 seconds
        """
        return random.uniform(0.05, 0.15)
    
    def human_type(self, element, text):
        """
        Type text with human-like delays between each keystroke
        
        Args:
            element: WebElement to type into
            text: Text string to type
        """
        for char in text:
            element.send_keys(char)
            time.sleep(self.typing_delay())
        logger.debug(f"Typed text with human-like delays: {text[:20]}...")
    
    def human_click(self, element):
        """
        Click with slight delay and mouse movement
        
        Args:
            element: WebElement to click
        """
        try:
            # Move to element first (simulates mouse movement)
            actions = ActionChains(self.driver)
            actions.move_to_element(element)
            actions.pause(random.uniform(0.1, 0.3))
            actions.click()
            actions.perform()
            
            # Random delay after click
            self.random_delay(0.5, 1.5)
            logger.debug("Human-like click performed")
            
        except Exception as e:
            # Fallback to direct click if ActionChains fails
            logger.warning(f"ActionChains click failed, using direct click: {e}")
            element.click()
            self.random_delay(0.5, 1.5)
    
    def scroll_to_element(self, element, smooth=True):
        """
        Scroll to element smoothly
        
        Args:
            element: WebElement to scroll to
            smooth: Whether to use smooth scrolling behavior
        """
        behavior = 'smooth' if smooth else 'auto'
        self.driver.execute_script(
            f"arguments[0].scrollIntoView({{behavior: '{behavior}', block: 'center'}});", 
            element
        )
        self.random_delay(0.5, 1.0)
        logger.debug("Scrolled to element")
    
    def scroll_page(self, direction='down', amount=300):
        """
        Scroll the page by a specified amount
        
        Args:
            direction: 'down' or 'up'
            amount: Number of pixels to scroll
        """
        scroll_amount = amount if direction == 'down' else -amount
        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        self.random_delay(0.3, 0.8)
        logger.debug(f"Scrolled {direction} by {amount}px")
    
    def fill_text_field(self, element, text, clear_first=True):
        """
        Fill a text field with human-like typing
        
        Args:
            element: WebElement (input field)
            text: Text to fill
            clear_first: Whether to clear existing text first
        """
        try:
            # Scroll to element
            self.scroll_to_element(element)
            
            # Click on field
            self.human_click(element)
            
            # Clear existing text if requested
            if clear_first:
                element.clear()
                self.random_delay(0.2, 0.5)
            
            # Type with human-like delays
            self.human_type(element, text)
            
            # Random pause after filling
            self.random_delay(0.5, 1.5)
            
            logger.debug(f"Filled text field with human-like behavior")
            return True
            
        except Exception as e:
            logger.error(f"Error filling text field: {e}")
            return False
    
    def move_mouse_randomly(self):
        """
        Move mouse to random position to simulate human activity
        """
        try:
            actions = ActionChains(self.driver)
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-100, 100)
            actions.move_by_offset(x_offset, y_offset)
            actions.perform()
            time.sleep(random.uniform(0.1, 0.3))
            logger.debug(f"Random mouse movement: ({x_offset}, {y_offset})")
        except Exception as e:
            logger.debug(f"Random mouse movement failed: {e}")
