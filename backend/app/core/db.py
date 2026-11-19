"""MySQL 持久化：风格档案存档（M4）。

表 style_archives：同名 upsert，tokens_json 存 StyleTokens 全量 JSON。
连接参数读 .env（DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_DATABASE）。
密码含特殊字符自动 URL 转义；连不上库时抛带指引的 RuntimeError，路由层兜底。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from sqlalchemy import String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from .tokens import StyleTokens

_engine = None
_ready = False


class Base(DeclarativeBase):
    pass


class StyleArchive(Base):
    __tablename__ = "style_archives"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    tokens_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def _connect_url() -> str:
    user = quote_plus(os.environ.get("DB_USER", "root"))
    pwd = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3306")
    db = os.environ.get("DB_DATABASE", "diy")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"


def get_engine():
    """懒连接 + 建表。失败时抛 RuntimeError（路由层转 503 语义返回）。"""
    global _engine, _ready
    if _ready:
        return _engine
    if not os.getenv("DB_DATABASE"):
        raise RuntimeError("未配置 DB_DATABASE（检查 backend/.env）")
    _engine = create_engine(_connect_url(), pool_pre_ping=True, pool_recycle=3600)
    try:
        Base.metadata.create_all(_engine)
    except Exception as e:  # MySQL 未启动等
        _engine = None
        raise RuntimeError(f"MySQL 连接失败（{e.__class__.__name__}），确认本机 3306 已启动") from e
    _ready = True
    return _engine


# ---------- CRUD ----------


def save_archive(name: str, tokens: StyleTokens) -> int:
    """按名字 upsert：同名覆盖，返回档案 id。"""
    with Session(get_engine()) as s:
        row = s.execute(
            select(StyleArchive).where(StyleArchive.name == name)
        ).scalar_one_or_none()
        payload = tokens.model_dump_json()
        if row is None:
            row = StyleArchive(name=name, tokens_json=payload)
            s.add(row)
        else:
            row.tokens_json = payload
        s.commit()
        return row.id


def list_archives() -> list[dict]:
    """档案摘要列表：id / 名称 / 主色 / 更新时间。"""
    with Session(get_engine()) as s:
        rows = s.execute(
            select(StyleArchive).order_by(StyleArchive.updated_at.desc())
        ).scalars().all()
        out: list[dict] = []
        for r in rows:
            try:
                accent = json.loads(r.tokens_json).get("color", {}).get("accent", {}).get("s500", "")
            except Exception:
                accent = ""
            out.append({
                "id": r.id,
                "name": r.name,
                "accent": accent,
                "updated_at": r.updated_at.isoformat(timespec="seconds"),
            })
        return out


def load_archive(archive_id: int) -> tuple[StyleTokens, str]:
    """按 id 取档案 → (StyleTokens, 档案名)。不存在抛 KeyError。"""
    with Session(get_engine()) as s:
        row = s.get(StyleArchive, archive_id)
        if row is None:
            raise KeyError(f"档案 #{archive_id} 不存在")
        return StyleTokens.model_validate_json(row.tokens_json), row.name


def delete_archive(archive_id: int) -> None:
    with Session(get_engine()) as s:
        row = s.get(StyleArchive, archive_id)
        if row is None:
            raise KeyError(f"档案 #{archive_id} 不存在")
        s.execute(delete(StyleArchive).where(StyleArchive.id == archive_id))
        s.commit()
