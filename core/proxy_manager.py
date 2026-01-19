# proxy_manager.py
import random
from typing import List, Optional
from PySide6.QtCore import QObject, Signal

from .config import Config


class ProxyManager(QObject):
    """Manages proxy rotation for search sessions"""
    
    # Signals for UI updates
    proxy_added = Signal(list)
    proxy_removed = Signal(str)
    working_proxies_updated = Signal(list)  # New signal for working proxies update
    
    def __init__(self):
        super().__init__()
        # Load custom proxies from config
        self.proxies = Config.CUSTOM_PROXIES.copy()
        self.used_proxies = set()
        self.working_proxies = set()
    
    def get_proxy(self) -> Optional[str]:
        """Get a random working proxy, or if none, a random available proxy"""
        # First try working proxies
        if self.working_proxies:
            available_working = list(self.working_proxies - self.used_proxies)
            if not available_working:
                # Reset if all working proxies have been used
                self.used_proxies.clear()
                available_working = list(self.working_proxies)
                
            if available_working:
                proxy = random.choice(available_working)
                self.used_proxies.add(proxy)
                return proxy
        
        # If no working proxies, use any available proxy
        if self.proxies:
            available_all = list(set(self.proxies) - self.used_proxies)
            if not available_all:
                # Reset if all proxies have been used
                self.used_proxies.clear()
                available_all = self.proxies
                
            if available_all:
                proxy = random.choice(available_all)
                self.used_proxies.add(proxy)
                return proxy
                
        return None

    def get_working_proxies(self) -> List[str]:
        """Get all working proxies"""
        return list(self.working_proxies)
    
    def add_proxies(self, proxies: List[str]):
        """Add new proxies to the pool and save to config"""
        new_proxies = [p for p in proxies if p not in self.proxies]
        self.proxies.extend(new_proxies)
        
        # Save to config
        Config.CUSTOM_PROXIES = self.proxies.copy()
        Config.save_settings()
        
        if new_proxies:
            self.proxy_added.emit(new_proxies)
    
    def mark_proxy_working(self, proxy: str):
        """Mark a proxy as working"""
        self.working_proxies.add(proxy)
        # Ensure it's in the main proxies list
        if proxy not in self.proxies:
            self.proxies.append(proxy)
            Config.CUSTOM_PROXIES = self.proxies.copy()
            Config.save_settings()
        
        # Emit signal that working proxies were updated
        self.working_proxies_updated.emit(list(self.working_proxies))
    
    def mark_proxy_failed(self, proxy: str):
        """Mark a proxy as failed"""
        if proxy in self.working_proxies:
            self.working_proxies.remove(proxy)
            # Emit signal that working proxies were updated
            self.working_proxies_updated.emit(list(self.working_proxies))
    
    def get_proxy_count(self) -> int:
        """Get total number of available proxies"""
        return len(self.proxies)
    
    def get_working_proxy_count(self) -> int:
        """Get number of working proxies"""
        return len(self.working_proxies)
    
    def clear_proxies(self):
        """Clear all proxies"""
        self.proxies.clear()
        self.working_proxies.clear()
        self.used_proxies.clear()
        Config.CUSTOM_PROXIES = []
        Config.save_settings()
        
        # Emit signal that working proxies were updated
        self.working_proxies_updated.emit([])

    def update_working_proxies(self, new_working_proxies: List[str]):
        """Update the working proxies list entirely"""
        self.working_proxies = set(new_working_proxies)
        
        # Update main proxies list to include working ones
        for proxy in new_working_proxies:
            if proxy not in self.proxies:
                self.proxies.append(proxy)
        
        # Save to config
        Config.CUSTOM_PROXIES = self.proxies.copy()
        Config.save_settings()
        
        # Emit signal that working proxies were updated
        self.working_proxies_updated.emit(new_working_proxies)

    def reset_working_proxies(self):
        """Reset working proxies for new checking session"""
        self.working_proxies.clear()
        self.used_proxies.clear()
        # Emit signal that working proxies were updated
        self.working_proxies_updated.emit([])