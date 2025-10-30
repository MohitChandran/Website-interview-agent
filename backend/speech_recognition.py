# import asyncio
# from deepgram import Deepgram
# from typing import Callable, Optional
# import json

# class SpeechRecognizer:
#     """Live speech recognition using Deepgram."""
    
#     def __init__(self, api_key: str):
#         """Initialize Deepgram client."""
#         self.api_key = api_key
#         self.deepgram = Deepgram(api_key)
#         self.connection = None
#         self.transcript_callback: Optional[Callable] = None
    
#     async def start_streaming(self, on_transcript: Callable):
#         """
#         Start live transcription streaming.
        
#         Args:
#             on_transcript: Callback function called with transcript text
#         """
#         self.transcript_callback = on_transcript
        
#         try:
#             # Create live transcription connection
#             self.connection = await self.deepgram.transcription.live({
#                 'punctuate': True,
#                 'interim_results': False,
#                 'language': 'en-US',
#                 'model': 'nova-2',
#                 'smart_format': True
#             })
            
#             # Set up event handlers
#             self.connection.registerHandler(
#                 self.connection.event.CLOSE,
#                 lambda _: print('Deepgram connection closed')
#             )
            
#             self.connection.registerHandler(
#                 self.connection.event.TRANSCRIPT_RECEIVED,
#                 self._on_message
#             )
            
#             print("Deepgram connection established")
            
#         except Exception as e:
#             print(f"Error starting Deepgram: {e}")
#             raise
    
#     def _on_message(self, message):
#         """Handle incoming transcription message."""
#         try:
#             data = json.loads(message)
            
#             # Extract transcript
#             if 'channel' in data:
#                 alternatives = data['channel']['alternatives']
#                 if alternatives and len(alternatives) > 0:
#                     transcript = alternatives[0].get('transcript', '')
#                     if transcript and self.transcript_callback:
#                         self.transcript_callback(transcript)
#         except Exception as e:
#             print(f"Error processing transcript: {e}")
    
#     async def send_audio(self, audio_data: bytes):
#         """Send audio data to Deepgram for transcription."""
#         if self.connection:
#             try:
#                 self.connection.send(audio_data)
#             except Exception as e:
#                 print(f"Error sending audio to Deepgram: {e}")
    
#     async def close(self):
#         """Close Deepgram connection."""
#         if self.connection:
#             try:
#                 await self.connection.finish()
#             except Exception as e:
#                 print(f"Error closing Deepgram: {e}")

import asyncio
from deepgram import Deepgram
from typing import Callable, Optional


class SpeechRecognizer:
    """Live speech recognition using Deepgram."""
    
    def __init__(self, api_key: str):
        """Initialize Deepgram client."""
        self.api_key = api_key
        self.deepgram = Deepgram(api_key)
        self.connection = None
        self.transcript_callback: Optional[Callable] = None
    
    async def start_streaming(self, on_transcript: Callable):
        """
        Start live transcription streaming.
        
        Args:
            on_transcript: Callback function called with transcript text
        """
        self.transcript_callback = on_transcript
        reconnect_attempts = 0
        max_reconnect_attempts = 5

        while reconnect_attempts < max_reconnect_attempts:
            try:
                self.connection = await self.deepgram.transcription.live({
                    'punctuate': True,
                    'interim_results': False,
                    'language': 'en-US',
                    'model': 'nova-2',
                    'smart_format': True,
                    'encoding': 'linear16',
                    'sample_rate': 16000,
                    'channels': 1,
                })
            
            # Set up event handlers
                self.connection.registerHandler(
                    self.connection.event.CLOSE,
                    lambda _: print('Deepgram connection closed')
                )
            
                self.connection.registerHandler(
                    self.connection.event.TRANSCRIPT_RECEIVED,
                    self._on_message
                )
            
                print("Deepgram connection established")
                break
            
            except Exception as e:
                reconnect_attempts += 1
                print(f"Error starting Deepgram (attempt {reconnect_attempts}): {e}")
                await asyncio.sleep(2 ** reconnect_attempts)  # exponential backoff
        if reconnect_attempts == max_reconnect_attempts:
            raise RuntimeError("Max reconnect attempts reached for Deepgram")

    def _on_message(self, message):
        """Handle incoming transcription message."""
        try:
            # Support both dict-like and JSON string payloads
            data = message
            if isinstance(message, (str, bytes)):
                import json
                try:
                    data = json.loads(message)
                except Exception:
                    # If not JSON, ignore
                    return

            channel = data.get('channel') or {}
            alternatives = channel.get('alternatives') or []
            if not alternatives:
                return

            transcript = alternatives[0].get('transcript', '')
            is_final = data.get('is_final') or (data.get('type') == 'transcript.completed')

            if transcript and self.transcript_callback:
                # We forward transcripts regardless of finality to support interruption detection
                try:
                    print(f"Deepgram transcript: {transcript}")
                except Exception:
                    pass
                self.transcript_callback(transcript)
        except Exception as e:
            print(f"Error processing transcript: {e}")
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram for transcription."""
        if self.connection:
            try:
                self.connection.send(audio_data)
            except Exception as e:
                print(f"Error sending audio to Deepgram: {e}")
    
    async def close(self):
        """Close Deepgram connection."""
        if self.connection:
            try:
                await self.connection.finish()
            except Exception as e:
                print(f"Error closing Deepgram: {e}")
