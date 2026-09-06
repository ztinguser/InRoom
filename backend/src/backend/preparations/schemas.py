from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PreparationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    state_version: int


class CancelInput(BaseModel):
    expected_state_version: int = Field(ge=1)
