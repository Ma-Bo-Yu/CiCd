"""沙箱支付订单（演示真实支付链路：下单 → 收银台 → 回调开通）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_FAILED = "failed"
ORDER_CANCELLED = "cancelled"

PRODUCT_PRO_MONTH = "pro_month"


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product: Mapped[str] = mapped_column(String(40), nullable=False, default=PRODUCT_PRO_MONTH)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ORDER_PENDING, index=True
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="sandbox")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
