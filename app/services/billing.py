"""个人套餐与配额。升级走支付沙箱订单（见 payment_sandbox），无微信/支付宝真扣款。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.usage import (
    KIND_DOC_UPLOAD,
    KIND_KB_CREATE,
    KIND_RESEARCH_CREATE,
    KIND_VIDEO_CREATE,
    UsageEvent,
)
from app.models.user import PLAN_FREE, PLAN_PRO, User

PLAN_LIMITS: dict[str, dict[str, int]] = {
    PLAN_FREE: {
        "kb": 2,
        "docs": 10,
        "video_month": 2,
        "research_month": 3,
    },
    PLAN_PRO: {
        "kb": 20,
        "docs": 200,
        "video_month": 30,
        "research_month": 50,
    },
}

PLAN_LABELS = {
    PLAN_FREE: "免费版",
    PLAN_PRO: "专业版",
}

PRO_PRICE_CNY = 29
PRO_DAYS = 30

QUOTA_MESSAGES = {
    "kb": "知识库数量已达套餐上限，请升级专业版",
    "docs": "文档数量已达套餐上限，请升级专业版",
    "video_month": "本月视频任务数已达上限，请升级专业版",
    "research_month": "本月研究任务数已达上限，请升级专业版",
}


@dataclass
class UsageSnapshot:
    plan: str
    plan_label: str
    plan_expires_at: datetime | None
    limits: dict[str, int]
    kb_count: int
    doc_count: int
    video_month: int
    research_month: int


def effective_plan(user: User, now: datetime | None = None) -> str:
    now = now or datetime.now()
    plan = (user.plan or PLAN_FREE).strip().lower()
    if plan == PLAN_PRO:
        if user.plan_expires_at is None or user.plan_expires_at >= now:
            return PLAN_PRO
        return PLAN_FREE
    return PLAN_FREE


def limits_for(user: User) -> dict[str, int]:
    return dict(PLAN_LIMITS[effective_plan(user)])


def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    return datetime(now.year, now.month, 1)


def _count_kbs(db: Session, user_id: str) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(KnowledgeBase).where(
                KnowledgeBase.owner_id == user_id
            )
        )
        or 0
    )


def _count_docs(db: Session, user_id: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Document)
            .join(KnowledgeBase, Document.kb_id == KnowledgeBase.id)
            .where(KnowledgeBase.owner_id == user_id)
        )
        or 0
    )


def _count_events_this_month(db: Session, user_id: str, kind: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(
                UsageEvent.user_id == user_id,
                UsageEvent.kind == kind,
                UsageEvent.created_at >= _month_start(),
            )
        )
        or 0
    )


def usage_snapshot(db: Session, user: User) -> UsageSnapshot:
    plan = effective_plan(user)
    return UsageSnapshot(
        plan=plan,
        plan_label=PLAN_LABELS.get(plan, plan),
        plan_expires_at=user.plan_expires_at if plan == PLAN_PRO else user.plan_expires_at,
        limits=limits_for(user),
        kb_count=_count_kbs(db, user.id),
        doc_count=_count_docs(db, user.id),
        video_month=_count_events_this_month(db, user.id, KIND_VIDEO_CREATE),
        research_month=_count_events_this_month(db, user.id, KIND_RESEARCH_CREATE),
    )


def record_usage(db: Session, user: User, kind: str, ref_id: str | None = None) -> None:
    db.add(UsageEvent(user_id=user.id, kind=kind, ref_id=ref_id))


def _raise_quota(metric: str, *, as_api: bool = False, as_page: bool = False) -> None:
    msg = QUOTA_MESSAGES.get(metric, "已达套餐配额上限，请升级专业版")
    if as_page:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/billing?quota={metric}"},
        )
    if as_api:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "quota_exceeded", "message": msg, "metric": metric}},
        )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)


def assert_can_create_kb(
    db: Session, user: User, *, as_api: bool = False, as_page: bool = False
) -> None:
    lim = limits_for(user)["kb"]
    if _count_kbs(db, user.id) >= lim:
        _raise_quota("kb", as_api=as_api, as_page=as_page)


def assert_can_upload_docs(
    db: Session,
    user: User,
    count: int = 1,
    *,
    as_api: bool = False,
    as_page: bool = False,
) -> None:
    lim = limits_for(user)["docs"]
    if _count_docs(db, user.id) + count > lim:
        _raise_quota("docs", as_api=as_api, as_page=as_page)


def assert_can_create_video(
    db: Session, user: User, *, as_api: bool = False, as_page: bool = False
) -> None:
    lim = limits_for(user)["video_month"]
    if _count_events_this_month(db, user.id, KIND_VIDEO_CREATE) >= lim:
        _raise_quota("video_month", as_api=as_api, as_page=as_page)


def assert_can_create_research(
    db: Session, user: User, *, as_api: bool = False, as_page: bool = False
) -> None:
    lim = limits_for(user)["research_month"]
    if _count_events_this_month(db, user.id, KIND_RESEARCH_CREATE) >= lim:
        _raise_quota("research_month", as_api=as_api, as_page=as_page)


def activate_pro(user: User, days: int = PRO_DAYS) -> None:
    user.plan = PLAN_PRO
    user.plan_expires_at = datetime.now() + timedelta(days=days)


def downgrade_to_free(user: User) -> None:
    user.plan = PLAN_FREE
    user.plan_expires_at = None


# Re-export kinds for callers
__all__ = [
    "KIND_DOC_UPLOAD",
    "KIND_KB_CREATE",
    "KIND_RESEARCH_CREATE",
    "KIND_VIDEO_CREATE",
    "PLAN_FREE",
    "PLAN_PRO",
    "PLAN_LABELS",
    "PLAN_LIMITS",
    "PRO_DAYS",
    "PRO_PRICE_CNY",
    "UsageSnapshot",
    "activate_pro",
    "assert_can_create_kb",
    "assert_can_create_research",
    "assert_can_create_video",
    "assert_can_upload_docs",
    "downgrade_to_free",
    "effective_plan",
    "limits_for",
    "record_usage",
    "usage_snapshot",
]
