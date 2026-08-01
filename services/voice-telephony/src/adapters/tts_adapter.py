import os
import abc
import logging
import httpx
from typing import AsyncGenerator

logger = logging.getLogger("voice_service.tts_adapter")


# ==============================================================================
# ABSTRACT BASE CLASS (The Adapter Interface)
# ==============================================================================
class BaseTTSAdapter(abc.ABC):
    """
    Abstract interface for all Text-to-Speech engines.
    Ensures vendor lock-in prevention: Any TTS service must implement synthesize_stream.
    """
    @abc.abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Convert input text into streaming raw audio bytes (mu-law / PCM)."""
        pass


# ==============================================================================
# OPTION 1: ElevenLabs Implementation
# ==============================================================================
class ElevenLabsTTSAdapter(BaseTTSAdapter):
    """
    TTS Adapter using ElevenLabs streaming API.
    Provides natural-sounding conversational voices with Egyptian Arabic accents.
    """
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default Voice ID
        # Output format specifically requested by Twilio Media Streams: u-law 8000Hz
        self.url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format=ulaw_8000"

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", self.url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    logger.error(f"ElevenLabs TTS failed with status {response.status_code}")
                    return

                # Stream incoming audio chunks immediately as they arrive from ElevenLabs
                async for chunk in response.aiter_bytes():
                    yield chunk

# ==============================================================================
# FACTORY FUNCTION (Selects Provider dynamically from .env)
# ==============================================================================
def get_tts_adapter() -> BaseTTSAdapter:
    provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
    if provider == "elevenlabs":
        return ElevenLabsTTSAdapter()
    else:
        # Only ElevenLabs implementation included here; add others as needed.
        raise ValueError(f"Unsupported TTS_PROVIDER: {provider}. Available: elevenlabs")