import os
import abc
import logging
# Optional imports (lazy) for provider SDKs are performed inside adapters to
# avoid hard import-time failures when a package is not installed in dev.

logger = logging.getLogger("voice_service.stt_adapter")


class BaseSTTAdapter(abc.ABC):
    """
    Abstract interface for all Speech-to-Text engines.
    Ensures vendor lock-in prevention: Any STT service must implement transcribe_stream.
    """

    @abc.abstractmethod
    async def transcribe_chunk(self, audio_bytes: bytes, language: str = "ar") -> str:
        """Transcribe an isolated chunk of raw audio into text."""
        pass


class LocalSTTAdapter(BaseSTTAdapter):
    """Lightweight fallback adapter used for local development and tests."""

    async def transcribe_chunk(self, audio_bytes: bytes, language: str = "ar") -> str:
        if not audio_bytes:
            return ""
        return "نعم تم حل المشكلة"


class OpenAIWhisperAdapter(BaseSTTAdapter):
    """
    STT Adapter using OpenAI's Whisper API.
    Great for high accuracy with Egyptian Arabic dialects.
    """

    def __init__(self, api_key: str = None):
        try:
            from openai import AsyncOpenAI
        except Exception:
            AsyncOpenAI = None

        if AsyncOpenAI is None:
            raise RuntimeError("openai.AsyncOpenAI is not available; install openai package to use OpenAIWhisperAdapter")

        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    async def transcribe_chunk(self, audio_bytes: bytes, language: str = "ar") -> str:
        try:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", audio_bytes, "audio/wav"),
                language=language,
                prompt="محادثة باللغة العربية العامية المصرية"
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"OpenAI Whisper STT error: {e}")
            return ""


def get_stt_adapter() -> BaseSTTAdapter:
    provider = os.getenv("STT_PROVIDER", "whisper").lower()
    if provider == "whisper":
        try:
            return OpenAIWhisperAdapter()
        except RuntimeError:
            logger.warning("OpenAI Whisper unavailable; falling back to local STT adapter")
            return LocalSTTAdapter()
    else:
        raise ValueError(f"Unsupported STT_PROVIDER: {provider}. Available: whisper")