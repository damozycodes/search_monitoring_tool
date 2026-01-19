import sys
import os
import asyncio
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
import qdarktheme

from ui.main_window_ui import MainWindow


def main():
    """Main application entry point"""
    
    # Create the QApplication
    app = QApplication(sys.argv)
    
    # Setup the dark theme
    # qdarktheme.setup_theme("dark", corner_shape="sharp")
    app.setStyleSheet(qdarktheme.load_stylesheet("dark"))

    
    # Create and show the main window immediately
    main_window = MainWindow()
    main_window.show()
    
    # Delay Playwright check to prevent UI freeze
    QTimer.singleShot(100, lambda: check_playwright_installation(main_window))
    
    # Execute the application
    sys.exit(app.exec())


def check_playwright_installation(main_window=None):
    """Check if Playwright browsers are installed, offer to install if not"""
    try:
        from playwright.async_api import async_playwright
        
        async def test_playwright():
            try:
                playwright = await async_playwright().start()
                # Quick test with short timeout
                browser = await playwright.chromium.launch(headless=True, timeout=10000)
                await browser.close()
                await playwright.stop()
                if main_window:
                    main_window.log_message("Playwright is properly installed.")
                print("Playwright is properly installed.")
            except Exception as e:
                print(f"Playwright browsers not installed: {e}")
                # Don't block UI - offer installation in background
                if main_window:
                    main_window.log_message("Playwright not installed properly. Please run: playwright install")
        
        # Create new event loop for the check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_playwright())
        loop.close()
        
    except ImportError:
        print("Playwright not installed. Please run: pip install playwright")
        if main_window:
            main_window.log_message("Playwright not installed. Please run: pip install playwright")


if __name__ == "__main__":
    main()