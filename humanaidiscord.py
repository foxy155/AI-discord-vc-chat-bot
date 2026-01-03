
import threading
import time
import requests
import json
import pyttsx3
import re
import os
from collections import deque
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==================== CONFIGURATION ====================
# DISCORD SETUP
DISCORD_TOKEN = "replace me"  # replace with discord token when using
VOICE_CHANNEL_URL = "replace me" # replace with discord  channel to start with u can change it later on

# OBS SETUP (CRITICAL: Must match OBS LocalVocal output EXACTLY)
TRANSCRIPT_FILE = "C:/obs_transcript.txt" # can replace with whatever file you want make sure its the same as in the local vocal plugin

# AI SETUP
OLLAMA_URL = "http://localhost:11434/api/generate" # can repalce according to what you have set up
OLLAMA_MODEL = "qwen2.5:0.5b-instruct"  # the AI i used can use any model u want would recommend this one cuz its fast

# CONVERSATION TIMING (tweeek to fit your use case)
SILENCE_THRESHOLD = 0.1      # Wait X seconds after speech ends before responding
SELF_IGNORE_TIME = 5.5       # Ignore own speech for X seconds after speaking
MAX_RESPONSE_WORDS = 30      # Maximum words in AI response
MIN_INPUT_WORDS = 2          # Minimum words to trigger a response
POLL_DELAY = 0.1             # How often to check for new input (seconds)

# TTS SETTINGS
TTS_RATE = 180               # Speech speed adjust as needed
TTS_VOLUME = 1.0

# ADVANCED AI SETTINGS
ENABLE_CONTEXT_MEMORY = True # Remember previous conversation
MAX_CONVERSATION_ITEMS = 10   # How many lines to remember
# =======================================================

class DiscordVoiceAssistant:
    """
    Main AI assistant class that handles Discord joining, transcription,
    AI processing, and speech synthesis.
    """

    def __init__(self):
        """Initialize all components of the assistant."""
        self.driver = None
        self.running = True

        # Conversation state tracking
        self.last_file_position = 0
        self.last_speech_time = 0
        self.last_ai_response = ""
        self.is_speaking = False
        self.last_input_time = 0
        self.ignore_until = 0

        # Conversation memory for context
        self.conversation_history = deque(maxlen=MAX_CONVERSATION_ITEMS)

        print("=" * 60)
        print("DISCORD AI VOICE ASSISTANT - FINAL VERSION")
        print("=" * 60)
        print(f"[Conversation] Waits {SILENCE_THRESHOLD}s of silence before replying")
        print(f"[Anti-Loop] Ignores own speech for {SELF_IGNORE_TIME}s")
        print(f"[AI] Using: {OLLAMA_MODEL} (max {MAX_RESPONSE_WORDS} words)")
        print(f"[Timing] Polling every {POLL_DELAY}s for new input")

    def login_to_discord(self):
        """
        Log into Discord web client using token injection.
        WARNING: Using user tokens violates Discord's Terms of Service.
        """
        print("\n[1/4] LOGGING INTO DISCORD...")

        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            print(f"[ERROR] ChromeDriver not found: {e}")
            print("\nTO FIX:")
            print("1. pip install selenium")
            print("2. Download ChromeDriver from: https://chromedriver.chromium.org/")
            print("3. Place chromedriver.exe in PATH or this script's folder")
            return False

        # Inject Discord token via localStorage
        print("[Browser] Injecting Discord token...")
        self.driver.get("https://discord.com/login")

        token_script = f"""
        function login(token) {{
            setInterval(() => {{
                document.body.appendChild(document.createElement('iframe')).contentWindow.localStorage.token = `"${{token}}"`;
            }}, 50);
            setTimeout(() => {{ location.reload(); }}, 500);
        }}
        login("{DISCORD_TOKEN}");
        """
        self.driver.execute_script(token_script)
        time.sleep(3)

        return True

    def join_voice_channel(self):
        """Navigate to and join the specified Discord voice channel."""
        print("\n[2/4] JOINING VOICE CHANNEL...")

        # Parse server and channel IDs from URL
        match = re.search(r'channels/(\d+)/(\d+)', VOICE_CHANNEL_URL)
        if not match:
            print(f"[ERROR] Invalid URL format. Expected: https://discord.com/channels/SERVER_ID/CHANNEL_ID")
            return False

        server_id, channel_id = match.groups()

        # Navigate to the voice channel
        self.driver.get(VOICE_CHANNEL_URL)
        time.sleep(2)

        try:
            # Try to find and click the join button (Discord UI may vary)
            join_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(., 'Join Voice') or contains(., 'Connect') or contains(., 'Join Call')]"))
            )
            join_button.click()
            print("[Success] Joined voice channel!")

            # Audio setup instructions
            print("\n" + "=" * 60)
            print("MANUAL AUDIO SETUP REQUIRED:")
            print("1. In Discord web, click the speaker/headphone icon")
            print("2. Set 'INPUT DEVICE' to: CABLE Output")
            print("3. Set 'OUTPUT DEVICE' to: CABLE Input")
            print("(Adjust names based on your virtual audio cable)")
            print("=" * 60 + "\n")

            return True

        except Exception as e:
            print(f"[Warning] Could not auto-join: {e}")
            print("You may need to join the voice channel manually.")
            return True  # Continue anyway

    def read_new_transcription(self):
        """
        Read only new content from the OBS transcription file.
        Includes anti-loop protection to ignore the AI's own speech.
        """
        try:
            current_time = time.time()

            # Don't read while speaking or during ignore period
            if self.is_speaking or current_time < self.ignore_until:
                return None

            # Check if file exists
            if not os.path.exists(TRANSCRIPT_FILE):
                return None

            # Get file size and read only new content
            current_size = os.path.getsize(TRANSCRIPT_FILE)
            if current_size <= self.last_file_position:
                return None

            with open(TRANSCRIPT_FILE, 'r', encoding='utf-8') as f:
                f.seek(self.last_file_position)
                new_text = f.read(current_size - self.last_file_position)
                self.last_file_position = current_size

                if new_text.strip():
                    # Get the most recent line
                    lines = [line.strip() for line in new_text.split('\n') if line.strip()]
                    if lines:
                        latest_line = lines[-1]

                        # Ignore very short inputs
                        if len(latest_line.split()) < MIN_INPUT_WORDS:
                            return None

                        # Check if this might be the AI's own speech (anti-loop)
                        if self._is_likely_ai_speech(latest_line):
                            print(f"[Anti-Loop] Ignoring own speech: {latest_line[:40]}...")
                            self.ignore_until = time.time() + SELF_IGNORE_TIME
                            return None

                        # Update timestamp and return
                        self.last_input_time = time.time()
                        return latest_line

            return None

        except Exception as e:
            print(f"[Transcription Error] {e}")
            return None

    def _is_likely_ai_speech(self, text):
        """Check if text appears to be the AI's own speech."""
        text_lower = text.lower()

        # Check against recent AI response
        if self.last_ai_response:
            last_lower = self.last_ai_response.lower()
            # Simple similarity check
            if last_lower in text_lower or text_lower in last_lower:
                return True

        # Common AI phrases to ignore
        ai_phrases = [
            "how can i assist",
            "how can i help",
            "what can i do",
            "hello there",
            "hi there",
            "hey there",
            "i'm here",
            "i am here",
            "that's interesting",
            "tell me more"
        ]

        for phrase in ai_phrases:
            if phrase in text_lower:
                return True

        return False

    def get_ai_response(self, user_text):
        """
        Get a response from the local Ollama AI with context awareness
        and complete sentence generation.
        """
        # Build conversation context if enabled
        context = ""
        if ENABLE_CONTEXT_MEMORY and self.conversation_history:
            context = "Recent conversation:\n" + "\n".join(list(self.conversation_history)[-3:]) + "\n"

        # System prompt for natural, complete responses
        system_prompt = (
            "You are a friendly voice assistant in a Discord call. "
            f"Respond in 1-2 COMPLETE sentences (max {MAX_RESPONSE_WORDS} words). "
            "Be conversational, natural, and finish your thoughts completely. "
            "Don't cut off mid-sentence."
        )

        # Format for Qwen model
        formatted_prompt = (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{context}User: {user_text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": formatted_prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,      # Balanced creativity/predictability
                "num_predict": 70,       # Enough tokens for complete sentences
                "top_p": 0.9,
                "repeat_penalty": 2.1,   # Discourage repetition
                "stop": ["<|im_end|>", "\n\n", "User:", "user:"]  # Natural stops only
            }
        }

        try:
            start_time = time.time()
            response = requests.post(OLLAMA_URL, json=payload, timeout=8)
            ai_time = time.time() - start_time

            if response.status_code == 200:
                raw_response = response.json().get('response', '').strip()

                # Clean up model artifacts
                clean_response = raw_response.replace('<|im_end|>', '').replace('<|im_start|>', '').strip()

                # Ensure complete sentence with proper punctuation
                clean_response = self._ensure_complete_sentence(clean_response)

                # Store in conversation history
                if ENABLE_CONTEXT_MEMORY:
                    self.conversation_history.append(f"User: {user_text}")
                    self.conversation_history.append(f"AI: {clean_response}")

                self.last_ai_response = clean_response
                print(f"[AI] {clean_response} ({ai_time:.1f}s)")
                return clean_response

        except requests.exceptions.Timeout:
            print("[AI Error] Request timed out - Ollama may be busy")
        except Exception as e:
            print(f"[AI Error] {e}")

        return None

    def _ensure_complete_sentence(self, text):
        """Ensure the AI response ends with proper punctuation."""
        if not text:
            return text

        # Find the last sentence boundary
        last_period = text.rfind('.')
        last_exclamation = text.rfind('!')
        last_question = text.rfind('?')
        last_boundary = max(last_period, last_exclamation, last_question)

        # If no punctuation found, add period
        if last_boundary == -1:
            text = text + '.'
        # If ends with punctuation, ensure it's the end
        elif last_boundary != len(text) - 1:
            # Find the actual end of the last sentence
            sentences = re.split(r'[.!?]', text)
            if sentences and sentences[0].strip():
                text = sentences[0].strip()
                # Add back the appropriate punctuation
                if text and text[-1] not in ['.', '!', '?']:
                    text = text + '.'

        # Enforce word limit while keeping sentences intact
        words = text.split()
        if len(words) > MAX_RESPONSE_WORDS:
            # Try to cut at sentence boundary
            shortened = ' '.join(words[:MAX_RESPONSE_WORDS])
            # Find the last punctuation in the shortened version
            last_punct = max(shortened.rfind('.'), shortened.rfind('!'), shortened.rfind('?'))
            if last_punct != -1:
                text = shortened[:last_punct + 1]
            else:
                text = shortened + '...'

        return text

    def speak_text(self, text):
        """
        Convert text to speech using pyttsx3 in a separate thread.
        This prevents blocking and ensures TTS works reliably every time.
        """
        if not text or self.is_speaking:
            return

        def tts_worker(speech_text):
            """Worker function that runs TTS in a background thread."""
            try:
                self.is_speaking = True
                self.last_speech_time = time.time()

                # Set ignore period to prevent self-reply loops
                self.ignore_until = time.time() + SELF_IGNORE_TIME

                # Create new TTS engine instance (fixes 'works once' issue)
                engine = pyttsx3.init()
                engine.setProperty('rate', TTS_RATE)
                engine.setProperty('volume', TTS_VOLUME)

                # Small delay for stability
                time.sleep(0.05)

                # Speak the text
                engine.say(speech_text)
                engine.runAndWait()

                # Small delay after speaking
                time.sleep(0.1)

            except Exception as e:
                print(f"[TTS Error] {e}")
            finally:
                self.is_speaking = False

        # Start TTS in background thread
        thread = threading.Thread(target=tts_worker, args=(text,), daemon=True)
        thread.start()

        print(f"[TTS] Speaking: {text[:50]}..." if len(text) > 50 else f"[TTS] Speaking: {text}")

    def should_respond_now(self):
        """
        Determine if enough silence has passed to respond.
        Prevents interrupting and ensures natural conversation flow.
        """
        current_time = time.time()

        # Don't respond if currently speaking
        if self.is_speaking:
            return False

        # Check if enough time has passed since last input
        time_since_input = current_time - self.last_input_time
        if time_since_input < SILENCE_THRESHOLD:
            return False

        # Check if enough time has passed since we last spoke
        time_since_speech = current_time - self.last_speech_time
        if time_since_speech < SILENCE_THRESHOLD:
            return False

        return True

    def main_processing_loop(self):
        """
        Main loop that handles the conversation flow:
        1. Reads new transcription from OBS
        2. Waits for appropriate silence
        3. Gets AI response
        4. Speaks response via TTS
        """
        print("\n[4/4] STARTING CONVERSATION ENGINE...")
        print("=" * 60)
        print("🎤 AI ASSISTANT IS NOW ACTIVE")
        print(f"Will wait {SILENCE_THRESHOLD}s of silence before responding")
        print("Speak into the call to test. Press Ctrl+C to stop.")
        print("=" * 60 + "\n")

        # State for pending responses
        pending_input = None
        pending_time = 0
        status_counter = 0

        while self.running:
            try:
                # 1. Check for new transcription
                new_text = self.read_new_transcription()

                if new_text:
                    print(f"[Input] {new_text}")
                    pending_input = new_text
                    pending_time = time.time()
                    status_counter = 0

                # 2. Process pending input when appropriate
                current_time = time.time()
                if pending_input and self.should_respond_now():
                    silence_elapsed = current_time - pending_time

                    if silence_elapsed >= SILENCE_THRESHOLD:
                        print(f"[Timing] Responding after {silence_elapsed:.1f}s of silence")

                        # 3. Get AI response
                        ai_response = self.get_ai_response(pending_input)

                        # 4. Speak if we got a valid response
                        if ai_response:
                            self.speak_text(ai_response)

                        # Clear pending input
                        pending_input = None

                # 5. Status updates
                status_counter += 1
                if status_counter >= 50:  # ~5 seconds
                    if pending_input:
                        waiting_time = current_time - pending_time
                        time_left = max(0, SILENCE_THRESHOLD - waiting_time)
                        print(f"[Status] Waiting {time_left:.1f}s more silence to respond...")
                    else:
                        print("[Status] Listening for conversation...")
                    status_counter = 0

                # 6. Brief sleep to prevent CPU overuse
                time.sleep(POLL_DELAY)

            except KeyboardInterrupt:
                print("\n[System] Interrupt received, shutting down...")
                break
            except Exception as e:
                print(f"[Loop Error] {e}")
                time.sleep(1)

    def start(self):
        """Start the complete AI assistant system."""

        # Pre-flight checks
        print("\n[0/4] PRE-FLIGHT CHECKS...")

        # Check Ollama
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                if OLLAMA_MODEL in model_names:
                    print("  ✓ Ollama is running with correct model")
                else:
                    print(f"  ✗ Model '{OLLAMA_MODEL}' not found")
                    print(f"    Run: ollama pull {OLLAMA_MODEL}")
                    return
            else:
                print("  ✗ Ollama not responding correctly")
                print("    Start Ollama with: ollama serve")
                return
        except:
            print("  ✗ Cannot connect to Ollama")
            print("    Make sure 'ollama serve' is running in another terminal")
            return

        # Check OBS transcription file
        if os.path.exists(TRANSCRIPT_FILE):
            print(f"  ✓ OBS transcription file found: {TRANSCRIPT_FILE}")
            self.last_file_position = os.path.getsize(TRANSCRIPT_FILE)
        else:
            print(f"  ⚠ OBS file not found: {TRANSCRIPT_FILE}")
            print("    Make sure OBS with LocalVocal is running")

        # Start browser and join Discord
        if not self.login_to_discord():
            return

        self.join_voice_channel()

        # Give user time to set up audio
        print("\n[3/4] FINAL SETUP...")
        print("Please complete the Discord audio setup above.")
        print("Starting in 5 seconds...")
        time.sleep(5)

        # Start main processing loop
        self.main_processing_loop()

    def stop(self):
        """Clean shutdown of all components."""
        print("\n" + "=" * 60)
        print("SHUTTING DOWN AI ASSISTANT...")
        print("=" * 60)

        self.running = False

        if self.driver:
            try:
                print("[Cleanup] Closing browser...")
                self.driver.quit()
            except:
                pass

        print("[Complete] AI assistant has been stopped.")
        print("Thank you for using Discord AI Assistant!")


# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":

    print("Discord AI Voice Assistant - Final Version")
    print("This tool violates Discord's Terms of Service.")
    print("Use at your own risk on test accounts only.\n")

    # Create and start assistant
    assistant = DiscordVoiceAssistant()

    try:
        assistant.start()
    except KeyboardInterrupt:
        print("\n[System] Stopped by user")
    except Exception as e:
        print(f"[Fatal Error] {e}")
        import traceback
        traceback.print_exc()
    finally:
        assistant.stop()