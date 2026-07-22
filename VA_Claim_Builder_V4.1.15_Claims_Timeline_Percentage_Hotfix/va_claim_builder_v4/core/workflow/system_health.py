from __future__ import annotations
import importlib.util, os, platform, shutil, sqlite3, sys
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class HealthCheck:
    name: str
    status: str
    detail: str
    required: bool = True

class SystemHealthChecker:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root)

    def run(self, db_path: str | Path | None = None) -> dict:
        checks: list[HealthCheck] = []
        py_ok = sys.version_info >= (3, 10)
        checks.append(HealthCheck("Python", "pass" if py_ok else "fail", platform.python_version()))
        for module, required in [("streamlit", True),("pydantic", True),("pypdf", True),("docx", True),("pytesseract", False),("openai", False)]:
            present = importlib.util.find_spec(module) is not None
            checks.append(HealthCheck(module, "pass" if present else ("warn" if not required else "fail"), "installed" if present else "not installed", required))
        tess = shutil.which("tesseract")
        checks.append(HealthCheck("Tesseract OCR", "pass" if tess else "warn", tess or "not found; native PDF text still works", False))
        writable = self._writable(self.project_root)
        checks.append(HealthCheck("Project storage", "pass" if writable else "fail", str(self.project_root)))
        if db_path:
            checks.append(self._database_check(Path(db_path)))
        local_only = os.getenv("VCB_LOCAL_ONLY", "false").lower() == "true"
        has_openai = bool(os.getenv("OPENAI_API_KEY")); has_xai = bool(os.getenv("XAI_API_KEY"))
        ai_detail = "local-only enabled" if local_only else f"OpenAI key={'yes' if has_openai else 'no'}, xAI key={'yes' if has_xai else 'no'}"
        checks.append(HealthCheck("AI configuration", "pass" if local_only or has_openai or has_xai else "warn", ai_detail, False))
        overall = "ready" if not any(c.status == "fail" for c in checks) else "blocked"
        return {"overall": overall, "checks": [asdict(c) for c in checks]}

    @staticmethod
    def _writable(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8"); probe.unlink()
            return True
        except OSError:
            return False

    @staticmethod
    def _database_check(path: Path) -> HealthCheck:
        try:
            with sqlite3.connect(path) as con:
                result = con.execute("PRAGMA integrity_check").fetchone()[0]
            return HealthCheck("Database integrity", "pass" if result == "ok" else "fail", result)
        except Exception as exc:
            return HealthCheck("Database integrity", "fail", str(exc))
