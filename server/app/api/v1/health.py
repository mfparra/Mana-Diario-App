from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.session import check_db, get_engine
from app.domain.calendar import today
from app.llm.health import check_llm
from app.services.health import HealthService
from app.services.studies import is_published

router = APIRouter(tags=["infra"])


class HealthOut(BaseModel):
    status: Literal["ok", "error"]
    db: Literal["ok", "error", "not_configured"]
    llm: Literal["ok", "degraded"]
    today_published: bool


def get_health_service(settings: Settings = Depends(get_settings)) -> HealthService:
    async def db_check() -> str:
        return await check_db(get_engine())

    async def today_published() -> bool:
        return await is_published(get_engine(), today())

    return HealthService(db_check, lambda: check_llm(settings), today_published)


@router.get("/health", response_model=HealthOut)
async def health(response: Response, service: HealthService = Depends(get_health_service)) -> HealthOut:
    report = await service.report()
    if not report.healthy:
        response.status_code = 503
    return HealthOut(
        status=report.status, db=report.db, llm=report.llm, today_published=report.today_published
    )
