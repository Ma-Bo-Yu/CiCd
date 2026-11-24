from collections.abc import Generator
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_column_if_missing(table: str, column: str, ddl_sqlite: str, ddl_other: str) -> None:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if column in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        conn.execute(text(ddl_sqlite if dialect == "sqlite" else ddl_other))


def _ensure_schema_patches() -> None:
    """为已有表补列（无 Alembic）。"""
    _add_column_if_missing(
        "knowledge_bases",
        "owner_id",
        "ALTER TABLE knowledge_bases ADD COLUMN owner_id VARCHAR(36)",
        "ALTER TABLE knowledge_bases ADD COLUMN owner_id VARCHAR(36) NULL",
    )
    _add_column_if_missing(
        "users",
        "plan",
        "ALTER TABLE users ADD COLUMN plan VARCHAR(20) DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN plan VARCHAR(20) NOT NULL DEFAULT 'free'",
    )
    _add_column_if_missing(
        "users",
        "plan_expires_at",
        "ALTER TABLE users ADD COLUMN plan_expires_at DATETIME",
        "ALTER TABLE users ADD COLUMN plan_expires_at DATETIME NULL",
    )


def _bootstrap_admin_and_claim_orphans() -> None:
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import PLAN_PRO, User
    from app.services.auth import hash_password
    from app.services.billing import PRO_DAYS

    db = SessionLocal()
    try:
        admin = db.scalar(
            select(User).where(User.username == settings.bootstrap_admin_username)
        )
        if admin is None:
            any_user = db.scalar(select(User).limit(1))
            if any_user is None:
                admin = User(
                    username=settings.bootstrap_admin_username,
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    plan=PLAN_PRO,
                    plan_expires_at=datetime.now() + timedelta(days=PRO_DAYS * 12),
                )
                db.add(admin)
                db.flush()
            else:
                admin = any_user

        # 演示管理员保持 pro，避免配额打断黄金路径
        if admin.username == settings.bootstrap_admin_username:
            admin.plan = PLAN_PRO
            if admin.plan_expires_at is None or admin.plan_expires_at < datetime.now():
                admin.plan_expires_at = datetime.now() + timedelta(days=PRO_DAYS * 12)

        orphans = list(
            db.scalars(
                select(KnowledgeBase).where(
                    (KnowledgeBase.owner_id.is_(None)) | (KnowledgeBase.owner_id == "")
                )
            ).all()
        )
        for kb in orphans:
            kb.owner_id = admin.id
        db.commit()
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401 — register models with Base.metadata

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_schema_patches()
    _bootstrap_admin_and_claim_orphans()
