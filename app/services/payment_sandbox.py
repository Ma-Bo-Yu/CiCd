"""沙箱支付：模拟「下单 → 第三方收银台 → 回调开通」全流程（无真实扣款）。"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment import (
    ORDER_CANCELLED,
    ORDER_FAILED,
    ORDER_PAID,
    ORDER_PENDING,
    PRODUCT_PRO_MONTH,
    PaymentOrder,
)
from app.models.user import User
from app.services.billing import PRO_DAYS, PRO_PRICE_CNY, activate_pro


def create_pro_order(db: Session, user: User) -> PaymentOrder:
    order = PaymentOrder(
        user_id=user.id,
        product=PRODUCT_PRO_MONTH,
        amount_cents=PRO_PRICE_CNY * 100,
        status=ORDER_PENDING,
        channel="sandbox",
    )
    db.add(order)
    db.flush()
    return order


def get_order_for_user(db: Session, order_id: str, user: User) -> PaymentOrder:
    order = db.scalar(select(PaymentOrder).where(PaymentOrder.id == order_id))
    if order is None or order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    return order


def _apply_paid(db: Session, order: PaymentOrder, user: User) -> None:
    if order.status == ORDER_PAID:
        return
    if order.status != ORDER_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单状态不可支付")
    order.status = ORDER_PAID
    order.paid_at = datetime.now()
    if order.product == PRODUCT_PRO_MONTH:
        activate_pro(user, days=PRO_DAYS)
    db.flush()


def sandbox_pay_success(db: Session, order: PaymentOrder, user: User) -> None:
    """收银台点「支付成功」→ 等同支付渠道回调成功。"""
    _apply_paid(db, order, user)


def sandbox_pay_fail(db: Session, order: PaymentOrder, user: User) -> None:
    if order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    if order.status != ORDER_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单状态不可失败")
    order.status = ORDER_FAILED
    db.flush()


def sandbox_cancel(db: Session, order: PaymentOrder, user: User) -> None:
    if order.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    if order.status != ORDER_PENDING:
        return
    order.status = ORDER_CANCELLED
    db.flush()
