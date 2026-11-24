$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
python -m pip install -r requirements.txt -q --disable-pip-version-check
Write-Host "MySQL 库 ai 建表由启动时自动完成。统一入口: http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
