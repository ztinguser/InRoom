from uuid import UUID

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from backend.auth.dependencies import CurrentUser
from backend.core.errors import AppError
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


@router.get(
    "/{preparation_id}/assets/{asset_id}/download",
    response_class=FileResponse,
)
async def download_asset(
    preparation_id: UUID,
    asset_id: UUID,
    db: DB,
    user: CurrentUser,
    store: ObjectStore,
):
    asset = await db.scalar(
        select(ResumeAsset).where(
            ResumeAsset.id == asset_id,
            ResumeAsset.preparation_id == preparation_id,
            ResumeAsset.owner_id == user.id,
        )
    )
    if asset is None:
        raise AppError(404, "NOT_FOUND", "文件不存在")

    path = store.path(asset.object_key)
    if not await run_in_threadpool(path.is_file):
        raise AppError(503, "FILE_UNAVAILABLE", "文件暂时不可用")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=asset.filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )
