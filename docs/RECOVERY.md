# 加密备份、恢复、升级与回滚 · 0.2.0

当前迁移 head：`0003_entities`。默认 runtime 启动先运行 Alembic upgrade，再启动 API/独立 worker；重复启动幂等。禁止自动 downgrade 或清表。

## 备份

网页「审计与备份」下载当前工作空间 `.wdhbak`；用至少16字符独立口令。保存到异盘/受控备份介质，口令分开保管。CLI `docker compose exec api python -m wdh_api.cli backup` 在本机可信管理域备份全库并提示口令；输出文件默认私有数据卷 `exports/backup-<UTC>.wdhbak`，需另复制到安全位置。

WDHBK02 使用 scrypt + AES-256-GCM 认证帧、认证结束标记；数据库 repeatable-read 只读快照，按快照引用保存原件并核查 SHA-256。备份含账号密码哈希和源内容，应视为敏感文件。错误口令/篡改/截断拒绝恢复。无后门、忘记口令无法解密；自定义封装尚未经过独立密码学审计。

`.env`/部署端口/主机磁盘加密设置不在聊天备份中，应单独保护和记录。数据恢复后可以使用新生成的数据库凭据，不依赖旧数据库密码；用户登录密码哈希随数据恢复。

## 恢复到新目标

绝不能在既有数据卷或数据库上恢复。准备**全新空 PostgreSQL 数据库**和**尚不存在的数据目录**；保留故障实例和原备份。可信本机 Python3.12 环境安装本包依赖后：

```sh
export RESTORE_DATABASE_URL='postgresql+psycopg://<user>:<password>@127.0.0.1:<port>/<NEW_EMPTY_DATABASE>'
export RESTORE_DATA_ROOT='/absolute/path/to/NEW_archive'
.venv/bin/python -m wdh_api.cli restore /absolute/path/to/backup.wdhbak
```

口令在终端隐藏输入；自动化可用 `--password-file`，文件须0600，不能把口令写命令行或日志。也可在独立容器/恢复用 Compose 项目运行相同 CLI，但必须挂载新目标与只读备份、设置新的 RESTORE_* 环境，不得复用当前 archive/postgres 卷。

程序先验证全部认证帧、表清单/计数、媒体哈希和 schema，再迁移/填充新目标；拒绝既有非空数据库/目录。失败不销毁旧实例。成功输出表计数及对象校验结果，恢复后旧会话全部作废；重新登录，核查消息、来源哈希、搜索、附件下载，再由操作人切换部署连接。`source_counts` 是备份原计数，`counts` 是会话作废后的实际恢复计数。

合成 PostgreSQL→新 PostgreSQL 演练已通过：4个原件 SHA 核验、媒体下载字节一致、登录/检索/来源可用、旧会话拒绝。实测时间及计数在 `evidence/restore-drill.json`。尚无生产备份计划，因此不承诺生产 RPO/RTO；应按实际数据量定期演练。

## 不安装宿主 Python 的离线恢复

在已有运行包目录执行，`.env` 是受保护的本地配置。下面每次选择新的 Compose 项目名和卷，恢复成功后用5174访问；不要换成原项目名。备份路径按实际替换。

```sh
RECOVERY_PROJECT="wdh-recovery-$(date -u +%Y%m%d%H%M%S)"
recovery_compose() {
  docker compose -p "$RECOVERY_PROJECT" -f compose.yaml -f compose.offline.yaml -f compose.recovered.yaml "$@"
}
recovery_compose up -d --no-build --wait db
recovery_compose run -d --no-deps --name wdh-restore-helper api sleep 1800
docker cp /absolute/path/to/backup.wdhbak wdh-restore-helper:/tmp/input.wdhbak
# 仅改变容器临时副本的权限；源备份文件权限不变。
docker exec -u 0 wdh-restore-helper chmod 644 /tmp/input.wdhbak
docker exec -it -e RESTORE_DATA_ROOT=/var/lib/wechat-hub/restored wdh-restore-helper python -c 'import os,sys,runpy; os.environ["RESTORE_DATABASE_URL"]=os.environ["DATABASE_URL"]; sys.argv=["wdh", "restore", "/tmp/input.wdhbak"]; runpy.run_module("wdh_api.cli",run_name="__main__")'
# 确认上一步恢复成功、表计数/哈希校验通过后再启动应用。
docker rm -f wdh-restore-helper
APP_PORT=8001 WEB_PORT=5174 recovery_compose up -d --no-build --wait
```

这是独立恢复环境，原实例保持完整；不要同时将两个实例当作可写主库。成功后记录 `RECOVERY_PROJECT` 名称和端口，以便下次管理相同实例。恢复过程中断/失败则保留目标以检查，换一个全新项目重试，不自动清理或覆盖失败目标。

## 升级与回滚

升级前停止导入写入和 worker，保存已验证的加密备份、旧镜像 ID、配置恢复信息；在隔离目标演练恢复。保留旧卷后迁移/更换镜像，检查 ready、消息/附件和检索，再允许写入。默认代码不删库、不自动降级。

回滚使用与备份 schema 相符的旧镜像，在新库/新卷恢复并核查后切换。不要把旧镜像直接连接已升级的新 schema，也不要删除故障卷或覆盖唯一备份。涉及覆盖用户存储的切换/删除需要另行明确授权。
