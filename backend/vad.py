import webrtcvad
import time
from typing import Callable, Optional

class VoiceActivityDetector:
    """Detect voice activity and silence using WebRTC VAD."""
    
    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 30, 
                 silence_threshold_seconds: float = 1, vad_mode: int = 2):
        """
        Initialize VAD.
        
        Args:
            sample_rate: Audio sample rate (8000, 16000, 32000, or 48000)
            frame_duration_ms: Frame duration (10, 20, or 30 ms)
            silence_threshold_seconds: Seconds of silence before triggering
            vad_mode: Aggressiveness mode (0-3, 3 is most aggressive)
        """
        self.vad = webrtcvad.Vad(vad_mode)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.silence_threshold_seconds = silence_threshold_seconds
        
        # Calculate frame size in bytes
        self.frame_size = int(sample_rate * frame_duration_ms / 1000) * 2  # 2 bytes per sample (16-bit)
        
        # Track speech/silence
        self.is_speaking = False
        self.silence_start: Optional[float] = None
        self.speech_detected = False
        self.consecutive_silence = 0
        self.consecutive_speech = 0
        self.silence_padding_frames = 3  # Require 3 consecutive silent frames to start silence duration
        self.speech_padding_frames = 3   # Require 3 consecutive speech frames to reset silence
        
        # Callback for silence detection
        self.on_silence_detected: Optional[Callable] = None
    
    def process_frame(self, frame: bytes) -> bool:
        """
        Process an audio frame and detect voice activity.
        Returns True if speech detected, False if silence
        """
        if len(frame) != self.frame_size:
            print(f"[VAD] Incorrect frame size, skipping")
            return False
        try:
            is_speech = self.vad.is_speech(frame, self.sample_rate)
            if is_speech:
                self.consecutive_speech += 1
                self.consecutive_silence = 0
                if self.consecutive_speech >= self.speech_padding_frames:
                    self.is_speaking = True
                    self.speech_detected = True
                    self.silence_start = None  # Only reset after enough confirmed speech
                return True
            else:
                self.consecutive_silence += 1
                self.consecutive_speech = 0
                if not self.speech_detected:
                    return False
                if self.consecutive_silence == self.silence_padding_frames and self.silence_start is None:
                    self.silence_start = time.time()
                    print("[VAD] Silence started")
                if self.silence_start is not None:
                    silence_duration = time.time() - self.silence_start
                    print(f"[VAD] Silence duration: {silence_duration:.2f} s")
                    if silence_duration >= self.silence_threshold_seconds:
                        print("[VAD] Silence threshold reached, triggering callback")
                        if self.on_silence_detected:
                            self.on_silence_detected()
                        self.reset()
                return False
        except Exception as e:
            print(f"VAD error: {e}")
            return False

    def reset(self):
        """Reset VAD state."""
        self.is_speaking = False
        self.silence_start = None
        self.speech_detected = False
        self.consecutive_silence = 0
        self.consecutive_speech = 0
    
    def set_silence_callback(self, callback: Callable):
        """Set callback function to be called when silence is detected."""
        self.on_silence_detected = callback
