"""快速检查主要页面是否可访问（需已启动 uvicorn :8000）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient

from app.main import app

PATHS = [
    ("/", 200),
    ("/kb", 200),
    ("/chat", 200),
    ("/chat/ai", 200),
    ("/chat/vision", 302),
    ("/research", 200),
    ("/video", 200),
    ("/settings", 200),
    ("/partials/nav", 200),
    ("/api/v1/health", 200),
    ("/static/js/htmx.min.js", 200),
    ("/static/js/site-boot.js", 200),
]


def main() -> None:
    client = TestClient(app, raise_server_exceptions=True)
    failed = 0
    for path, expect in PATHS:
        r = client.get(path, follow_redirects=False)
        ok = r.status_code == expect
        mark = "OK" if ok else "FAIL"
        print(f"{mark}  {path} -> {r.status_code} (expect {expect})")
        if not ok:
            failed += 1
    if failed:
        sys.exit(1)
    print(f"\n全部 {len(PATHS)} 项通过。")


if __name__ == "__main__":
    main()
