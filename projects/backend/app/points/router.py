"""积分与成长 API（规格 v2 §4.2 资源清单）。

鉴权：child-scoped token（T2 switch-session 签发）；家长侧明细视图由 T6/T9
复用 points.service.get_ledger，不在此重复暴露家长入口。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.accounts.models import ChildProfile
from app.learning.router import get_current_child, get_session
from app.points import service
from app.points.schemas import GrantRewardRequest, RedeemRequest
from app.reports.router import get_child_context

router = APIRouter(prefix="/v1")


def _child_id(auth: tuple[ChildProfile, dict]) -> str:
    return auth[0].id


@router.post("/rewards/grant")
def grant_reward(
    request: GrantRewardRequest,
    auth: tuple[ChildProfile, dict] = Depends(get_current_child),
    session: Session = Depends(get_session),
) -> dict:
    return service.grant_reward(session, _child_id(auth), request.evidence_id)


@router.get("/children/{child_id}/ledger")
def get_ledger(
    child_id: str,
    _ctx: str = Depends(get_child_context),
    session: Session = Depends(get_session),
) -> dict:
    return service.get_ledger(session, child_id)


@router.post("/rewards/redeem")
def redeem(
    _request: RedeemRequest,
    _auth: tuple[ChildProfile, dict] = Depends(get_current_child),
) -> dict:
    return service.redeem_reserved()
