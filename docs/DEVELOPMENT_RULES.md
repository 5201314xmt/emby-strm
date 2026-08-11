# 缺集管家 v2.0 — 开发规则 / Development Rules

> **适用所有人。任何代码提交不符合本规则，直接打回。**

---

## 核心原则 / Core Principles

### 1. 先读规格 → 再改代码

修改任何代码前，必须先打开 `docs/PROJECT_SPEC.md` 确认：

- 涉及的功能模块 (F001-F015) 的输入/输出/DB 影响
- API 端点的路径、方法、参数、返回格式
- 数据模型的字段和约束
- 前端页面的交互定义

### 2. 代码服从规格 → 不许降需求

```
✅ 正确：修复代码，让它符合规格
❌ 错误：修改规格来迁就现状代码
```

### 3. 新功能先更新规格

```
1. 在 PROJECT_SPEC.md 新建功能模块条目 (F0XX)
2. 填写：目的 / 输入 / 处理 / 输出 / DB 影响 / 代码位置
3. 在 API 章节补充新端点
4. 在数据模型章节补充新表/新列
5. 然后写代码
```

### 4. Bug 修复必须记录四要素

```markdown
## Bug: <简短标题>
**问题:** <用户看到的异常行为>
**原因:** <根因分析，代码位置 + 行号>
**修改:** <改动内容，文件 + 变动>
**影响范围:** <哪些页面/接口/数据受影响>
```

### 5. 三个禁止

| ❌ | 说明 |
|----|------|
| 删除已有功能 | PROJECT_SPEC 中标记 ✅ 的模块不可移除 |
| 修改接口兼容性 | 已有 API 路径/方法/参数/返回格式不可变 |
| 只修表面问题 | 追到根因，修源不断流 |

### 6. 改后两件事

| 检查 | 命令 | 标准 |
|------|------|------|
| 后端可导入 | `python -c "from app.main import app"` | 无异常 |
| API 健康 | `curl /api/health` | 200 |
| 前端构建 | `npm run build` | 0 errors |
| 业务流程 | 手动验证 | 受影响页面链路正常 |

---

## 技术约定 / Technical Conventions

### 后端

| 规则 | 说明 |
|------|------|
| Python 3.12+ | async/await 所有 I/O |
| SQLAlchemy 查询 | 关联用 `selectinload` 防 N+1 |
| API 响应 | 统一 `{success, data, message}` → `make_response()` |
| 错误处理 | 不静默吃异常，至少记日志 |
| 敏感字段 | Token/Key 返回前 `mask_secret()` 打码 |
| JSON 默认值 | `default=list` (可调用), 禁止 `default=[]` |

### 前端

| 规则 | 说明 |
|------|------|
| TypeScript 5.5+ | 禁止 `any` (外部 API 除外) |
| React 18+ | 函数组件 + hooks |
| CSS | Tailwind, 类名合并用 `cn()` |
| 状态 | UI → Zustand, 服务端 → TanStack Query |
| API 调用 | 统一经 `lib/api.ts` (Axios) |
| React key | 禁止 `key={index}`, 必须稳定 ID |
| 三态覆盖 | Loading(Skeleton) / Error(toast) / Empty(EmptyState) |

---

## 目录规范

```
backend/app/
  api/       → HTTP+WS 路由 (薄层, 调 services/tasks)
  services/  → 业务逻辑 (算法, 外部 API)
  tasks/     → 异步任务编排 + 调度
  core/      → 基础设施 (DB, 安全, 事件, 全局状态)
  models/    → SQLAlchemy ORM (一表一文件)
  schemas/   → Pydantic 请求/响应模型

frontend/src/
  pages/        → 路由页面
  components/   → 共享组件 (layout/, shared/)
  stores/       → Zustand
  hooks/        → 自定义 hooks
  lib/          → API 客户端, WebSocket, 工具
```

---

## 数据库变更

| 规则 | 说明 |
|------|------|
| 表结构变更 | 必须 Alembic migration |
| 新增列 | nullable 或有 default |
| 外键 | 必须带 `ondelete` (CASCADE/SET NULL) |
| 迁移前 | 自动备份 (env.py) |

---

## 安全

| 规则 | 说明 |
|------|------|
| 密码 | PBKDF2-SHA256 + 随机盐, 永不存明文 |
| 验证 | hmac.compare_digest 防时序 |
| 展示 | Token/Key 打码 |
| 限速 | 登录/设密 60s/10 次 |
| Cookie | HttpOnly + SameSite=Lax |
| 挂载 | STRM 目录 `:ro` 只读 |

---

## Git 提交

```
格式: <type>: <简短中文描述>

feat     新功能
fix      Bug 修复
docs     文档
refactor 重构
chore    构建/依赖
perf     性能

示例:
  feat: 添加电影扫描支持 (F016)
  fix: 修复异常筛选映射 (P1-2)
  docs: 更新 PROJECT_SPEC 至 v2.2
```

---

## 功能开发流程

```
需求 → 更新 PROJECT_SPEC (F0XX, ⏳)
     → 设计 Schema+API → 补充第5章
     → 后端 (models→services→api→tasks)
     → 前端 (stores→pages→components)
     → 联调 + 质量门禁
     → 更新 PROJECT_SPEC (✅)
     → Git commit
```

---

## 质量门禁

| # | 检查项 | 标准 |
|---|--------|------|
| G1 | 后端可导入 | 无异常 |
| G2 | API 健康 | 200 |
| G3 | 前端构建 | 0 errors |
| G4 | TypeScript | 0 errors |
| G5 | 业务流程 | 手动验证通过 |

---

## 文档维护

| 文档 | 何时更新 | 谁更新 |
|------|---------|--------|
| PROJECT_SPEC.md | 功能变更、API 变更、数据模型变更 | 开发者 |
| DEVELOPMENT_RULES.md | 开发流程/规范变更 | 架构师 |
| README.md | 部署方式变更、大版本发布 | 维护者 |
