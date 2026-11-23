"""快速验证设置模块改造：运行 python scripts/verify_settings_export.py。"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.api import routes_settings  # noqa: E402
from main import app  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")
    return ok


def main() -> int:
    studio = (ROOT / "frontend/src/views/StudioView.vue").read_text(encoding="utf-8")
    theme = (ROOT / "frontend/src/composables/theme.ts").read_text(encoding="utf-8")
    system = (ROOT / "frontend/src/composables/systemSettings.ts").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api/style.ts").read_text(encoding="utf-8")
    settings_py = (ROOT / "backend/app/api/routes_settings.py").read_text(encoding="utf-8")
    llm_py = (ROOT / "backend/app/core/llm.py").read_text(encoding="utf-8")

    results = [
        check("设置页两个 Tab", ">系统设置</button>" in studio and ">模型设置</button>" in studio),
        check("主题默认跟随系统", "ThemePreference = 'system'" in theme),
        check("默认输出路径", "'C:/Users/output'" in system),
        check("导出前询问设置项", "askBeforeExport" in system and "askBeforeExport" in studio),
        check(
            "说明改为悬浮提示",
            'class="hint-mark"' in studio
            and "勾选后忽略默认路径，每次导出都选择位置；未勾选时保存到上方路径。" in studio,
        ),
        check("后端写盘 API 接入", "saveExportToDir" in api and "saveExportToDir" in studio),
        check(
            "路径选择控件替代手输",
            'v-model="systemDraft.outputDir"' not in studio
            and "pickSystemDir" in studio
            and "class=\"path-field\"" in studio,
        ),
        check("原生目录选择 API", '"/pick-dir"' in settings_py and "pickDirectory" in api),
        check(
            "模型改为下拉选择",
            "modelOptions" in studio and "model-field" in studio and "listLlmModels" in api,
        ),
        check(
            "模型列表后端接口",
            '"/llm/models"' in settings_py and "def list_models" in llm_py,
        ),
    ]

    with TestClient(app) as client:
        with tempfile.TemporaryDirectory() as tmp:
            res = client.post("/api/style/export/save", json={"output_dir": tmp})
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            dest = Path(data.get("path", ""))
            results.append(check(
                "导出写入指定目录",
                res.status_code == 200 and bool(data.get("ok")) and dest.is_file() and zipfile.is_zipfile(dest),
                str(dest),
            ))

        res = client.post("/api/style/export/save", json={"output_dir": "relative/output"})
        results.append(check("拒绝相对路径", res.status_code == 400))

        with tempfile.TemporaryDirectory() as tmp:
            marker = routes_settings._PICK_DIR_MARKER
            fake = SimpleNamespace(stdout=marker + tmp.encode("utf-8"), stderr=b"", returncode=0)
            with patch.object(routes_settings.subprocess, "run", return_value=fake):
                res = client.post("/api/settings/pick-dir")
            data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            results.append(check(
                "目录选择返回绝对路径",
                res.status_code == 200 and data.get("selected") is True
                and Path(data.get("path", "")).resolve() == Path(tmp).resolve(),
                str(data.get("path", "")),
            ))

            fake = SimpleNamespace(stdout=b"", stderr=b"", returncode=0)
            with patch.object(routes_settings.subprocess, "run", return_value=fake):
                res = client.post("/api/settings/pick-dir")
            results.append(check("取消目录选择不返回路径", res.json().get("selected") is False))

        with patch.object(
            routes_settings.llm, "list_models",
            return_value={"ok": True, "models": ["m1", "m2"], "url": "https://example/models"},
        ):
            res = client.post(
                "/api/settings/llm/models",
                json={"base_url": "https://example/v1/chat/completions", "api_key": "fake"},
            )
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        results.append(check(
            "模型列表接口返回选项",
            res.status_code == 200 and data.get("models") == ["m1", "m2"],
            str(data.get("models", [])),
        ))

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
