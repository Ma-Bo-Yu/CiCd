"""CLI wrapper: POST /api/v1/dev/seed (server must be running)."""

import httpx

if __name__ == "__main__":
    r = httpx.post("http://127.0.0.1:8000/api/v1/dev/seed", timeout=30.0)
    print(r.status_code, r.text)
