from uuid import UUID

from fastapi import APIRouter

from backend.auth.dependencies import CurrentUser
from backend.db.session import DB
from backend.preparations import repository
from backend.preparations.schemas import CancelInput, PreparationOut

router = APIRouter(prefix="/v1/preparations", tags=["preparations"])


@router.post("", response_model=PreparationOut, status_code=201)
async def create(db: DB, user: CurrentUser):
    return await repository.create_preparation(db, user.id)


@router.get("/{preparation_id}", response_model=PreparationOut)
async def get(preparation_id: UUID, db: DB, user: CurrentUser):
    return await repository.get_preparation(db, user.id, preparation_id)


@router.post("/{preparation_id}/cancel", response_model=PreparationOut)
async def cancel(
    preparation_id: UUID,
    body: CancelInput,
    db: DB,
    user: CurrentUser,
):
    return await repository.cancel_preparation(
        db,
        user.id,
        preparation_id,
        body.expected_state_version,
    )
