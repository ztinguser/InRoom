from uuid import UUID

from fastapi import APIRouter

from backend.auth.dependencies import CurrentUser
from backend.db.session import DB
from backend.jobs.repository import get_job
from backend.jobs.results import cancel_job
from backend.jobs.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get(job_id: UUID, db: DB, user: CurrentUser):
    return await get_job(db, user.id, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel(job_id: UUID, db: DB, user: CurrentUser):
    return await cancel_job(db, user.id, job_id)
