from dataclasses import dataclass


@dataclass
class Conversation:
    customer_id: str | None = None
    transcript: str | None = None
