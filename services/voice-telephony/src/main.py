import os
import json
import base64
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.adapters.twilio import router as twilio_router
from src.api.handshake_router import router as handshake_router
from src.adapters.pipeline import VoiceAudioPipeline
from src.controllers.dialogue_state import ArabicDialogueController

try:
    from shared.database.connection import init_db_pool, close_db_pool, AsyncSessionLocal
    from shared.database.models import CallRecord, TranscriptLog
except Exception:  # pragma: no cover - fallback for local-only environments
    async def init_db_pool() -> None:
        return None

    async def close_db_pool() -> None:
        return None

    class AsyncSessionLocal:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._db = None

        async def __aenter__(self) -> "AsyncSessionLocal":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def add(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def commit(self) -> None:
            return None

    class CallRecord:  # type: ignore[override]
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    class TranscriptLog:  # type: ignore[override]
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_service.main")


# Manage DB Connection Lifecycles during startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing DB Connection Pool...")
    await init_db_pool()
    yield
    logger.info("Closing DB Connection Pool...")
    await close_db_pool()


app = FastAPI(
    title="Voice & Telephony Microservice (Member 1)",
    version="1.0.0",
    lifespan=lifespan
)

# Include Routers
app.include_router(twilio_router)
app.include_router(handshake_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "voice-telephony"}


# ==============================================================================
# MAIN WEBSOCKET MEDIA STREAM HANDLER
# ==============================================================================
@app.websocket("/ws/call")
async def websocket_twilio_media_stream(websocket: WebSocket):
    """
    Bi-directional streaming WebSocket endpoint connecting Twilio Media Streams to AI STT/TTS pipeline.
    """
    await websocket.accept()
    pipeline = VoiceAudioPipeline()
    dialogue_controller = ArabicDialogueController()
    
    call_sid = None
    customer_phone = None

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event_type = data.get("event")

            # Event 1: Stream Start metadata from Twilio
            if event_type == "start":
                start_data = data.get("start", {})
                call_sid = start_data.get("callSid")
                custom_params = start_data.get("customParameters", {})
                customer_phone = custom_params.get("customerPhone", "UNKNOWN")

                logger.info(f"WebSocket Connected | CallSid: {call_sid} | Customer: {customer_phone}")
                
                # Create Initial Call Record in Postgres
                async with AsyncSessionLocal() as db:
                    new_call = CallRecord(
                        call_sid=call_sid,
                        customer_phone=customer_phone,
                        resolution_status="IN_PROGRESS"
                    )
                    db.add(new_call)
                    await db.commit()

                # Play Opening Greeting in Egyptian Arabic
                greeting_text = dialogue_controller.get_initial_greeting()
                async for response_chunk in pipeline.generate_outgoing_audio_chunks(greeting_text):
                    await websocket.send_json(response_chunk)

            # Event 2: Inbound Media Chunk from Customer Phone
            elif event_type == "media":
                payload_base64 = data["media"]["payload"]
                raw_audio_bytes = base64.b64decode(payload_base64)

                # Process chunk through STT
                customer_text = await pipeline.process_incoming_audio_chunk(raw_audio_bytes)

                if customer_text:
                    # Log Customer Turn to DB
                    async with AsyncSessionLocal() as db:
                        db.add(TranscriptLog(call_sid=call_sid, speaker="CUSTOMER", text=customer_text))
                        await db.commit()

                    # Compute State & Response
                    response_text, next_state, should_escalate = dialogue_controller.process_turn(customer_text)

                    # Stream Response Audio Back
                    async for response_chunk in pipeline.generate_outgoing_audio_chunks(response_text):
                        await websocket.send_json(response_chunk)

                    # Update Resolution State in Postgres
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(select(CallRecord).where(CallRecord.call_sid == call_sid))
                        record = result.scalars().first()
                        if record:
                            record.resolution_status = next_state
                            record.escalated_to_human = should_escalate
                            await db.commit()

            # Event 3: Call Stop
            elif event_type == "stop":
                logger.info(f"Twilio Media Stream Stopped for CallSid: {call_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for CallSid: {call_sid}")
    except Exception as e:
        logger.error(f"WebSocket execution error on CallSid {call_sid}: {e}")
    finally:
        await websocket.close()