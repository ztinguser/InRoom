from uuid import UUID

from fastapi import APIRouter, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.auth.dependencies import CurrentUser
from backend.db.session import DB
from backend.files.dependencies import ObjectStore
from backend.files.uploads import read_pdf
from backend.preparations.models import ResumeAsset
from backend.preparations.repository import get_preparation
from backend.preparations.schemas import ResumeAssetOut

router = APIRouter(prefix="/preparations", tags=["preparations"])


@router.post(
    "/{preparation_id}/assets",
    response_model=ResumeAssetOut,
    status_code=201,
)
async def upload_asset(
    preparation_id: UUID,
    file: UploadFile,
    db: DB,
    user: CurrentUser,
    store: ObjectStore,
):
    await get_preparation(db, user.id, preparation_id)
    content = await read_pdf(file)

    def save_file() -> str:
        key = store.put(content)
        db.info["uploaded_keys"].append(key)
        return key

    key = await run_in_threadpool(save_file)
    asset = ResumeAsset(
        preparation_id=preparation_id,
        owner_id=user.id,
        object_key=key,
        filename=file.filename or "resume.pdf",
        size_bytes=len(content),
    )
    db.add(asset)
    await db.flush()
    return asset
