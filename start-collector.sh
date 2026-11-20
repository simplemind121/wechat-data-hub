#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
case "${1:-}" in
  files) collector_name=personal; collector_profile=personal-collector ;;
  wecom) collector_name=wecom; collector_profile=wecom-collector ;;
  *) echo '用法：bash start-collector.sh files 或 bash start-collector.sh wecom'; exit 1 ;;
esac
collector_config="collector/${collector_name}.json"
[[ -f "$collector_config" && ! -L "$collector_config" ]] || {
  echo "请先在网页创建数据源，将下载的配置保存到 ${collector_config}。"; exit 1;
}
mkdir -p collector/inbox "collector/${collector_name}-state" collector/secrets
chmod 700 collector "collector/${collector_name}-state" collector/secrets
chmod 600 "$collector_config"
export COLLECTOR_UID="${COLLECTOR_UID:-$(id -u)}"
export COLLECTOR_GID="${COLLECTOR_GID:-$(id -g)}"
docker compose -f compose.yaml -f compose.offline.yaml -f compose.collectors.yaml \
  --profile "$collector_profile" up -d --no-build "$collector_profile"
echo '采集端已启动；连接状态和导入结果可在网页的数据源与导入中查看。'
