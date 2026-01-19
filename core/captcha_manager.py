# captcha_manager.py
import asyncio
import time
import speech_recognition as sr
import pyaudio
import os
from typing import Optional, Dict
from PySide6.QtCore import QObject, Signal

from .config import Config


class CaptchaManagerSignals(QObject):
    """Signals for CAPTCHA operations"""
    captcha_solved = Signal(dict)  # captcha result
    captcha_failed = Signal(str, str)  # browser_id, error
    log_message = Signal(str)  # log message


class AudioCaptchaSolver:
    """Solve audio CAPTCHAs using speech recognition"""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        try:
            self.audio = pyaudio.PyAudio()
        except Exception as e:
            print(f"PyAudio initialization warning: {e}")
        
    async def solve_audio_captcha(self, page):
        """Solve audio CAPTCHA by playing and transcribing the audio"""
        try:
            # Check if audio challenge is available
            audio_button = await page.query_selector('#recaptcha-audio-button')
            if audio_button and await audio_button.is_visible():
                await audio_button.click()
                await asyncio.sleep(3)
            
            # Get the audio source
            audio_src = await page.evaluate("""
                () => {
                    const audio = document.querySelector('#audio-source');
                    return audio ? audio.src : null;
                }
            """)
            
            if not audio_src:
                # Alternative method to get audio source
                audio_src = await page.evaluate("""
                    () => {
                        // Look for any audio elements in recaptcha
                        const audioElement = document.querySelector('audio');
                        return audioElement ? audioElement.src : null;
                    }
                """)
                if not audio_src:
                    return False
                
            # Download and process audio
            audio_content = await page.evaluate("""
                async (audioSrc) => {
                    try {
                        const response = await fetch(audioSrc);
                        const buffer = await response.arrayBuffer();
                        return Array.from(new Uint8Array(buffer));
                    } catch (e) {
                        console.error('Audio download failed:', e);
                        return null;
                    }
                }
            """, audio_src)
            
            if not audio_content:
                return False
            
            # Save audio to temporary file
            temp_audio = "captcha_audio.wav"
            try:
                with open(temp_audio, 'wb') as f:
                    f.write(bytes(audio_content))
            except Exception as e:
                return False
            
            # Transcribe audio using speech recognition
            text = await self.transcribe_audio(temp_audio)
            
            # Clean up temp file
            try:
                os.remove(temp_audio)
            except:
                pass
            
            if text:
                # Enter the transcribed text
                input_field = await page.query_selector('#audio-response')
                if not input_field:
                    # Try alternative selectors
                    input_field = await page.query_selector('input[type="text"]')
                
                if input_field:
                    await input_field.fill(text)
                    await asyncio.sleep(1)
                    
                    # Submit the response
                    verify_button = await page.query_selector('#recaptcha-verify-button')
                    if not verify_button:
                        verify_button = await page.query_selector('button[type="submit"]')
                    
                    if verify_button:
                        await verify_button.click()
                        await asyncio.sleep(3)
                        
                        # Check if CAPTCHA was solved successfully
                        if not await self.is_captcha_still_present(page):
                            return True
            
            return False
            
        except Exception as e:
            return False
    
    async def transcribe_audio(self, audio_file_path):
        """Transcribe audio file to text using speech recognition"""
        try:
            with sr.AudioFile(audio_file_path) as source:
                # Adjust for ambient noise and record
                self.recognizer.adjust_for_ambient_noise(source)
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                return text.strip()
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            pass
        except Exception as e:
            pass
        
        return None
    
    async def is_captcha_still_present(self, page):
        """Check if CAPTCHA is still present on the page"""
        try:
            captcha_element = await page.query_selector('.g-recaptcha, #recaptcha, iframe[src*="recaptcha"]')
            return captcha_element is not None
        except:
            return False


class CaptchaManager(QObject):
    """Manages CAPTCHA solving operations using audio CAPTCHA solving"""
    
    def __init__(self):
        super().__init__()
        self.signals = CaptchaManagerSignals()
        self.active_solvers = {}  # Track active solvers by browser_id
        self.audio_solver = AudioCaptchaSolver()
        
    async def is_captcha_or_block(self, page) -> bool:
        """Detect CAPTCHA or blocking pages"""
        try:
            url = page.url.lower()
            captcha_indicators = ["sorry", "captcha", "/sorry/", "recaptcha"]
            
            if any(indicator in url for indicator in captcha_indicators):
                return True
                
            # Check for visible CAPTCHA elements
            captcha_selectors = [
                ".g-recaptcha",
                "#recaptcha",
                "iframe[src*='recaptcha']",
                "div.rc-",
                ".captcha",
                "#captcha"
            ]
            
            for selector in captcha_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        return True
                except:
                    continue
                    
            # Check page content for blocking messages
            try:
                body_text = await page.inner_text("body", timeout=2000)
                body_lower = body_text.lower()
                blocking_phrases = [
                    "unusual traffic",
                    "are you a robot", 
                    "recaptcha",
                    "solve the captcha",
                    "to continue",
                    "automated requests",
                    "confirm you are human"
                ]
                
                if any(phrase in body_lower for phrase in blocking_phrases):
                    return True
            except:
                pass
                
            return False
            
        except Exception:
            return False

    async def wait_for_manual_captcha_clear(self, page, label: str, timeout_sec: int) -> bool:
        """
        Wait for manual CAPTCHA solving with user interaction
        """
        self.signals.log_message.emit(f"[{label}] CAPTCHA/block detected. Please solve in browser window.")
        
        deadline = asyncio.get_event_loop().time() + timeout_sec
        
        self.signals.log_message.emit(f"[{label}] You have {timeout_sec} seconds to solve CAPTCHA manually...")
        self.signals.log_message.emit(f"[{label}] Script will auto-continue when CAPTCHA is cleared.")
        
        # Poll for CAPTCHA resolution
        while asyncio.get_event_loop().time() < deadline:
            if not await self.is_captcha_or_block(page):
                self.signals.log_message.emit(f"[{label}] CAPTCHA appears cleared. Continuing...")
                return True
            await asyncio.sleep(3)
        
        self.signals.log_message.emit(f"[{label}] Timeout waiting for CAPTCHA resolution")
        return False

    async def solve_captcha_automatically(self, page, browser_id: int) -> bool:
        """
        Solve CAPTCHA automatically using audio challenge method
        """
        try:
            # Check if we're on a CAPTCHA page
            if not await self.is_captcha_or_block(page):
                return False
                
            self.signals.log_message.emit(f"Browser {browser_id}: Attempting automatic CAPTCHA solving via audio challenge...")
            
            # First try to find and click the audio challenge button
            audio_button_selectors = [
                '#recaptcha-audio-button',
                '.rc-button-audio',
                'button[title*="audio" i]',
                'button[aria-label*="audio" i]',
                'button[id*="audio"]'
            ]
            
            audio_button = None
            for selector in audio_button_selectors:
                audio_button = await page.query_selector(selector)
                if audio_button and await audio_button.is_visible():
                    break
                audio_button = None
            
            if audio_button:
                await audio_button.click()
                await asyncio.sleep(3)
                
                # Now solve the audio CAPTCHA
                success = await self.audio_solver.solve_audio_captcha(page)
                if success:
                    self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA solved automatically via audio challenge!")
                    return True
                else:
                    self.signals.log_message.emit(f"Browser {browser_id}: Audio CAPTCHA solving failed")
            else:
                self.signals.log_message.emit(f"Browser {browser_id}: Audio challenge button not found")
                
            return False
            
        except Exception as e:
            self.signals.log_message.emit(f"Browser {browser_id}: Auto CAPTCHA solving failed: {e}")
            return False

    async def handle_captcha_flow(self, page, browser_id: int, context_name: str) -> bool:
        """Handle CAPTCHA detection and solving flow"""
        if await self.is_captcha_or_block(page):
            self.signals.log_message.emit(f"Browser {browser_id}: [{context_name}] CAPTCHA detected")
            
            # Try automatic solving first if enabled
            if Config.AUDIO_CAPTCHA_ENABLED:
                if await self.solve_captcha_automatically(page, browser_id):
                    self.signals.log_message.emit(f"Browser {browser_id}: [{context_name}] CAPTCHA solved automatically!")
                    return True
                else:
                    self.signals.log_message.emit(f"Browser {browser_id}: [{context_name}] Automatic solving failed")
            
            # Fall back to manual solving if automatic fails or is disabled
            if Config.CAPTCHA_SOLVE_ENABLED:
                self.signals.log_message.emit(f"Browser {browser_id}: [{context_name}] Falling back to manual solving...")
                return await self.wait_for_manual_captcha_clear(page, f"Browser {browser_id}", Config.CAPTCHA_TIMEOUT)
            else:
                self.signals.log_message.emit(f"Browser {browser_id}: [{context_name}] CAPTCHA solving disabled, waiting briefly...")
                await asyncio.sleep(5)
                return not await self.is_captcha_or_block(page)
        
        return True

    async def solve_recaptcha_if_present(self, browser_id: int, page, step_name: str) -> bool:
        """Attempt to solve reCAPTCHA if present using audio method"""
        if not Config.CAPTCHA_SOLVE_ENABLED and not Config.AUDIO_CAPTCHA_ENABLED:
            self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA solving disabled")
            return False
            
        if browser_id in self.active_solvers:
            self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA solving already in progress")
            return False
            
        self.active_solvers[browser_id] = True
        self.signals.log_message.emit(f"Browser {browser_id}: Checking for CAPTCHA at {step_name}...")
        
        try:
            return await self.handle_captcha_flow(page, browser_id, step_name)
                
        except Exception as e:
            error_msg = str(e)
            self.signals.log_message.emit(f"Browser {browser_id}: CAPTCHA solving failed at {step_name}: {error_msg}")
            self.signals.captcha_failed.emit(str(browser_id), error_msg)
            return False
        finally:
            self.active_solvers.pop(browser_id, None)

    async def _is_captcha_page(self, page) -> bool:
        """Check if current page is a CAPTCHA page"""
        try:
            current_url = page.url.lower()
            return "sorry" in current_url or "captcha" in current_url
        except:
            return False

    async def wait_for_recaptcha_or_continue(self, browser_id: int, page, timeout=30000) -> bool:
        """Wait for reCAPTCHA to appear or continue after timeout"""
        try:
            self.signals.log_message.emit(f"Browser {browser_id}: Waiting for potential CAPTCHA to appear...")
            await page.wait_for_selector('iframe[src*="recaptcha"], .g-recaptcha, #captcha, .captcha', timeout=timeout)
            return True
        except:
            self.signals.log_message.emit(f"Browser {browser_id}: No CAPTCHA appeared within timeout, continuing...")
            return False

    async def solve_recaptcha_v2(self, browser_id: int, page, proxy: str = None) -> bool:
        """Legacy method for backward compatibility"""
        return await self.solve_recaptcha_if_present(browser_id, page, "legacy_method")
    
    async def handle_captcha_scenarios(self, browser_id: int, page, scenario: str = "search") -> bool:
        """Handle different CAPTCHA scenarios"""
        try:
            if scenario == "homepage":
                # Scenario 1: Check for immediate CAPTCHA on homepage
                immediate_captcha = await self.solve_recaptcha_if_present(browser_id, page, "homepage")
                
                if immediate_captcha:
                    # If CAPTCHA was solved on homepage, wait a bit
                    await asyncio.sleep(3)
                    return True
                else:
                    return False
                    
            elif scenario == "post_search":
                # Scenario 2: Wait and check for CAPTCHA after search
                self.signals.log_message.emit(f"Browser {browser_id}: Checking for CAPTCHA after search...")
                post_search_captcha = await self.wait_for_recaptcha_or_continue(browser_id, page, 60000)
                
                if post_search_captcha:
                    await asyncio.sleep(5)
                    return await self.solve_recaptcha_if_present(browser_id, page, "post-search")
                return True
                
            else:
                # Generic scenario - just try to solve if present
                return await self.solve_recaptcha_if_present(browser_id, page, scenario)
                
        except Exception as e:
            self.signals.log_message.emit(f"Browser {browser_id}: Error in CAPTCHA scenario {scenario}: {e}")
            return False