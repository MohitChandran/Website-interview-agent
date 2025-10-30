import asyncio
from typing import Dict, List, Optional, Callable
from .text_generation import InterviewerAI
from .voice_synthesis import VoiceSynthesizer
from .speech_recognition import SpeechRecognizer
from .vad import VoiceActivityDetector
from .utils import InterviewTimer, encode_audio_to_base64
from config.config import config


class ConversationManager:
    """Manage the interview conversation flow."""
    
    def __init__(self, candidate_info: Dict, resume_data: Dict):
        """
        Initialize conversation manager.
        # ... (initialization is unchanged)
        """
        self.candidate_name = candidate_info.get("name", "Candidate")
        self.role = candidate_info.get("role", "the position")
        self.resume_data = resume_data
        
        # Initialize components
        self.ai_interviewer = InterviewerAI(config.GROQ_API_KEY)
        self.voice_synthesizer = VoiceSynthesizer(
            config.ELEVENLABS_API_KEY,
            config.ELEVENLABS_VOICE_ID
        )
        self.speech_recognizer = SpeechRecognizer(config.DEEPGRAM_API_KEY)
        self.vad = VoiceActivityDetector(
            sample_rate=config.SAMPLE_RATE,
            frame_duration_ms=config.FRAME_DURATION_MS,
            silence_threshold_seconds=config.SILENCE_THRESHOLD_SECONDS,
            vad_mode=config.VAD_MODE
        )
        
        # State tracking
        self.conversation_history: List[Dict] = []
        self.current_user_speech = ""
        self.is_ai_speaking = False
        self.interview_active = False
        self.timer = InterviewTimer(config.INTERVIEW_DURATION_MINUTES)
        self.response_in_progress = False  # Debounce/deduplication flag
        
        # WebSocket for sending messages
        self.websocket = None
        
        # Buffer for audio chunking to feed VAD with exact frame sizes
        self.audio_buffer = b""
        
        # Set up VAD callback
        self.vad.set_silence_callback(self._on_silence_detected)
    
    async def start_interview(self, websocket) -> Dict:
        """
        Start the interview and generate initial greeting.
        # ...
        """
        self.websocket = websocket
        self.interview_active = True
        self.timer.start()
        
        # Generate greeting
        greeting_text = self.ai_interviewer.start_interview(
            self.candidate_name,
            self.role,
            self.resume_data
        )
        
        # Synthesize greeting audio
        greeting_audio = self.voice_synthesizer.synthesize(greeting_text)
        greeting_audio_base64 = encode_audio_to_base64(greeting_audio)
        
        # Add to history
        self.conversation_history.append({
            "role": "interviewer",
            "text": greeting_text
        })
        
        # Start speech recognition
        await self.speech_recognizer.start_streaming(self._on_transcript_received)
        
        # 🌟 FIX 1a: Set AI speaking state for initial greeting
        self.is_ai_speaking = True
        
        return {
            "type": "ai_response",
            "text": greeting_text,
            "audio": greeting_audio_base64
        }
    
    async def process_audio_chunk(self, audio_data: bytes):
        """Process incoming audio chunk from candidate."""
        if not self.interview_active:
            return
        
        # Check if interview time expired
        if self.timer.is_expired():
            await self._end_interview()
            return
        
        # 🌟 FIX 1b & 2a: Send audio to Deepgram ALWAYS (for interruption)
        await self.speech_recognizer.send_audio(audio_data)
        
        # 🌟 FIX 1c: VAD should only look for silence when the AI is NOT speaking
        if self.is_ai_speaking:
            return
        
        # VAD processing logic starts here
        
        # Buffer incoming audio to ensure exact frame sizes are sent to VAD
        self.audio_buffer += audio_data
        
        frame_size = self.vad.frame_size
        
        # Process all complete frames in buffer
        while len(self.audio_buffer) >= frame_size:
            frame = self.audio_buffer[:frame_size]
            self.audio_buffer = self.audio_buffer[frame_size:]
            
            # Process frame with VAD for speech/silence detection
            self.vad.process_frame(frame)
    
    
    async def handle_websocket_message(self, message: dict):
        msg_type = message.get("type")
        if msg_type == "stop":
            await self.stop()
        elif msg_type == "ai_audio_completed":
            # The frontend signals the AI audio has finished playing
            self.is_ai_speaking = False
            print("AI audio completed, resuming VAD listening")
        else:
            # Handle other messages
            pass

    def _on_transcript_received(self, transcript: str):
        """Callback when transcript is received from Deepgram."""
        if transcript:
            # For debugging, always print transcripts
            print(f"Transcript received: {transcript}")

            if self.is_ai_speaking:
                # 🌟 FIX 2b: Interruption detected! Stop TTS and listen to the user.
                print("User interrupted AI speech! Stopping TTS.")
                # Use create_task to avoid blocking the Deepgram message thread
                asyncio.create_task(self._handle_interruption(transcript))
            
            else:
                # Normal accumulation when AI is not speaking
                self.current_user_speech += " " + transcript

    async def _handle_interruption(self, first_transcript: str):
        """Handles user interruption during AI speech."""
        
        # 1. Stop AI speaking state immediately
        self.is_ai_speaking = False

        # 2. Tell the frontend to stop the current audio playback
        if self.websocket:
            await self.websocket.send_json({"type": "stop_ai_audio"})
            print("Sent 'stop_ai_audio' signal to client.")
            
        # 3. Reset VAD state to ensure the ongoing speech is treated as a new utterance
        self.vad.reset()

        # 4. Use the first detected transcript to start the user's current speech
        self.current_user_speech = first_transcript.strip()
        print(f"Interruption handled. Current speech: '{self.current_user_speech}'")


    def _on_silence_detected(self):
        print("Silence callback triggered")
        if self.current_user_speech.strip() and not self.is_ai_speaking and not self.response_in_progress:
            print(f"Silence detected. User said: {self.current_user_speech}")
            asyncio.create_task(self._generate_and_send_response())
    
    async def _generate_and_send_response(self):
        if self.response_in_progress:
            print("[ConversationManager] WARNING: Response already in progress, skipping.")
            return
        self.response_in_progress = True
        print("[ConversationManager] AI response generation started")
        self.is_ai_speaking = True
        try:
            user_text = self.current_user_speech.strip()
            print(f"[ConversationManager] Sending to LLM: '{user_text}'")
            self.current_user_speech = ""  # CLEAR IMMEDIATELY to deduplicate
            self.vad.reset()

            self.conversation_history.append({
                "role": "candidate",
                "text": user_text
            })
            ai_response_text = self.ai_interviewer.generate_response(
                user_text, self.conversation_history)
            print(f"[ConversationManager] LLM responded: '{ai_response_text}'")
            self.conversation_history.append({"role": "interviewer", "text": ai_response_text})
            ai_audio = self.voice_synthesizer.synthesize(ai_response_text)
            print(f"[ConversationManager] Synthesized audio byte length: {len(ai_audio)}")
            ai_audio_base64 = encode_audio_to_base64(ai_audio)
            if self.websocket:
                print("[ConversationManager] Sending AI response over WebSocket")
                await self.websocket.send_json({
                    "type": "ai_response",
                    "text": ai_response_text,
                    "audio": ai_audio_base64
                })
                print("[ConversationManager] AI response sent")
        except Exception as e:
            print(f"[ConversationManager] Error during AI response generation: {e}")
        finally:
            self.response_in_progress = False

    async def _end_interview(self):
        """End the interview gracefully."""
        if not self.interview_active:
            return
        
        self.interview_active = False
        
        # Generate closing message
        closing_text = self.ai_interviewer.generate_closing(self.candidate_name)
        
        # Synthesize audio
        closing_audio = self.voice_synthesizer.synthesize(closing_text)
        closing_audio_base64 = encode_audio_to_base64(closing_audio)
        
        # Send to client
        if self.websocket:
            await self.websocket.send_json({
                "type": "interview_end",
                "text": closing_text,
                "audio": closing_audio_base64
            })
        
        # Close speech recognition
        await self.speech_recognizer.close()
    
    async def stop(self):
        """Stop the conversation and cleanup."""
        self.interview_active = False
        await self.speech_recognizer.close()
    
    async def test_silence_task(self):
        print("Testing silence trigger task...")
        await self._generate_and_send_response()

