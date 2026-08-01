"""Config version schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConfigVersionRead(BaseModel):
    id: uuid.UUID
    route_server_id: uuid.UUID
    content: str
    config_hash: str
    template_snapshot: dict[str, Any] | None
    generated_at: datetime
    applied_at: datetime | None
    apply_error: str | None = None
    apply_error_at: datetime | None = None
    generated_by_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ConfigDiff(BaseModel):
    current_hash: str | None
    new_hash: str
    diff: str
