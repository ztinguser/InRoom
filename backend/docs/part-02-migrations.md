# Part 02 数据库迁移验证

日期：2026-09-06。本记录保留初次开发库迁移证据；后续完整验收见 [Part 02 验收记录](part-02.md)。

## 实现

- `alembic.ini`：迁移位置配置；连接地址统一从 Settings 读取。
- `migrations/env.py`：异步迁移入口，加载 `backend.db.models.Base.metadata`。Windows 使用 Selector 事件循环，避免 Psycopg 与 Proactor 不兼容。
- `0001_initial.py`：创建 users、preparations、login_sessions 和必要外键、索引。
- `0002_preparation_version.py`：添加非空 state_version，数据库默认值为 1。

## 实际验证

使用 Compose 中已运行的 PostgreSQL 17.6，仅操作本地 `127.0.0.1:5432/inroom` 开发库。开始时 public schema 无业务表。

| 检查 | 结果 |
|---|---|
| 空库升级至 0001 | 成功，current 返回 0001 |
| 在 0001 插入用户和准备工作区 | 成功 |
| 升级至 head | 成功，current 返回 0002 (head) |
| 旧数据保留 | 工作区仍为 DRAFT，state_version 为 1 |
| alembic check | No new upgrade operations detected. |
| 不存在的迁移目标 | does_not_exist 被拒绝，进程退出码非零 |
| 失败后的版本 | 仍为 0002 |

演示用户 issuer 为 `migration-example`、subject 为 `example-user`，用户 ID 为 `00000000-0000-0000-0000-000000000001`。准备工作区 ID 为 `00000000-0000-0000-0000-000000000002`。这些合成验证数据保留在开发库中，可用于复查，不是 OIDC 登录用户。

运行使用项目内 `.pytest_cache/structure-env` 的 Python 3.12 与已锁定依赖。常规开发可在 backend 目录运行 `uv run alembic current` 和 `uv run alembic check` 复查。

初次迁移未覆盖的迁移中途失败、用户隔离、业务事务回滚、并发冲突和真实 OIDC 登录，现已由 Part 02 集成测试补齐。降级删除字段/表未作为验收动作执行。
