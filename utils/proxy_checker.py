# proxy_checker.py
import asyncio
import aiohttp
import random
import time
import socket
from typing import List, Dict
from PySide6.QtCore import QObject, Signal

from core.config import Config


class ProxyCheckerSignals(QObject):
    """Signals for proxy checking operations"""
    proxy_scraped = Signal(int)  # count
    proxy_checked = Signal(dict)  # individual proxy result
    scraping_progress_updated = Signal(int, int)  # current, total for scraping
    checking_progress_updated = Signal(int, int)  # current, total for checking
    log_message = Signal(str)  # log message
    checking_started = Signal()
    checking_finished = Signal(list)  # all working proxies
    scraping_started = Signal()
    scraping_finished = Signal()


class ProxyChecker(QObject):
    """Manages proxy scraping and checking operations"""
    
    def __init__(self):
        super().__init__()
        self.signals = ProxyCheckerSignals()
        self.scraped_proxies = []
        self.working_proxies = []
        self.is_checking = False
        self.is_scraping = False
        self.should_stop = False
        
    async def _scrape_proxies_async(self):
        """Scrape proxies from public sources asynchronously"""
        self.is_scraping = True
        self.should_stop = False
        self.signals.scraping_started.emit()
        self.signals.log_message.emit("Starting proxy scraping from public sources...")
        
        all_proxies = []
        total_sources = len(Config.PROXY_SOURCES)
        
        for i, (url, scheme) in enumerate(Config.PROXY_SOURCES):
            if self.should_stop:
                break
                
            try:
                self.signals.log_message.emit(f"Scraping from {url}...")
                
                timeout = aiohttp.ClientTimeout(total=30)
                connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
                
                async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            text = await response.text()
                            proxies = [line.strip() for line in text.split('\n') if line.strip()]
                            
                            # Convert to full proxy URLs and filter unique
                            full_proxies = []
                            for proxy in proxies:
                                if proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                                    full_proxies.append(proxy)
                                else:
                                    full_proxies.append(f"{scheme}://{proxy}")
                            
                            # Filter unique proxies by protocol:ip:port
                            unique_proxies = self._filter_unique_proxies(full_proxies)
                            all_proxies.extend(unique_proxies)
                            self.signals.log_message.emit(f"Found {len(unique_proxies)} unique proxies from {url}")
                        
                    self.signals.scraping_progress_updated.emit(i + 1, total_sources)
                    
            except Exception as e:
                self.signals.log_message.emit(f"Failed to scrape from {url}: {str(e)}")
            
            # Small delay to avoid being blocked
            await asyncio.sleep(1)
        
        if not self.should_stop:
            # Remove duplicates across all sources
            self.scraped_proxies = self._filter_unique_proxies(all_proxies)
            self.signals.proxy_scraped.emit(len(self.scraped_proxies))
            self.signals.scraping_finished.emit()
        else:
            self.signals.log_message.emit("Proxy scraping stopped by user")
            self.signals.scraping_finished.emit()
            
        self.is_scraping = False
    
    def _filter_unique_proxies(self, proxies: List[str]) -> List[str]:
        """Filter proxies to keep only unique protocol:ip:port combinations"""
        unique_proxies = {}
        
        for proxy in proxies:
            try:
                # Extract protocol, ip, and port
                if proxy.startswith('socks5://'):
                    protocol = 'socks5'
                    rest = proxy[9:]
                elif proxy.startswith('socks4://'):
                    protocol = 'socks4'
                    rest = proxy[9:]
                elif proxy.startswith('http://'):
                    protocol = 'http'
                    rest = proxy[7:]
                elif proxy.startswith('https://'):
                    protocol = 'https'
                    rest = proxy[8:]
                else:
                    continue
                
                # Extract IP and port
                if ':' in rest:
                    ip, port = rest.split(':', 1)
                    # Remove any authentication part if present
                    if '@' in ip:
                        ip = ip.split('@')[-1]
                    
                    key = f"{protocol}:{ip}:{port}"
                    unique_proxies[key] = proxy
                    
            except Exception:
                continue
        
        return list(unique_proxies.values())
    
    async def _check_proxies_async(self, proxies: List[str], use_us_only: bool = True, timeout: int = None):
        """Check proxies asynchronously with better error handling"""
        if timeout is None:
            timeout = Config.DEFAULT_TIMEOUT_SEC
            
        self.is_checking = True
        self.should_stop = False
        self.signals.checking_started.emit()
        self.signals.log_message.emit(f"Checking {len(proxies)} proxies (timeout: {timeout}s)...")
        
        working_proxies = []
        
        # Filter unique proxies before checking
        unique_proxies = self._filter_unique_proxies(proxies)
        self.signals.log_message.emit(f"After deduplication: {len(unique_proxies)} unique proxies to check")
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(min(Config.DEFAULT_CONCURRENCY, 50))
        
        tasks = []
        for proxy in unique_proxies:
            if self.should_stop:
                break
            task = self._check_single_proxy_with_retry(proxy, semaphore, use_us_only, timeout)
            tasks.append(task)
        
        # Process results as they complete
        completed = 0
        for task in asyncio.as_completed(tasks):
            if self.should_stop:
                break
                
            try:
                result = await task
                completed += 1
                
                if self.should_stop:
                    break
                    
                # Strict timeout enforcement
                if result['working'] and result['latency'] > timeout:
                    result['working'] = False
                    self.signals.log_message.emit(f"âœ— Proxy timeout: {result['proxy']} ({result['latency']:.2f}s > {timeout}s)")
                
                if result['working']:
                    working_proxies.append(result)
                    self.signals.log_message.emit(f"âœ“ Working proxy: {result['proxy']} ({result['country']}, {result['latency']:.2f}s)")
                else:
                    self.signals.log_message.emit(f"âœ— Failed proxy: {result['proxy']}")
                
                self.signals.proxy_checked.emit(result)
                self.signals.checking_progress_updated.emit(completed, len(unique_proxies))
                
            except Exception as e:
                completed += 1
                self.signals.checking_progress_updated.emit(completed, len(unique_proxies))
                continue
        
        if not self.should_stop:
            self.working_proxies = working_proxies
            self.signals.checking_finished.emit(working_proxies)
            self.signals.log_message.emit(f"Proxy checking completed. Found {len(working_proxies)} working proxies.")
        else:
            self.signals.log_message.emit(f"Proxy checking stopped. Found {len(working_proxies)} working proxies so far.")
            self.signals.checking_finished.emit(working_proxies)
            
        self.is_checking = False
    
    async def _check_single_proxy_with_retry(self, proxy: str, semaphore: asyncio.Semaphore, use_us_only: bool = True, timeout: int = None, max_retries: int = 2):
        """Check a single proxy with retry mechanism"""
        for attempt in range(max_retries):
            try:
                result = await self._check_single_proxy(proxy, semaphore, use_us_only, timeout)
                if result['working']:
                    return result
                # If not working, wait a bit before retry
                await asyncio.sleep(0.5)
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                else:
                    # Return failed result after all retries
                    return {
                        'proxy': proxy,
                        'type': self._get_proxy_type(proxy),
                        'country': 'Unknown',
                        'latency': timeout + 1 if timeout else 11,
                        'working': False
                    }
        
        # Should not reach here, but return failed result
        return {
            'proxy': proxy,
            'type': self._get_proxy_type(proxy),
            'country': 'Unknown',
            'latency': timeout + 1 if timeout else 11,
            'working': False
        }
    
    async def _check_single_proxy(self, proxy: str, semaphore: asyncio.Semaphore, use_us_only: bool = True, timeout: int = None):
        """Check a single proxy"""
        if timeout is None:
            timeout = Config.DEFAULT_TIMEOUT_SEC
            
        async with semaphore:
            proxy_info = {
                'proxy': proxy,
                'type': self._get_proxy_type(proxy),
                'country': 'Unknown',
                'latency': timeout + 1,
                'working': False
            }
            
            start_time = time.time()
            
            try:
                # Test proxy with multiple endpoints
                for endpoint, country_field in Config.IP_CHECK_ENDPOINTS:
                    try:
                        from aiohttp_socks import ProxyConnector
                        
                        connector = ProxyConnector.from_url(proxy)
                        timeout_obj = aiohttp.ClientTimeout(total=timeout)
                        
                        async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
                            async with session.get(endpoint, headers={'User-Agent': Config.USER_AGENT}) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    
                                    # Extract country info
                                    country = self._extract_country(data, country_field)
                                    proxy_info['country'] = country
                                    proxy_info['latency'] = time.time() - start_time
                                    
                                    # Check if it's US proxy or if we don't care about country
                                    if not use_us_only or country.upper() in ['US', 'USA', 'UNITED STATES']:
                                        proxy_info['working'] = True
                                        return proxy_info
                    
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        continue
                
            except Exception as e:
                proxy_info['working'] = False
                proxy_info['latency'] = time.time() - start_time
            
            return proxy_info
    
    def _get_proxy_type(self, proxy: str) -> str:
        """Extract proxy type from URL"""
        if proxy.startswith('socks5://'):
            return 'SOCKS5'
        elif proxy.startswith('socks4://'):
            return 'SOCKS4'
        elif proxy.startswith('https://'):
            return 'HTTPS'
        else:
            return 'HTTP'
    
    def _extract_country(self, data: dict, field: str) -> str:
        """Extract country information from response data"""
        try:
            if field == 'cc':
                return data.get('cc', 'Unknown')
            elif field == 'country':
                return data.get('country', 'Unknown')
            elif field == 'country_iso':
                return data.get('country_iso', 'Unknown')
            elif field == 'origin':
                return 'Unknown'
        except:
            pass
        return 'Unknown'

    def stop_checking(self):
        """Stop the current proxy checking process"""
        self.should_stop = True
        self.is_checking = False
        self.is_scraping = False
        self.signals.log_message.emit("Proxy checking stopped by user")