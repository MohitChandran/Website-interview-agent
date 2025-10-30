import base64
import time
from typing import Optional


def encode_audio_to_base64(audio_bytes: bytes) -> str:
    """Encode audio bytes to base64 string."""
    return base64.b64encode(audio_bytes).decode('utf-8')

def decode_audio_from_base64(audio_base64: str) -> bytes:
    """Decode base64 string to audio bytes."""
    return base64.b64decode(audio_base64)

def get_timestamp() -> str:
    """Get current timestamp as formatted string."""
    return time.strftime("%Y-%m-%d %H:%M:%S")

class InterviewTimer:
    """Simple timer for interview duration tracking."""
    
    def __init__(self, duration_minutes: int):
        self.duration_seconds = duration_minutes * 60
        self.start_time: Optional[float] = None
    
    def start(self):
        """Start the timer."""
        self.start_time = time.time()
    
    def is_expired(self) -> bool:
        """Check if interview time has expired."""
        if self.start_time is None:
            return False
        elapsed = time.time() - self.start_time
        return elapsed >= self.duration_seconds
    
    def remaining_seconds(self) -> int:
        """Get remaining seconds."""
        if self.start_time is None:
            return self.duration_seconds
        elapsed = time.time() - self.start_time
        remaining = max(0, self.duration_seconds - elapsed)
        return int(remaining)
