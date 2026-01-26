"""Selenium-based scraper used by the refactored LinkedIn pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver


@dataclass(slots=True)
class ScraperConfig:
    profile_url: str
    headless: bool = True
    timeout_seconds: int = 30
    scroll_pause: float = 1.0
    scroll_attempts: int = 3


class LinkedInScraper:
    """Encapsulates Selenium lifecycle + polite scrolling."""

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self._driver: Optional[WebDriver] = None
        self._cancelled = False

    def fetch_html(self) -> str:
        driver = self._ensure_driver()
        driver.get(self.config.profile_url)
        self._respectful_scroll(driver)
        return driver.page_source

    def cancel(self) -> None:
        self._cancelled = True
        self._teardown_driver()

    # ------------------------------------------------------------------ helpers
    def _ensure_driver(self) -> WebDriver:
        if self._driver:
            return self._driver
        options = Options()
        if self.config.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(self.config.timeout_seconds)
        self._driver = driver
        return driver

    def _respectful_scroll(self, driver: WebDriver) -> None:
        attempts = 0
        last_height = driver.execute_script("return document.body.scrollHeight")
        while attempts < self.config.scroll_attempts and not self._cancelled:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.config.scroll_pause)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            attempts += 1

    def _teardown_driver(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            finally:
                self._driver = None

    def __del__(self) -> None:  # pragma: no cover
        self._teardown_driver()


__all__ = ["LinkedInScraper", "ScraperConfig"]
