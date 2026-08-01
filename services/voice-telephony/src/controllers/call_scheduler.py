"""Bounded background scheduler for outbound Twilio calls.

The database methods are deliberately small integration points. Replace them with
the shared database implementation when it becomes available.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client
except ImportError:  # Allows local development before Twilio is installed.
    Client = None  # type: ignore[assignment,misc]

    class TwilioRestException(Exception):
        """Fallback exception used when the optional Twilio dependency is absent."""


logger = logging.getLogger("voice_service.call_scheduler")

POLL_INTERVAL_SECONDS = int(os.getenv("CALL_SCHEDULER_POLL_INTERVAL_SECONDS", "10"))
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "5"))
MAX_RETRY_COUNT = int(os.getenv("MAX_CALL_RETRY_COUNT", "3"))


class CallSchedulerEngine:
    """Polls pending calls and dispatches them with bounded concurrency."""

    def __init__(self) -> None:
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER", "")
        self.webhook_url = os.getenv(
            "PUBLIC_WEBHOOK_URL",
            "https://your-domain.com/api/v1/twilio/voice-stream",
        )
        self.twilio_client = (
            Client(self.account_sid, self.auth_token)
            if Client and self.account_sid and self.auth_token
            else None
        )
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
        self._task: Optional[asyncio.Task[None]] = None
        self.is_running = False

        if self.twilio_client is None:
            logger.warning("Twilio credentials or package missing; scheduler is in mock mode.")

    async def fetch_pending_calls_from_db(self) -> List[Dict[str, Any]]:
        """Return calls ready to dial.

        Connect this method to the shared database; returning an empty list keeps
        the scheduler safe until that integration is implemented.
        """
        return []

    async def update_call_status_in_db(
        self,
        customer_id: str,
        status: str,
        call_sid: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """Persist a call-state change (database integration point)."""
        logger.info(
            "Call status update customer=%s status=%s call_sid=%s retries=%s at=%s",
            customer_id,
            status,
            call_sid,
            retry_count,
            datetime.now(timezone.utc).isoformat(),
        )

    async def dispatch_single_outbound_call(self, record: Dict[str, Any]) -> None:
        """Dial one record without exceeding the configured concurrency limit."""
        customer_id = str(record["id"])
        phone_number = str(record["phone_number"])

        async with self._semaphore:
            try:
                await self.update_call_status_in_db(customer_id, "DIALING")
                call_sid = await self._create_call(customer_id, phone_number)
                await self.update_call_status_in_db(customer_id, "IN_PROGRESS", call_sid)
                logger.info("Dispatched call customer=%s sid=%s", customer_id, call_sid)
            except TwilioRestException as error:
                logger.error("Twilio failed for customer=%s: %s", customer_id, error)
                await self.handle_failed_call(record, str(error))
            except Exception as error:
                logger.exception("Unexpected dial failure for customer=%s", customer_id)
                await self.handle_failed_call(record, str(error))

    async def _create_call(self, customer_id: str, phone_number: str) -> str:
        if self.twilio_client is None:
            await asyncio.sleep(0)
            return f"MOCK_SID_{customer_id}"

        status_base_url = self.webhook_url.rsplit("/", 1)[0]
        call = await asyncio.to_thread(
            self.twilio_client.calls.create,
            to=phone_number,
            from_=self.phone_number,
            url=self.webhook_url,
            status_callback=f"{status_base_url}/call-status",
            status_callback_event=["initiated", "answered", "completed"],
        )
        return str(call.sid)

    async def handle_failed_call(self, record: Dict[str, Any], error_msg: str) -> None:
        """Increment retry count or mark the call as permanently failed."""
        customer_id = str(record["id"])
        retries = int(record.get("retry_count", 0)) + 1
        status = "FAILED" if retries >= MAX_RETRY_COUNT else "PENDING"
        logger.warning(
            "Call failed customer=%s retries=%d/%d error=%s",
            customer_id,
            retries,
            MAX_RETRY_COUNT,
            error_msg,
        )
        await self.update_call_status_in_db(customer_id, status, retry_count=retries)

    async def run_loop(self) -> None:
        """Run until :meth:`stop` is called or the task is cancelled."""
        self.is_running = True
        logger.info("Outbound call scheduler started.")
        try:
            while self.is_running:
                records = await self.fetch_pending_calls_from_db()
                if records:
                    results = await asyncio.gather(
                        *(self.dispatch_single_outbound_call(record) for record in records),
                        return_exceptions=True,
                    )
                    for result in results:
                        if isinstance(result, Exception):
                            logger.error("Unhandled scheduler task error: %s", result)
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Outbound call scheduler cancelled.")
            raise
        finally:
            self.is_running = False

    def start(self) -> asyncio.Task[None]:
        """Start the loop once and return its background task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_loop(), name="outbound-call-scheduler")
        return self._task

    async def stop(self) -> None:
        """Stop and await the background task cleanly."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


scheduler_engine = CallSchedulerEngine()


async def start_scheduler() -> asyncio.Task[None]:
    """FastAPI lifespan startup hook."""
    return scheduler_engine.start()


async def stop_scheduler(task: Optional[asyncio.Task[None]] = None) -> None:
    """FastAPI lifespan shutdown hook; accepts the startup task for compatibility."""
    del task
    await scheduler_engine.stop()
