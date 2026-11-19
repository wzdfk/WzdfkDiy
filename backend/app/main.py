"""UIDiy Agent · FastAPI 入口。

启动（backend/ 目录下，任选其一）：
  conda activate diy && python app/main.py      # 直接脚本启动
  conda activate diy && python -m app.main      # 模块方式启动
  conda activate diy && uvicorn app.main:app --reload --port 8300
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# 允许 python app/main.py 直接脚本运行：把 backend/ 挂进 sys.path
_BASE_DIR = Path(__file__).resolve().parent.parent   # backend/
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from app.api.routes_settings import router as settings_router
from app.api.routes_style import router as style_router
from app.core.logging_config import setup_logging

load_dotenv(_BASE_DIR / ".env")
logger = setup_logging()


def _cors_origins() -> list[str]:
    yaml_cfg = os.getenv("UIDIY_CORS", "")
    if yaml_cfg:
        return [o.strip() for o in yaml_cfg.split(",") if o.strip()]
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


app = FastAPI(title="UIDiy Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个请求的状态与耗时；异常写完整堆栈。"""
    started = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        logger.exception("请求异常 %s %s", request.method, request.url.path)
        raise
    cost_ms = (time.perf_counter() - started) * 1000
    client = request.client.host if request.client else "-"
    logger.info(
        "REQ %s %s -> %s (%.1fms) client=%s",
        request.method, request.url.path, status, cost_ms, client,
    )
    return response


app.include_router(style_router)
app.include_router(settings_router)


@app.get("/api/health")
def health():
    db_configured = bool(os.getenv("DB_DATABASE"))
    return {"ok": True, "db": db_configured, "db_name": os.getenv("DB_DATABASE", "")}


def _server_addr() -> tuple[str, int]:
    """host/port 取值优先级：环境变量 UIDIY_HOST/UIDIY_PORT > config.yaml > 默认值。"""
    host = os.getenv("UIDIY_HOST")
    port = os.getenv("UIDIY_PORT")
    if not (host and port):
        try:
            import yaml
            cfg = yaml.safe_load((_BASE_DIR / "config.yaml").read_text(encoding="utf-8")) or {}
            app_cfg = cfg.get("app") or {}
            host = host or str(app_cfg.get("host", "127.0.0.1"))
            port = port or str(app_cfg.get("port", 8300))
        except Exception:
            host, port = host or "127.0.0.1", port or "8300"
    return host, int(port)


if __name__ == "__main__":
    import uvicorn

    host, port = _server_addr()
    logger.info("UIDiy Agent → http://%s:%s  (docs at /docs)", host, port)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,           # 开发热重载；生产可改 False
        log_config=None,       # 使用 app.core.logging_config 的双写配置
        access_log=True,
    )
