from elevenlabs import generate, set_api_key, Voice, VoiceSettings
from typing import Optional

class VoiceSynthesizer:
    """Convert text to speech using ElevenLabs API."""
    
    def __init__(self, api_key: str, voice_id: str):
        """
        Initialize ElevenLabs API.
        
        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID to use for synthesis
        """
        set_api_key(api_key)
        self.voice_id = voice_id
    
    def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech audio.
        
        Args:
            text: Text to convert to speech
        
        Returns:
            Audio bytes (MP3 format)
        """
        try:
            audio = generate(
                text=text,
                voice=Voice(
                    voice_id=self.voice_id,
                    settings=VoiceSettings(
                        stability=0.5,
                        similarity_boost=0.75,
                        style=0.0,
                        use_speaker_boost=True
                    )
                ),
                model="eleven_monolingual_v1"
            )
            
            
            return audio
            
        except Exception as e:
            print(f"Error synthesizing speech: {e}")
            raise
    
    def synthesize_streaming(self, text: str):
        """
        Stream audio generation (for future enhancement).
        
        Args:
            text: Text to convert to speech
        
        Yields:
            Audio chunks
        """
        try:
            audio_stream = generate(
                text=text,
                voice=Voice(
                    voice_id=self.voice_id,
                    settings=VoiceSettings(stability=0.5, similarity_boost=0.75)
                ),
                stream=True,
                model="eleven_monolingual_v1"
            )
            
            for chunk in audio_stream:
                yield chunk
                
        except Exception as e:
            print(f"Error in streaming synthesis: {e}")
            raise
