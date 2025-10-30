import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    
    # Interview settings
    INTERVIEW_DURATION_MINUTES = 10
    SILENCE_THRESHOLD_SECONDS = 1
    
    # Audio settings
    SAMPLE_RATE = 16000
    FRAME_DURATION_MS = 30
    VAD_MODE = 2  # Aggressiveness (0-3, 3 is most aggressive)

config = Config()
