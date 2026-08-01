import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from shared.database.models import CallRecord, TranscriptLog
    from shared.database.connection import get_async_db
except Exception:  # pragma: no cover - fallback for local-only environments
    class CallRecord:  # type: ignore[override]
        pass

    class TranscriptLog:  # type: ignore[override]
        pass

    async def get_async_db():
        yield None

logger = logging.getLogger("voice_service.handshake_router")

router = APIRouter(prefix="/api/v1/voice", tags=["Voice API & Member 2 Handshake"])


@router.get("/resolutions", response_model=List[dict])
async def get_first_call_resolutions(
    limit: int = 50,
    status_filter: Optional[str] = "RESOLVED",
    db: AsyncSession = Depends(get_async_db)
):
    """
    HANDSHAKE ENDPOINT FOR MEMBER 2:
    Retrieves call records and statuses to populate the First Call Resolution (FCR) Report.
    """
    try:
        query = select(CallRecord)
        if status_filter:
            query = query.where(CallRecord.resolution_status == status_filter)
        query = query.order_by(CallRecord.created_at.desc()).limit(limit)

        result = await db.execute(query)
        calls = result.scalars().all()

        return [
            {
                "call_id": str(call.id),
                "call_sid": call.call_sid,
                "customer_phone": call.customer_phone,
                "duration_seconds": call.duration_seconds,
                "resolution_status": call.resolution_status,
                "escalated_to_human": call.escalated_to_human,
                "created_at": call.created_at.isoformat()
            }
            for call in calls
        ]
    except Exception as e:
        logger.error(f"Error fetching resolutions for Member 2 report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error fetching call resolutions"
        )


@router.get("/transcript/{call_sid}")
async def get_call_transcript(
    call_sid: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves full turn-by-turn spoken dialogue logs for QA and prompt evaluation.
    """
    query = select(TranscriptLog).where(TranscriptLog.call_sid == call_sid).order_by(TranscriptLog.timestamp.asc())
    result = await db.execute(query)
    transcripts = result.scalars().all()

    if not transcripts:
        raise HTTPException(status_code=404, detail=f"No transcripts found for call_sid: {call_sid}")

    return {
        "call_sid": call_sid,
        "turns": [
            {
                "speaker": t.speaker,  # 'CUSTOMER' or 'SYSTEM'
                "text": t.text,
                "latency_ms": t.latency_ms,
                "timestamp": t.timestamp.isoformat()
            }
            for t in transcripts
        ]
    }