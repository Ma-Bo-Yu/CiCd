#!/bin/bash
# 日常改代码：只同步挂载目录并重启（秒级）
# 仅当 Dockerfile / requirements.txt 变化，或 FORCE_REBUILD=1 时才完整 build
set -e
cd /opt/ai-workbench

need_build=0
if [ "${FORCE_REBUILD:-0}" = "1" ]; then
  need_build=1
elif [ ! -f .deploy-fingerprint ]; then
  need_build=1
else
  cur=$(cat Dockerfile requirements.txt 2>/dev/null | sha256sum | awk '{print $1}')
  old=$(cat .deploy-fingerprint 2>/dev/null || true)
  if [ "$cur" != "$old" ]; then
    need_build=1
  fi
fi

if [ "$need_build" = "1" ]; then
  echo "==> Dockerfile/依赖有变，执行 docker compose build"
  # 不清空 builder 缓存，避免每次重装 apt/pip
  docker compose build
  cat Dockerfile requirements.txt 2>/dev/null | sha256sum | awk '{print $1}' > .deploy-fingerprint
else
  echo "==> 仅代码/模板变更，跳过 build，直接重启"
fi

docker compose up -d --force-recreate
docker compose ps
curl -fsS http://127.0.0.1:8000/api/v1/health || true
echo
echo REBUILD_DONE
