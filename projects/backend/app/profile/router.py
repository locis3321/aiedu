"""能力画像 API（规格 v2 §10.3）。

鉴权：child-scoped token；跨孩子读取一律 403（负例必测）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.learning.router import get_session
from app.profile import service
from app.reports.router import get_child_context

router = APIRouter(prefix="/v1")


@router.get("/children/{child_id}/profile/dimensions")
def get_dimensions(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_dimensions(session, child_id)


@router.get("/children/{child_id}/profile/history")
def get_history(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_history(session, child_id)
