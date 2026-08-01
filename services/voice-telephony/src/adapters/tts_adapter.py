import os
import abc
import logging
from typing import AsyncGenerator

logger = logging.getLogger("voice_service.tts_adapter")


class BaseTTSAdapter(abc.ABC):
    """
    Abstract interface for all Text-to-Speech engines.
    Ensures vendor lock-in prevention: Any TTS service must implement synthesize_stream.
    """

    @abc.abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Convert input text into streaming raw audio bytes (mu-law / PCM)."""
        pass


class LocalTTSAdapter(BaseTTSAdapter):
    """Simple local fallback adapter for development and tests."""

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        payload = text.encode("utf-8")
        yield payload


class ElevenLabsTTSAdapter(BaseTTSAdapter):
    """
    TTS Adapter using ElevenLabs streaming API.
    Provides natural-sounding conversational voices with Egyptian Arabic accents.
    """

    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?output_format=ulaw_8000"

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        try:
            import httpx
        except Exception:
            logger.warning("httpx is not installed; falling back to local TTS adapter")
            yield text.encode("utf-8")
            return

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

                async for chunk in response.aiter_bytes():
                    yield chunk


def get_tts_adapter() -> BaseTTSAdapter:
    provider = os.getenv("TTS_PROVIDER", "elevenlabs").lower()
    if provider == "elevenlabs":
        try:
            return ElevenLabsTTSAdapter()
        except Exception:
            logger.warning("ElevenLabs TTS unavailable; falling back to local TTS adapter")
            return LocalTTSAdapter()
    else:
        raise ValueError(f"Unsupported TTS_PROVIDER: {provider}. Available: elevenlabs")