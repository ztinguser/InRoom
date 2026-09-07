from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
