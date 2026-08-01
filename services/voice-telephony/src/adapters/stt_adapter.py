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
            # Send raw audio payload to OpenAI Whisper API
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", audio_bytes, "audio/wav"),
                language=language,
                prompt="محادثة باللغة العربية العامية المصرية"  # Context hint for Egyptian dialect
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"OpenAI Whisper STT error: {e}")
            return ""

def get_stt_adapter() -> BaseSTTAdapter:
    provider = os.getenv("STT_PROVIDER", "whisper").lower()
    if provider == "whisper":
        return OpenAIWhisperAdapter()
    else:
        # Only Whisper adapter is implemented here. Add other adapters explicitly.
        raise ValueError(f"Unsupported STT_PROVIDER: {provider}. Available: whisper")