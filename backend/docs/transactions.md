# 数据所有权与原子提交约定

Part 02 固定本约定。当前用 Preparation 验证事务与版本检查；SessionStore 的会话表、命令回执和任务表在后续 Part 引入，不提前创建空表或通用基类。

## 所有权与引用

- owner_id 来自已验证的当前用户，HTTP 请求不能指定或替换 owner_id。
- 资源读取和修改必须同时按 id、owner_id 过滤；不存在和不属于当前用户都返回 NOT_FOUND。
- 外键确保引用存在。新增带 owner_id 的子表引用其他业务资源时，使用父表 `(id, owner_id)` 唯一约束和子表相应复合外键，阻止跨用户引用；不能只检查 ID 存在。当前 preparations 和 login_sessions 直接引用 users，无跨业务资源引用。
- 后续 question/turn 等关联还需约束 session_id 一致；增加实际关系时才引入对应约束。
- User 的身份键是 `(issuer, subject)`，不按邮箱合并账号。登录记录由服务端控制有效期，退出删除登录记录，旧 Cookie 无法恢复身份。

## 当前事务边界

`db/session.py` 的 `async_sessionmaker.begin()` 为一次请求建立事务。Repository 和身份 service 可以 execute/flush，但不自行 commit；异常会让整个事务回滚。`Depends(..., scope="function")` 在 HTTP 成功响应发送前提交。测试覆盖已 flush 的两次写入一起回滚，以及最终提交失败不能返回 201。

并发更新使用一条 UPDATE，同时匹配 id、owner_id 和 expected_state_version，并把 state_version 加一。未更新到行时，先区分当前用户是否拥有资源：无资源返回 404，版本过期返回 409 VERSION_CONFLICT。不会自动用最新版本覆盖重试。

## SessionStore.commit 的后续实现约定

接口语义：`commit(expected_version, mutation, events, jobs) -> CommitReceipt`。mutation 的上下文必须包含已验证 actor、session_id、command_id 和 payload_hash；Worker 提交还必须携带租约 fencing token。

一次短数据库事务依次完成：

1. 验证资源 owner、命令允许状态。相同 command_id 已成功提交且 payload_hash 一致时返回已存回执；不同内容复用 ID 返回 IDEMPOTENCY_CONFLICT。
2. 以 owner_id、session_id、expected_version 做原子版本更新，Worker 同时验证租约 fencing token。版本不符返回 VERSION_CONFLICT；失效 Worker 不得写入。
3. 写入问题、回答等规范化业务数据、按会话递增 seq 的领域事件、checkpoint，以及 jobs/outbox 和命令回执。
4. 全部成功才提交；任一步失败，包含版本递增在内的所有写入全部回滚。
5. CommitReceipt 在事务成功提交后才交给传输层返回。WebSocket 发送失败不撤销已提交结果，客户端按 command_id 查回执或重试。

同一会话的版本更新行锁串行化提交；事件 `(session_id, seq)`、回执 `(session_id, command_id)` 使用唯一约束。并发重复命令等待前一事务结束后重读回执，不产生第二次业务写入。跨记录引用也在同一事务中验证。

模型、TTS、ASR 和外部通知放在事务外。任务创建与业务数据同事务，实际执行交给 Worker；Outbox 的至少一次发送和消费去重属于 Part 03。本 Part 只定义这些后续语义，不声称已实现命令幂等、事件、租约或任务系统。
