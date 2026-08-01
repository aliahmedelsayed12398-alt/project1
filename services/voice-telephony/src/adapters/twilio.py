import os
import logging
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, status
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.request_validator import RequestValidator   

logger = logging.getLogger("voice_service.twilio_adapter")

router = APIRouter(prefix="/api/v1/twilio", tags=["Twilio Telephony"])

# Load Twilio credentials from environment
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
PUBLIC_WEBSOCKET_URL = os.getenv("PUBLIC_WEBSOCKET_URL", "wss://your-domain.com/ws/call")


def verify_twilio_signature(request_url: str, post_data: dict, signature: Optional[str]) -> bool:
    """
    Validates that incoming webhook HTTP POST requests originate directly from Twilio.
    """
    if not TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO_AUTH_TOKEN is not configured. Skipping signature validation.")
        return True
    
    if not signature:
        return False

    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(request_url, post_data, signature)


@router.post("/voice-stream", response_class=Response)
async def handle_outbound_call_stream(request: Request):
    """
    Twilio Voice Webhook Endpoint.
    Triggered when an outbound or inbound call connects.
    Returns TwiML instructing Twilio to open a bi-directional Media Stream over WebSocket.
    """
    # 1. Extract request parameters and headers
    form_data = await request.form()
    payload = dict(form_data)
    twilio_signature = request.headers.get("X-Twilio-Signature")
    request_url = str(request.url)

    # 2. Security Check: Validate Twilio Signature
    if not verify_twilio_signature(request_url, payload, twilio_signature):
        logger.error("Unauthorized Twilio webhook request failed signature validation.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio Request Signature"
        )

    call_sid = payload.get("CallSid", "UNKNOWN")
    customer_phone = payload.get("To", payload.get("From", "UNKNOWN"))
    logger.info(f"Initiating TwiML stream for CallSid: {call_sid} | Customer: {customer_phone}")

    # 3. Construct TwiML XML Response
    response = VoiceResponse()
    
    # Optional: Initial pause to allow audio socket handshake to stabilize
    response.pause(length=1)

    # Connect to bi-directional WebSocket media stream
    connect = Connect()
    stream = connect.stream(url=PUBLIC_WEBSOCKET_URL)
    
    # Pass metadata parameters down to the WebSocket session
    stream.parameter(name="callSid", value=call_sid)
    stream.parameter(name="customerPhone", value=customer_phone)
    
    response.append(connect)

    # Return XML with proper TwiML MIME type
    return Response(content=str(response), media_type="application/xml")


@router.post("/call-status")
async def handle_call_status_update(request: Request):
    """
    Twilio Call Status Webhook.
    Captures status lifecycle updates (initiated, ringing, answered, completed, failed, busy).
    """
    form_data = await request.form()
    payload = dict(form_data)
    
    call_sid = payload.get("CallSid")
    call_status = payload.get("CallStatus")
    call_duration = payload.get("CallDuration", "0")

    logger.info(
        f"Call Status Update | CallSid: {call_sid} | Status: {call_status} | Duration: {call_duration}s"
    )

    # Note: Here you will update the PostgreSQL call records via shared/database
    if call_status in ["completed", "failed", "no-answer", "busy"]:
        logger.info(f"Call {call_sid} terminated with final status: {call_status}")

    return {"status": "accepted", "call_sid": call_sid}