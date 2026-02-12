"""Event schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    type: str
    actor_id: uuid.UUID | None
    resource_type: str
    resource_id: uuid.UUID
    data: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
