#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -f WeChat_Data_Hub_images_v0.4.0.tar.gz ]]; then
  exec bash ./start-offline.sh
fi
command -v docker >/dev/null || { echo '请先安装并启动 Docker Desktop / Docker Engine。'; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Docker 尚未运行，请启动后重试。'; exit 1; }
if [[ ! -f .env ]] && docker volume inspect "${COMPOSE_PROJECT_NAME:-wechat-data-hub}_postgres" >/dev/null 2>&1; then
  echo '检测到已有数据库卷但缺少 .env。升级请先复制旧版本 .env，避免生成不匹配的数据库密码。'
  exit 1
fi
if [[ ! -f .env ]]; then
  if command -v python3 >/dev/null; then
    python3 scripts/bootstrap.py
  else
    docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/work" -w /work python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c python scripts/bootstrap.py
  fi
fi
docker compose up -d --build --wait
printf '\n已启动：http://127.0.0.1:5173\n首次打开请设置自己的管理员账号和密码。\n'
