import asyncio
import random
import time
from typing import List, Dict
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, QMutex

from .captcha_manager import CaptchaManager
from .config import Config


class SearchSignals(QObject):
    """Signals for search operations"""
    search_started = Signal(int, str)  # browser_id, proxy
    search_completed = Signal(int, str)  # browser_id, status
    search_failed = Signal(int, str)  # browser_id, error
    progress_update = Signal(int, int)  # current, total
    log_message = Signal(str)  # log message
    captcha_detected = Signal(int)  # browser_id
    captcha_solved = Signal(int)  # browser_id
    all_searches_completed = Signal()  # When max searches reached
    stats_updated = Signal(dict)  # Emit stats for UI update
    target_found = Signal(int)  # browser_id when target text is found


class BrowserInstance(QRunnable):
    """Individual browser instance for performing searches"""
    
    def __init__(self, browser_id: int, keyword: str, user_agent: str, debug_mode: bool = False, captcha_manager: CaptchaManager = None):
        super().__init__()
        self.browser_id = browser_id
        self.keyword = keyword
        self.user_agent = user_agent
        self.debug_mode = debug_mode
        self.captcha_manager = captcha_manager
        self.signals = SearchSignals()
        self._is_running = True
        self.target_found = False
    
    def run(self):
        """Execute the search in a separate thread"""
        try:
            self.signals.search_started.emit(self.browser_id, "direct")
            self.signals.log_message.emit(f"Browser {self.browser_id}: Starting search with direct connection")
            
            # Run the async search
            asyncio.run(self._perform_search())
            
            if self._is_running:
                if self.target_found:
                    self.signals.search_completed.emit(self.browser_id, "SUCCESS_TARGET_FOUND")
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Search completed successfully - TARGET FOUND!")
                else:
                    self.signals.search_completed.emit(self.browser_id, "SUCCESS")
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Search completed successfully")
            
        except Exception as e:
            if self._is_running:
                error_msg = str(e)
                self.signals.search_failed.emit(self.browser_id, error_msg)
                self.signals.log_message.emit(f"Browser {self.browser_id}: FAILED - {error_msg}")
    
    async def _perform_search(self):
        """Perform the actual Google search using Playwright with integrated proxies"""
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
        
        playwright = await async_playwright().start()
        browser = None
        
        try:
            # Configure browser launch options
            browser_options = {
                "headless": not self.debug_mode,
                "timeout": Config.TIMEOUT
            }
            
            # Use hardcoded proxies in rotation
            proxy = self._get_proxy_for_browser()
            if proxy:
                browser_options["proxy"] = proxy
                self.signals.log_message.emit(f"Browser {self.browser_id}: Using proxy {proxy['server']}")
            else:
                self.signals.log_message.emit(f"Browser {self.browser_id}: Using direct connection")
            
            # Launch browser with additional stealth args
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=VizDisplayCompositor",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-popup-blocking",
                "--disable-translate",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--metrics-recording-only",
                "--no-first-run",
                "--disable-client-side-phishing-detection",
                "--disable-prompt-on-repost",
                "--disable-hang-monitor",
                "--disable-component-extensions-with-background-pages",
                "--disable-domain-reliability",
                "--disable-partial-raster",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
            ]
            
            browser_options["args"] = browser_args
            
            # Launch browser
            browser = await playwright.chromium.launch(**browser_options)
            
            # Create context with user agent and viewport
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
            )
            
            # Apply stealth to context
            await self._apply_stealth_measures(context)
            
            page = await context.new_page()

            # Remove webdriver property and apply additional stealth
            await page.add_init_script("""
                delete Object.getPrototypeOf(navigator).webdriver;
                delete Object.getPrototypeOf(navigator).plugins;
                delete Object.getPrototypeOf(navigator).languages;
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            """)
            
            # Set longer timeout for navigation
            page.set_default_timeout(45000)
            page.set_default_navigation_timeout(45000)
            
            # Step 1: Navigate to Google
            self.signals.log_message.emit(f"Browser {self.browser_id}: Step 1 - Navigating to Google")
            await page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check if we hit CAPTCHA immediately
            if await self._is_captcha_page(page):
                self.signals.log_message.emit(f"Browser {self.browser_id}: CAPTCHA detected immediately after navigation")
                if self.captcha_manager:
                    captcha_solved = await self.captcha_manager.solve_recaptcha_if_present(self.browser_id, page, "immediate")
                    if not captcha_solved:
                        raise Exception("Immediate CAPTCHA could not be solved")
                else:
                    raise Exception("CAPTCHA detected but CAPTCHA solving is disabled")
            
            # Step 2: Perform search operation
            self.signals.log_message.emit(f"Browser {self.browser_id}: Step 2 - Performing search")
            search_success = await self._perform_search_operation(page)
            
            if not search_success:
                raise Exception("Search operation failed")
            
            # Step 3: Check for post-search CAPTCHA
            self.signals.log_message.emit(f"Browser {self.browser_id}: Step 3 - Checking for post-search CAPTCHA")
            await asyncio.sleep(random.uniform(3, 6))
            
            # Check if we're on a CAPTCHA page after search
            if await self._is_captcha_page(page):
                self.signals.log_message.emit(f"Browser {self.browser_id}: CAPTCHA detected after search")
                if self.captcha_manager:
                    captcha_solved = await self.captcha_manager.solve_recaptcha_if_present(self.browser_id, page, "post-search")
                    if not captcha_solved:
                        # If CAPTCHA not solved, try to continue anyway
                        self.signals.log_message.emit(f"Browser {self.browser_id}: CAPTCHA not solved, but continuing...")
                else:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: CAPTCHA detected but CAPTCHA solving disabled")
            
            # Step 4: Final verification - Check for successful search
            self.signals.log_message.emit(f"Browser {self.browser_id}: Step 4 - Final verification")
            await asyncio.sleep(random.uniform(2, 4))
            
            # Check if we successfully reached search results AND found the target text
            try:
                current_url = page.url
                search_title = await page.title()
                
                # Check for the specific target text in the page
                self.target_found = await self._is_target_text_found(page)
                
                # Check various success indicators
                if self.target_found:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: ✓✓✓ SUCCESS - Target text 'Dailynewswork Weekly Magazine' found!")
                    self.signals.log_message.emit(f"Browser {self.browser_id}: On search results page with target content")
                    self.signals.target_found.emit(self.browser_id)
                elif await self._is_search_results_page(page) or "google.com/search" in current_url:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: ✓ Search completed successfully (but target text not found)")
                    self.signals.log_message.emit(f"Browser {self.browser_id}: On search results page")
                elif "sorry" in current_url or "captcha" in current_url:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: ⚠ Still on CAPTCHA page, but marking as completed")
                    # We'll count this as completed since we tried to solve CAPTCHA
                else:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: ? Uncertain page state, but marking as completed")
                    
            except Exception as e:
                self.signals.log_message.emit(f"Browser {self.browser_id}: Final verification note: {e}")
            
            # Print final URL and title
            final_url = page.url
            final_title = await page.title()
            self.signals.log_message.emit(f"Browser {self.browser_id}: Final URL: {final_url}")
            self.signals.log_message.emit(f"Browser {self.browser_id}: Final title: {final_title}")
            
        except Exception as e:
            raise Exception(f"Search failed: {str(e)}")
        finally:
            # Always close browser and playwright
            try:
                if browser:
                    await browser.close()
                await playwright.stop()
            except Exception as e:
                self.signals.log_message.emit(f"Browser {self.browser_id}: Error closing browser: {e}")
    
    async def _apply_stealth_measures(self, context):
        """Apply additional stealth measures to avoid detection"""
        await context.add_init_script("""
            // Override the permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Mock Chrome runtime
            window.chrome = {
                runtime: {
                    // Mock the Chrome runtime
                }
            };

            // Remove automation痕迹
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
        """)
    
    async def _is_target_text_found(self, page) -> bool:
        """Enhanced method to check if the target text is found on the page"""
        try:
            target_text = "Dailynewswork Weekly Magazine"
            
            # Method 1: Exact CSS selector match
            target_selectors = [
                'h3.LC20lb.MBeuO.DKV0Md',
                'h3.LC20lb',
                '.LC20lb',
                '[class*="LC20lb"]',
                'h3[class*="LC20lb"]'
            ]
            
            for selector in target_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        text_content = await element.text_content()
                        if text_content and target_text in text_content:
                            self.signals.log_message.emit(f"Browser {self.browser_id}: Found target text with selector: {selector}")
                            return True
                except Exception:
                    continue
            
            # Method 2: Text-based search using Playwright's text selector
            try:
                text_elements = await page.query_selector_all(f'text="{target_text}"')
                if text_elements and len(text_elements) > 0:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Found target text using exact text match")
                    return True
            except Exception:
                pass
            
            # Method 3: Partial text match
            try:
                partial_elements = await page.query_selector_all('text=/Dailynewswork/i')
                for element in partial_elements:
                    text_content = await element.text_content()
                    if text_content and "Dailynewswork" in text_content:
                        self.signals.log_message.emit(f"Browser {self.browser_id}: Found target text using partial match")
                        return True
            except Exception:
                pass
            
            # Method 4: JavaScript evaluation for text content search
            try:
                found = await page.evaluate("""
                    (targetText) => {
                        // Search in all elements
                        const elements = document.querySelectorAll('*');
                        for (let element of elements) {
                            if (element.textContent && element.textContent.includes(targetText)) {
                                return true;
                            }
                        }
                        return false;
                    }
                """, target_text)
                
                if found:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Found target text using JavaScript evaluation")
                    return True
            except Exception:
                pass
            
            # Method 5: Check page HTML content
            try:
                page_content = await page.content()
                if target_text in page_content:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Found target text in page HTML")
                    return True
            except Exception:
                pass
                
            self.signals.log_message.emit(f"Browser {self.browser_id}: Target text '{target_text}' not found")
            return False
            
        except Exception as e:
            self.signals.log_message.emit(f"Browser {self.browser_id}: Error checking for target text: {e}")
            return False
    
    def _get_proxy_for_browser(self):
        """Get a proxy for the browser instance from hardcoded list"""
        if not Config.HARDCODED_PROXIES:
            return None
            
        proxy_str = random.choice(Config.HARDCODED_PROXIES)
        return self._parse_proxy(proxy_str)
    
    def _parse_proxy(self, proxy_str: str):
        """Parse proxy string into Playwright proxy configuration"""
        parts = proxy_str.strip().split(":")
        if len(parts) < 4:
            return None
        
        host, port, username = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        
        return {
            "server": f"http://{host}:{port}",
            "username": username,
            "password": password
        }

    async def _is_search_results_page(self, page) -> bool:
        """Check if we're on a Google search results page"""
        try:
            # Check for search results indicators
            search_results = await page.query_selector("#search")
            search_box = await page.query_selector('input[name="q"]')
            current_url = page.url
            
            return (search_results is not None or 
                   "google.com/search" in current_url or
                   (search_box and await search_box.is_visible()))
        except:
            return False

    async def _perform_search_operation(self, page):
        """Perform the search operation"""
        try:
            # Try multiple selectors for the search box
            selectors = [
                'textarea[jsname="yZiJbe"]',
                'textarea[name="q"]',
                'textarea[title="Search"]',
                'textarea[aria-label="Search"]',
                'input[name="q"]',
                'input[title="Search"]',
                'input[aria-label="Search"]',
                '[name="q"]',
                'textarea.gLFyf',
                'input.gLFyf'
            ]
            
            search_box = None
            for selector in selectors:
                search_box = await page.query_selector(selector)
                if search_box and await search_box.is_visible():
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Found search box with selector: {selector}")
                    break
            
            if search_box:
                # Clear any existing text and type the keyword
                await search_box.click()
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await search_box.fill("")
                
                # Type with random delays to simulate human
                for char in self.keyword:
                    await search_box.type(char, delay=random.randint(50, 150))
                    await asyncio.sleep(random.uniform(0.05, 0.2))
                
                await asyncio.sleep(random.uniform(0.5, 1.5))
                await search_box.press("Enter")
                self.signals.log_message.emit(f"Browser {self.browser_id}: Search submitted successfully for '{self.keyword}'!")
                
                # Wait for navigation after search
                try:
                    await page.wait_for_navigation(timeout=30000)
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Navigation after search completed")
                except Exception as e:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Navigation timeout after search, continuing...")
                
                return True
            else:
                self.signals.log_message.emit(f"Browser {self.browser_id}: Could not find search box with any selector")
                # Try alternative approach - navigate directly to search URL
                try:
                    search_url = f"https://www.google.com/search?q={self.keyword.replace(' ', '+')}"
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Trying direct search URL: {search_url}")
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Direct search URL navigation successful")
                    return True
                except Exception as e:
                    self.signals.log_message.emit(f"Browser {self.browser_id}: Direct search URL also failed: {e}")
                    return False
                
        except Exception as e:
            self.signals.log_message.emit(f"Browser {self.browser_id}: Error during search: {e}")
            return False

    async def _is_captcha_page(self, page) -> bool:
        """Check if current page is a CAPTCHA page using multiple methods"""
        try:
            current_url = page.url.lower()
            
            # Check URL patterns for CAPTCHA pages
            if "sorry" in current_url or "captcha" in current_url:
                return True
            
            # Get page content
            content = await page.content()
            
            # Check for CAPTCHA elements in content
            captcha_indicators = [
                "g-recaptcha",
                "recaptcha",
                "captcha",
                "cf_captcha_kind",
                "challenge-form"
            ]
            
            content_lower = content.lower()
            if any(indicator in content_lower for indicator in captcha_indicators):
                return True
            
            # Check for visible CAPTCHA elements
            captcha_selectors = [
                ".g-recaptcha",
                "#recaptcha",
                "[class*='captcha']",
                "[id*='captcha']",
                "#g-recaptcha-response"
            ]
            
            for selector in captcha_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        return True
                except:
                    continue
            
            # Check for CAPTCHA iframes
            captcha_iframes = await page.query_selector_all('iframe[src*="recaptcha"], iframe[src*="captcha"]')
            if captcha_iframes:
                for iframe in captcha_iframes:
                    try:
                        if await iframe.is_visible():
                            return True
                    except:
                        continue
                    
            return False
        except:
            return False
    
    def stop(self):
        """Stop this browser instance"""
        self._is_running = False
        
class SearchManager(QObject):
    """Manages multiple browser instances and search operations"""
    
    def __init__(self):
        super().__init__()
        self.captcha_manager = CaptchaManager()
        self.browser_instances: List[BrowserInstance] = []
        self.active_browsers = 0
        self.max_active_browsers = Config.CONCURRENT_BROWSERS
        self.is_running = False
        self.current_keyword = ""
        self.debug_mode = False
        self.cycle_count = 0
        self.max_searches = 0
        self.completed_searches = 0
        self.failed_searches = 0
        self.successful_searches = 0
        self.target_found_searches = 0  # Track searches where target was found
        self.signals = SearchSignals()
        self.thread_pool = QThreadPool()
        self.mutex = QMutex()  # For thread-safe operations
        
        # Connect CAPTCHA manager signals
        self.captcha_manager.signals.log_message.connect(self.signals.log_message.emit)
        self.captcha_manager.signals.captcha_solved.connect(self.on_captcha_solved)
        self.captcha_manager.signals.captcha_failed.connect(self.on_captcha_failed)
        
        # Set initial thread pool size
        self.thread_pool.setMaxThreadCount(self.max_active_browsers)
    
    def start_searches(self, keyword: str, concurrency: int, max_searches: int):
        """Start multiple search sessions"""
        if self.is_running:
            self.stop_searches()
        
        self.is_running = True
        self.current_keyword = keyword
        self.max_searches = max_searches
        self.max_active_browsers = concurrency
        self.completed_searches = 0
        self.failed_searches = 0
        self.successful_searches = 0
        self.target_found_searches = 0
        self.cycle_count = 0
        
        # Update thread pool max threads
        self.thread_pool.setMaxThreadCount(concurrency)
        
        self.signals.log_message.emit(f"Starting searches for keyword: '{keyword}'")
        self.signals.log_message.emit(f"Concurrency: {concurrency}, Max Searches: {max_searches}")
        self.signals.log_message.emit(f"Using integrated proxies: {len(Config.HARDCODED_PROXIES)} available")
        self.signals.log_message.emit(f"Maximum active browsers: {self.max_active_browsers}")
        
        # Start initial batch
        self._start_batch()
    
    def _start_batch(self):
        """Start a batch of concurrent searches"""
        if not self.is_running or self.completed_searches >= self.max_searches:
            if self.completed_searches >= self.max_searches:
                self.signals.all_searches_completed.emit()
                self.signals.log_message.emit(f"Completed {self.max_searches} searches. Continuous mode will continue after interval.")
            return
        
        # Calculate how many searches to start in this batch
        available_slots = self.max_active_browsers - self.active_browsers
        remaining_searches = self.max_searches - self.completed_searches
        batch_size = min(available_slots, remaining_searches)
        
        if batch_size <= 0:
            return
        
        self.signals.log_message.emit(f"Starting {batch_size} new browsers (active: {self.active_browsers}/{self.max_active_browsers})")
        
        for i in range(batch_size):
            if self.completed_searches + self.active_browsers >= self.max_searches:
                break
                
            user_agent = random.choice(Config.USER_AGENTS)
            browser_id = self.completed_searches + self.active_browsers + 1
            
            browser = BrowserInstance(
                browser_id, 
                self.current_keyword, 
                user_agent, 
                self.debug_mode, 
                self.captcha_manager
            )
            browser.signals.search_started.connect(self._on_search_started)
            browser.signals.search_completed.connect(self._on_search_completed)
            browser.signals.search_failed.connect(self._on_search_failed)
            browser.signals.log_message.connect(self.signals.log_message.emit)
            browser.signals.target_found.connect(self._on_target_found)
            
            self.browser_instances.append(browser)
            self.thread_pool.start(browser)
    
    def _on_search_started(self, browser_id: int, proxy: str):
        """Handle search started - track active browsers"""
        self.mutex.lock()
        self.active_browsers += 1
        self.mutex.unlock()
        self.signals.log_message.emit(f"Browser {browser_id} started (active: {self.active_browsers}/{self.max_active_browsers})")
        self._emit_stats()
    
    def _on_search_completed(self, browser_id: int, status: str):
        """Handle search completion"""
        self.mutex.lock()
        self.completed_searches += 1
        self.successful_searches += 1
        
        # Track if target was found
        if status == "SUCCESS_TARGET_FOUND":
            self.target_found_searches += 1
            
        self.active_browsers -= 1
        self.mutex.unlock()
        
        self.signals.progress_update.emit(self.completed_searches, self.max_searches)
        
        if status == "SUCCESS_TARGET_FOUND":
            self.signals.log_message.emit(f"Browser {browser_id} completed successfully - TARGET FOUND! (active: {self.active_browsers}/{self.max_active_browsers})")
        else:
            self.signals.log_message.emit(f"Browser {browser_id} completed successfully (active: {self.active_browsers}/{self.max_active_browsers})")
        
        self._emit_stats()
        
        # Start next search if we haven't reached max
        if self.is_running and self.completed_searches < self.max_searches:
            self._start_batch()
    
    def _on_target_found(self, browser_id: int):
        """Handle when target text is found"""
        self.signals.log_message.emit(f"Browser {browser_id}: 🎯 TARGET TEXT FOUND - 'Dailynewswork Weekly Magazine'")
    
    def _on_search_failed(self, browser_id: int, error: str):
        """Handle search failure"""
        self.mutex.lock()
        self.completed_searches += 1
        self.failed_searches += 1
        self.active_browsers -= 1
        self.mutex.unlock()
        
        self.signals.progress_update.emit(self.completed_searches, self.max_searches)
        self.signals.log_message.emit(f"Browser {browser_id} failed (active: {self.active_browsers}/{self.max_active_browsers})")
        
        self._emit_stats()
        
        # Start next search if we haven't reached max
        if self.is_running and self.completed_searches < self.max_searches:
            self._start_batch()
    
    def on_captcha_solved(self, result: dict):
        """Handle CAPTCHA solved signal"""
        browser_id = result['browser_id']
        self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA solved at {result['step']}")
    
    def on_captcha_failed(self, browser_id: str, error: str):
        """Handle CAPTCHA failed signal"""
        self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA failed - {error}")
    
    def _emit_stats(self):
        """Emit current statistics for UI update"""
        stats = self.get_status()
        self.signals.stats_updated.emit(stats)
    
    def stop_searches(self):
        """Stop all search operations"""
        self.is_running = False
        
        # Stop all browser instances
        for browser in self.browser_instances:
            browser.stop()
        
        self.browser_instances.clear()
        self.active_browsers = 0
        self.signals.log_message.emit("Search sessions stopped")
        self._emit_stats()
    
    def get_status(self) -> Dict:
        """Get current search manager status"""
        total_searches = self.completed_searches
        success_rate = (self.successful_searches / total_searches * 100) if total_searches > 0 else 0
        target_found_rate = (self.target_found_searches / total_searches * 100) if total_searches > 0 else 0
        remaining = max(0, self.max_searches - total_searches)
        
        return {
            "is_running": self.is_running,
            "current_keyword": self.current_keyword,
            "active_browsers": self.active_browsers,
            "max_active_browsers": self.max_active_browsers,
            "cycle_count": self.cycle_count,
            "completed_searches": total_searches,
            "successful_searches": self.successful_searches,
            "failed_searches": self.failed_searches,
            "target_found_searches": self.target_found_searches,
            "success_rate": success_rate,
            "target_found_rate": target_found_rate,
            "remaining_searches": remaining,
            "max_searches": self.max_searches
        }
    
    def restart_searches_continuous(self):
        """Restart searches in continuous mode"""
        if not self.is_running:
            keyword = self.current_keyword
            concurrency = self.max_active_browsers
            max_searches = self.max_searches
            
            if keyword:
                self.signals.log_message.emit("Continuous mode: Restarting searches...")
                self.start_searches(keyword, concurrency, max_searches)