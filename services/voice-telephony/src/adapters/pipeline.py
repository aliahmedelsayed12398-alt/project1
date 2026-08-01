import logging
import base64
# Use relative imports to work when package is used as a module or run in-place
from .stt_adapter import get_stt_adapter
from .tts_adapter import get_tts_adapter

logger = logging.getLogger("voice_service.pipeline")


class VoiceAudioPipeline:
    """
    Orchestrates the continuous flow between Telephony WebSockets, STT, Dialogue Logic, and TTS.
    """
    def __init__(self):
        # Dynamically load whichever provider is set in .env
        self.stt = get_stt_adapter()
        self.tts = get_tts_adapter()

    async def process_incoming_audio_chunk(self, raw_mulaw_bytes: bytes) -> str:
        """
        Takes raw mulaw audio bytes from Twilio WebSocket,
        converts them to text via the active STT provider.
        """
        if not raw_mulaw_bytes:
            return ""
        
        # 1. Pass payload to STT Adapter
        transcribed_text = await self.stt.transcribe_chunk(raw_mulaw_bytes, language="ar")
        if transcribed_text:
            logger.info(f"[Customer Spoke]: {transcribed_text}")
        
        return transcribed_text

    async def generate_outgoing_audio_chunks(self, response_text: str):
        """
        Takes dynamic Arabic text response from Dialogue Controller,
        converts it to streaming audio via the active TTS provider,
        and yields base64-encoded audio payloads ready for Twilio WebSocket.
        """
        logger.info(f"[System Responding]: {response_text}")

        # 1. Stream raw audio bytes from active TTS provider
        async for audio_chunk in self.tts.synthesize_stream(response_text):
            # 2. Encode binary audio as base64 string (required by Twilio Media Stream API)
            base64_audio = base64.b64encode(audio_chunk).decode("utf-8")
            
            # 3. Format into Twilio JSON WebSocket payload
            payload = {
                "event": "media",
                "media": {
                    "payload": base64_audio
                }
            }
            yield payload