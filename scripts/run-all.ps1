# 统一工作台：仅启动后端，浏览器打开 http://127.0.0.1:8000

$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root



if (-not (Test-Path ".env")) {

    Copy-Item ".env.example" ".env"

    Write-Host "已创建 .env，请确认 MySQL 账号密码与 SEED_DOCS_DIR"

}



python -m pip install -r requirements.txt -q --disable-pip-version-check



$backend = Start-Process -PassThru -WindowStyle Minimized python -ArgumentList @(

    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"

)



Start-Sleep -Seconds 2

Start-Process "http://127.0.0.1:8000/"



Write-Host "后端 PID $($backend.Id)  统一入口: http://127.0.0.1:8000"

Write-Host "首页可「初始化演示数据」→ 知识库文档 indexed 后体验问答与视频。"



