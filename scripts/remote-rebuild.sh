#!/bin/bash
set -e
cd /opt/ai-workbench
# 停掉卡住的构建
pkill -f 'docker compose build' 2>/dev/null || true
pkill -f docker-buildx 2>/dev/null || true
sleep 2
docker builder prune -f >/dev/null 2>&1 || true
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8000/api/v1/health || true
echo
echo REBUILD_DONE
