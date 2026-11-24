# 启动 AI 学习知识工作台（Windows PowerShell）
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已创建 .env，请编辑 LLM_API_KEY / EMBED_API_KEY 后重新运行。"
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
