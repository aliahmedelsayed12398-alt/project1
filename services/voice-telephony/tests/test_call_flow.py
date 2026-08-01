import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.adapters.pipeline import VoiceAudioPipeline
from src.controllers.dialogue_state import ArabicDialogueController


@pytest.mark.asyncio
async def test_end_to_end_audio_pipeline_latency():
    """
    Verifies that the audio pipeline transcribes customer audio and yields TTS response chunks
    within the strict 1200ms target threshold.
    """
    pipeline = VoiceAudioPipeline()
    dialogue = ArabicDialogueController()

    # Mock sample Egyptian Arabic customer response ("نعم تم حل المشكلة")
    mock_customer_audio = b"\x00\xff" * 1600  # Fake mulaw audio bytes
    
    start_time = asyncio.get_event_loop().time()

    # 1. Test STT Conversion
    with patch.object(pipeline.stt, 'transcribe_chunk', new_callable=AsyncMock) as mock_stt:
        mock_stt.return_value = "نعم تم حل المشكلة"
        transcribed_text = await pipeline.process_incoming_audio_chunk(mock_customer_audio)
        assert transcribed_text == "نعم تم حل المشكلة"

    # 2. Test State Controller Logic
    response_text, next_state, should_escalate = dialogue.process_turn(transcribed_text)
    assert next_state == "RESOLVED"
    assert should_escalate is False

    # 3. Test TTS Response Chunk Generation
    audio_chunks_received = 0
    async for chunk in pipeline.generate_outgoing_audio_chunks(response_text):
        audio_chunks_received += 1
        if audio_chunks_received == 1:
            # Measure Time to First Audio Chunk (TTFB)
            first_byte_latency = (asyncio.get_event_loop().time() - start_time) * 1000
            print(f"\n[Test Result] Time to First Audio Byte: {first_byte_latency:.2f}ms")
            assert first_byte_latency <= 1200, "Latency exceeded 1.2s threshold!"

    assert audio_chunks_received > 0