# OutlookEmailPlus Daytona 部署

本目录维护 OutlookEmailPlus 在 Daytona（app.daytona.io）上的快照与沙箱配置。
目标：仓库代码合并到 main 后，Daytona 中的运行镜像自动跟随更新。

## 组件

| 名称 | 说明 |
|------|------|
| 快照 `outlookmailplus` | 由仓库根目录 `Dockerfile` 构建（2 CPU / 4 GiB / 10 GiB，region: us） |
| 沙箱 `outlookmailplus` | 从快照创建，public，端口 5000，不自动停止 |
| `snapshot.sh` | 重建快照（已存在则先删除） |
| `sandbox.sh` | 重建沙箱（从快照，注入应用环境变量） |
| `app.sh` | 沙箱内启动/停止应用，输出健康检查与 24 小时预览地址 |
| `deploy.sh` | 全量刷新：快照 -> 沙箱 -> 启动 -> 预览地址 |
| `.github/workflows/daytona-snapshot.yml` | main/master/dev 合并或手动触发时自动刷新 |

## 快速开始（本地）

前置：已安装 [daytona CLI](https://www.daytona.io/docs/en/tools/cli) 并登录（或设置 `DAYTONA_API_KEY`）。

```bash
# 1. 准备密钥（不入库）
cp daytona/.env.local.example daytona/.env.local
# 编辑 daytona/.env.local，填入 OEMP_SECRET_KEY / OEMP_LOGIN_PASSWORD

# 2. 全量部署
bash daytona/deploy.sh

# 3. 仅重建沙箱或查看状态
bash daytona/sandbox.sh
bash daytona/app.sh status
```

## CI 自动刷新

push 到 `main` / `master` / `dev`（命中相关路径）或手动触发
`Refresh Daytona Snapshot` 工作流时：

1. 从仓库 `Dockerfile` 重建快照（删除旧快照后重建）。
2. 删除旧沙箱并以新快照重建。
3. 启动应用并输出预览地址。

需要以下 GitHub Secrets（仓库 Settings -> Secrets and variables -> Actions）：

| Secret | 说明 |
|--------|------|
| `DAYTONA_API_KEY` | Daytona API Key（app.daytona.io/dashboard/keys） |
| `OEMP_SECRET_KEY` | 应用 SECRET_KEY，用于加密数据库敏感字段 |
| `OEMP_LOGIN_PASSWORD` | 应用登录密码 |

> 注意：`SECRET_KEY` 一旦用于写入数据库，更换会导致旧数据无法解密。
> CI 重建沙箱使用容器本地磁盘存储数据库（`/app/data`），重建后数据重置，属于预期行为。

## 已知限制

- 不使用 Daytona volume：当前组织的存储后端为 S3（mountpoint-s3），SQLite 在其上
  写入会报 `disk I/O error`。数据库存放在沙箱本地磁盘。
- 预览地址最长 24 小时；过期后运行 `bash daytona/app.sh start` 重新生成。
- 快照与沙箱配额受组织层限制约束；如需扩容调整：

  ```bash
  SNAPSHOT_NAME=outlookmailplus bash daytona/snapshot.sh --help
  ```

  （资源参数可在 `snapshot.sh` 中调整，例如 `--cpu 4 --memory 8`。）

## 参考

- Daytona 官方 Agent Skill：github.com/daytona/skills（技能名 `daytona`）
- Daytona 文档：https://www.daytona.io/docs/en/snapshots
- 官方 CLI 参考：https://www.daytona.io/docs/en/tools/cli
