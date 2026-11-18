#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null || { echo '请先安装 Docker Desktop / Docker Engine。'; exit 1; }
docker info >/dev/null 2>&1 || { echo '请先启动 Docker。'; exit 1; }
docker compose version >/dev/null
[[ -f images.lock ]] || { echo '缺少 images.lock，请使用完整运行包。'; exit 1; }
images_match() {
  local name expected actual
  while IFS=' ' read -r name expected; do
    [[ -z "$name" || "$name" == \#* ]] && continue
    actual="$(docker image inspect --format '{{.Id}}' "$name" 2>/dev/null || true)"
    [[ "$actual" == "$expected" ]] || return 1
  done < images.lock
}
if ! images_match; then
  [[ -f WeChat_Data_Hub_images_v0.3.0.tar.gz ]] || {
    echo '缺少离线镜像包；请把 WeChat_Data_Hub_images_v0.3.0.tar.gz 放在本目录，或使用 ./start.sh 从源码构建。'
    exit 1
  }
  docker load -i WeChat_Data_Hub_images_v0.3.0.tar.gz
fi
images_match || { echo '镜像 ID 与交付清单不符，已停止启动。'; exit 1; }
if [[ ! -f .env ]] && docker volume inspect "${COMPOSE_PROJECT_NAME:-wechat-data-hub}_postgres" >/dev/null 2>&1; then
  echo '检测到已有数据库卷但缺少 .env。升级请先复制旧版本 .env，避免生成不匹配的数据库密码。'
  exit 1
fi
if [[ ! -f .env ]]; then
  if command -v python3 >/dev/null; then
    python3 scripts/bootstrap.py
  else
    docker run --rm --network none --user "$(id -u):$(id -g)" \
      -v "$PWD:/work" -w /work wechat-data-hub-api:0.3.0 python scripts/bootstrap.py
  fi
fi
docker compose -f compose.yaml -f compose.offline.yaml up -d --no-build --wait
printf '\n已启动：http://127.0.0.1:5173\n首次打开请创建自己的管理员账号和密码。\n'
