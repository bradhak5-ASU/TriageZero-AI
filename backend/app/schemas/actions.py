from typing import Literal

from pydantic import BaseModel

ActionDecision = Literal["approve", "reject"]


class IngestAccepted(BaseModel):
    """External ingestion receipt. Field names are the proven wire contract —
    the frontend HTTP adapter translates investigation_id to its internal id."""

    investigation_id: str
    status: Literal["received"] = "received"
    received_at: str
