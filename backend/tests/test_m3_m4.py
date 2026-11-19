"""M3/M4 测试：撤销栈 + MySQL 档案持久化。

用例通过 TestClient 打真实 API。MySQL 不可达时档案用例自动跳过。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

client = TestClient(app)


def _reset():
    client.post("/api/style/reset")


# ---------- M3：撤销 ----------

def test_chat_returns_history_shape():
    _reset()
    r = client.post("/api/style/chat", json={"message": "再柔和一点", "history": [
        {"role": "user", "text": "你好"},
        {"role": "bot", "text": "在"},
    ]})
    assert r.status_code == 200
    body = r.json()
    assert {"tokens", "diff", "reply"} <= set(body)


def test_undo_restores_previous_state():
    _reset()
    before = client.get("/api/style/current").json()["elevation"]["type"]

    client.post("/api/style/chat", json={"message": "再柔和一点"})
    after = client.get("/api/style/current").json()["elevation"]["type"]

    r = client.post("/api/style/undo")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tokens"]["elevation"]["type"] == before

    # 栈空后返回 ok=False 但不炸
    r2 = client.post("/api/style/undo")
    assert r2.status_code == 200


def test_undo_covers_panel_and_parse():
    """面板 patch（POST /current）和 parse 也要能撤销。"""
    _reset()
    base = client.get("/api/style/current").json()
    assert base["shape"]["strategy"] == "fold"

    # 面板改动
    import copy
    patched = copy.deepcopy(base)
    patched["line"]["border_width"] = 3
    client.post("/api/style/current", json=patched)
    cur = client.get("/api/style/current").json()
    assert cur["line"]["border_width"] == 3

    r = client.post("/api/style/undo")
    assert r.json()["tokens"]["line"]["border_width"] == base["line"]["border_width"]


# ---------- M4：MySQL 档案持久化 ----------

def _mysql_available() -> bool:
    try:
        from app.core import db
        db.get_engine()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _mysql_available(), reason="MySQL 未启动或不可达")
def test_archive_save_list_load_delete():
    _reset()
    name = "测试档案 pytest"

    # save（同名覆盖）
    r1 = client.post("/api/style/archives", json={"name": name})
    assert r1.json()["ok"] is True
    r1b = client.post("/api/style/archives", json={"name": name})
    assert r1b.json()["ok"] is True

    # list
    items = client.get("/api/style/archives").json()["items"]
    match = [i for i in items if i["name"] == name]
    assert len(match) == 1, "同名应覆盖而不是新增"
    archive_id = match[0]["id"]
    assert match[0]["accent"].startswith("#")

    # 改动当前风格后 load 回来
    client.post("/api/style/chat", json={"message": "硬朗一些"})
    r_load = client.post(f"/api/style/archives/{archive_id}/load")
    assert r_load.json()["ok"] is True
    assert r_load.json()["tokens"]["meta"]["version"]

    # delete
    r_del = client.delete(f"/api/style/archives/{archive_id}")
    assert r_del.json()["ok"] is True
    items_after = client.get("/api/style/archives").json()["items"]
    assert all(i["id"] != archive_id for i in items_after)


@pytest.mark.skipif(not _mysql_available(), reason="MySQL 未启动或不可达")
def test_archive_load_missing_returns_ok_false():
    r = client.post("/api/style/archives/999999/load")
    assert r.json()["ok"] is False
