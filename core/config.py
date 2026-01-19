import os
import json

class Config:
    # Default configuration
    CONCURRENT_BROWSERS = 3
    MAX_BROWSERS = 100
    
    # Search settings
    SEARCH_DELAY_MIN = 2  # seconds
    SEARCH_DELAY_MAX = 10  # seconds
    
    # Playwright settings
    HEADLESS = True
    TIMEOUT = 30000  # 30 seconds
    
    # CAPTCHA settings - Updated for audio CAPTCHA solving
    CAPTCHA_SOLVE_ENABLED = True
    CAPTCHA_MAX_RETRIES = 3
    CAPTCHA_TIMEOUT = 120  # seconds
    
    # Audio CAPTCHA settings
    AUDIO_CAPTCHA_ENABLED = True
    
    # Google search settings
    SEARCH_URL = "https://www.google.com/search?q={keyword}"
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ]

    # UI Settings
    UPDATE_INTERVAL_MS = 500
    
    # Continuous mode settings
    DEFAULT_RESCAN_INTERVAL = 60  # minutes
    
    # Hardcoded proxies for direct integration
    HARDCODED_PROXIES = [
        "ca.proxy-jet.io:1010:251110DU7gC-resi_region-US_Georgia_Atlanta:At1PnxVbC8Lb2ag",
        "ca.proxy-jet.io:1010:251110DU7gC-resi_region-US_California_Florin:At1PnxVbC8Lb2ag",
    ]

    @classmethod
    def _get_data_dir(cls):
        """Get data directory path using os instead of pathlib"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(current_dir), "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        return data_dir

    @classmethod
    def _get_settings_path(cls):
        """Get settings file path using os instead of pathlib"""
        return os.path.join(cls._get_data_dir(), "settings.json")

    @classmethod
    def load_settings(cls):
        """Load settings from JSON file"""
        try:
            settings_path = cls._get_settings_path()
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
                    # Update class attributes
                    for key, value in settings.items():
                        if hasattr(cls, key):
                            setattr(cls, key, value)
        except Exception as e:
            print(f"Error loading settings: {e}")

    @classmethod
    def save_settings(cls):
        """Save settings to JSON file"""
        try:
            settings_path = cls._get_settings_path()
            settings = {
                'CONCURRENT_BROWSERS': cls.CONCURRENT_BROWSERS,
                'CAPTCHA_SOLVE_ENABLED': cls.CAPTCHA_SOLVE_ENABLED,
                'CAPTCHA_MAX_RETRIES': cls.CAPTCHA_MAX_RETRIES,
                'HEADLESS': cls.HEADLESS,
                'DEFAULT_RESCAN_INTERVAL': cls.DEFAULT_RESCAN_INTERVAL,
                'AUDIO_CAPTCHA_ENABLED': cls.AUDIO_CAPTCHA_ENABLED,
            }
            
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

# Load settings on startup
Config.load_settings()