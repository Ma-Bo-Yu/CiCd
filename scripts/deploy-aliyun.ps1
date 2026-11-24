# 一键部署到阿里云 ECS（需已配置 SSH 公钥登录）
param(
    [string]$HostIp = "47.114.54.192",
    [string]$User = "root",
    [string]$RemoteDir = "/opt/ai-workbench"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$sshTarget = "${User}@${HostIp}"
Write-Host "==> target $sshTarget dir $RemoteDir"

ssh -o BatchMode=yes -o ConnectTimeout=12 $sshTarget "echo ok"
if ($LASTEXITCODE -ne 0) {
    Write-Host "SSH failed. Add this public key to ~/.ssh/authorized_keys on the ECS:"
    if (Test-Path "$env:USERPROFILE\.ssh\id_ed25519.pub") {
        Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
    }
    exit 1
}

if (-not (Test-Path ".env.production")) {
    Copy-Item ".env.production.example" ".env.production"
    Write-Host "Created .env.production - edit secrets then re-run."
    exit 1
}

Write-Host "==> prepare remote docker"
ssh $sshTarget "mkdir -p $RemoteDir/data $RemoteDir/chroma; touch $RemoteDir/app.db; if ! command -v docker >/dev/null 2>&1; then curl -fsSL https://get.docker.com | sh; systemctl enable --now docker; fi; docker compose version >/dev/null 2>&1 || (apt-get update -y && apt-get install -y docker-compose-plugin); echo prepare_ok"

Write-Host "==> upload files"
scp -r Dockerfile docker-compose.yml requirements.txt README.md .env.production app scripts "${sshTarget}:${RemoteDir}/"

Write-Host "==> build and start"
ssh $sshTarget "cd $RemoteDir && docker compose build --pull && docker compose up -d && docker compose ps && curl -fsS http://127.0.0.1:8000/api/v1/health || true"

Write-Host ""
Write-Host "Done. Open security group TCP 8000 if needed."
Write-Host "URL: http://${HostIp}:8000/"
