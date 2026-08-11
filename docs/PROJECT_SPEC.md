# 缺集管家 v2.0 — 产品规格文档 / Product Specification

> **适用范围：** 所有代码修改、功能开发、Bug 修复必须以此文档为唯一功能依据。
> 如文档与代码不一致，以本文档为准，并更新代码以匹配文档。

| 字段 | 值 |
|------|-----|
| 版本 | 2.4.1 |
| 最后更新 | 2026-08-12 |
| 维护者 | 产品负责人 / 架构师 |

## 变更记录 / Changelog

### v2.4.1 (2026-08-12)
- fix: 批量订阅/忽略返回422 — 路由顺序冲突 `/{tmdb_id}` 抢走 `/batch/...`
  - 所有动态路由 `{tmdb_id}` 加 `:int` 类型限定
  - Starlette 路由匹配: `/batch/subscribe` 不再被 int 路由拦截
- fix: 前端批量订阅成功/失败判断缺失 — `res.data.success` 未检查
- fix: BatchActionBar 增加 loading 态防重复点击
- fix: 批量订阅失败详情逐条展示 (fail_msgs)

### v2.4.0 (2026-08-11)
- fix: 设置页布尔开关反跳 — `auto_scan`/`auto_subscribe`/`include_specials` 归一化为 "1"/"0"
- fix: `/api/settings` GET 敏感字段返回打码值，密钥不再泄露到浏览器
- fix: 扫描 `source_ids` 筛选实际生效
- fix: 未识别文件按源删除，中断不丢数据
- fix: 重复订阅防 IntegrityError 白屏
- fix: MissingPage 移除页面级假角标
- feat: 缺集列表排序(缺集多→少 / 缺集少→多 / 剧名)
- feat: 搜索支持 TMDB ID + 防抖 300ms
- feat: Dashboard 扫描速度 + KPI空引导 + 历史详情链接
- feat: LogsPage 自动刷新(5s)
- feat: MoviePilot 连接多端点探测 + Authorization/X-API-Key 双认证头
- feat: MoviePilot/TMDB 配置从 DB 读取，网页配置热更新

### v2.3.0 (2026-08-11) — 审计修复版
- 3 CRITICAL: WS断开内存泄漏 / ws_router重复注册 / asyncio.run crash
- 3 HIGH: SQL注入→bindparams / select-all受控组件 / authStore错误保留initialized
- 5 P1: Emby源UI / 异常筛选 / include_specials保存 / 扫描恢复 / 旧客户端关闭
- 4 P2: 全局搜索 / Emby分页 / 安装向导 / 日志分页

---

## 1. 项目定位 / Project Positioning

### 1.1 一句话描述

**缺集管家** 是一个 Docker 部署的 Web 应用：扫描 STRM 文件或 Emby 媒体库 → 对比 TMDB 剧集数据 → 计算缺集 → 一键提交 MoviePilot 订阅补全。

### 1.2 解决的问题

| 问题 | 方案 |
|------|------|
| 手动排查媒体库缺集耗时 | 全自动扫描 + TMDB 对比 |
| 手动逐个创建 MP 订阅 | 一键/批量/自动订阅 |
| TMDB 故障时分析崩溃 | 三级缓存衰落 + degraded 标记 |
| 忘记已订阅/已忽略 | 订阅管理页 + 忽略系统 |

### 1.3 目标用户

- 中文 NAS 用户，已部署 MoviePilot v3
- 已有 STRM 文件库或 Emby 媒体库
- 非技术人员

### 1.4 使用环境

| 要素 | 规格 |
|------|------|
| 部署 | Docker Compose 单容器 |
| 数据库 | SQLite (aiosqlite + SQLAlchemy 2.0) |
| 依赖服务 | MoviePilot v3（TMDB 代理 + 订阅执行） |
| 可选服务 | Emby Server（API 扫描源） |
| 浏览器 | Chrome/Edge/Firefox |

### 1.5 不做什么 / Non-Goals

| ❌ | 说明 |
|----|------|
| 不生成 STRM 文件 | 只扫描已有文件 |
| 不支持电影 | 仅处理 TV Shows |
| 不管理文件组织 | 不重命名/移动/删除 |
| 不参与下载 | 只提交订阅，由 MP 执行 |

---

## 2. 核心业务流程 / Core Business Flow

### 2.1 首次安装

```
访问 → 未初始化 → /setup 设置密码 → 自动登录 → /dashboard
                  → /settings 配置 MP → /sources 添加源 → 开始扫描
```

### 2.2 扫描→分析→订阅 完整链路

```
用户点"开始扫描"
  → 遍历 sources → filesystem(os.walk+regex) 或 emby(HTTP API, 分页)
  → 多源取并集去重 (merge_scan_results)
  → TMDB 查询 (MP代理优先, 三级缓存, 网络失败退回旧缓存)
  → 缺集计算 (已播出 - 已有 = 缺失, status判定)
  → 写入 DB (shows upsert, seasons 全量重写, unrecognized 全量重建)
  → 同步 MP 订阅状态
  → 自动订阅 (可选, skipped degraded)
  → 完成 (记录 last_scan, 写 ScanJob missing_count)
```

### 2.3 用户操作链路

```
/dashboard → 点KPI"缺集总数" → /shows?status=partial
  → 筛选/搜索/分页 → 单季订阅/批量订阅/忽略
  → MoviePilot API → 本地 Subscription 记录
```

---

## 3. 功能模块清单 / Feature Modules

### F001: 系统初始化与安全

| 属性 | 内容 |
|------|------|
| **目的** | 保护管理后台 |
| **处理** | PBKDF2-SHA256 + hmac.compare_digest + Session (30天) |
| **DB** | settings (admin_password_hash), sessions |
| **代码** | core/security.py, api/auth.py |
| **前端** | LoginPage, SetupPage (步骤指示器) |
| **状态** | ✅ Complete |

### F002: 扫描源管理

| 属性 | 内容 |
|------|------|
| **目的** | 管理 STRM 目录 / Emby 服务器 |
| **处理** | CRUD + 连通测试 (os.listdir 或 HTTP /emby/System/Info) |
| **DB** | sources |
| **代码** | api/sources.py, models/source.py |
| **前端** | SourcesPage (类型选择器 STRM/Emby + Emby URL/Key 字段) |
| **状态** | ✅ Complete |

### F003: STRM 文件扫描

| 属性 | 内容 |
|------|------|
| **目的** | 从 STRM 文件提取已有集 |
| **处理** | os.walk → 正则匹配 TMDB ID/季号/集号 (支持多格式) |
| **输出** | `{tmdb_id: {seasons: {1: [eps]}}}` + 未识别列表 |
| **代码** | services/scanner/filesystem.py |
| **状态** | ✅ Complete |

### F004: Emby API 扫描

| 属性 | 内容 |
|------|------|
| **目的** | 通过 Emby API 获取已有集 |
| **处理** | Users→Series(分页 200/page)→Episodes(分页 500/page), 提取 ProviderIds.Tmdb |
| **代码** | services/scanner/emby.py |
| **状态** | ✅ Complete |

### F005: TMDB 数据获取

| 属性 | 内容 |
|------|------|
| **目的** | 获取季列表 + 集数 + 播出日期 |
| **处理** | MP 代理优先 → 直连兜底, 三级缓存(内存→SQLite→网络, 24h TTL) |
| **DB** | tmdb_cache |
| **代码** | services/tmdb.py, services/tmdb_models.py |
| **状态** | ✅ Complete |

### F006: 缺集计算引擎

| 属性 | 内容 |
|------|------|
| **目的** | 计算每季缺失集 |
| **处理** | 过滤已播出 → 差集 → 状态判定 (complete/partial/full_missing) |
| **代码** | services/analyzer.py |
| **状态** | ✅ Complete |

### F007: 缺集列表展示

| 属性 | 内容 |
|------|------|
| **目的** | 高密度表格展示所有缺集 |
| **处理** | selectinload 防N+1, 筛选(6态)/搜索/分页/批量操作/展开详情 |
| **DB** | shows, seasons, subscriptions, ignored, sources |
| **代码** | api/shows.py |
| **前端** | MissingPage (status 字段支持异常筛选) |
| **状态** | ✅ Complete |

### F008: 订阅管理

| 属性 | 内容 |
|------|------|
| **目的** | 向 MoviePilot 提交订阅 + 跟踪状态 |
| **处理** | mp_client.create_subscribe → 写 subscriptions → search_subscribe (可选) |
| **DB** | subscriptions |
| **代码** | api/shows.py, api/subscriptions.py, services/moviepilot.py |
| **前端** | MissingPage (行内订阅), SubscriptionsPage |
| **状态** | ✅ Complete |

### F009: 批量操作

| 属性 | 内容 |
|------|------|
| **目的** | 一次操作多个季 |
| **处理** | 遍历 items → 逐个调用 MP/写 ignored |
| **代码** | api/shows.py |
| **前端** | BatchActionBar |
| **状态** | ✅ Complete |

### F010: 自动扫描调度

| 属性 | 内容 |
|------|------|
| **目的** | 按间隔定时扫描 |
| **处理** | 60s 轮询 → auto_scan=1 AND elapsed ≥ interval → start_scan |
| **DB** | settings (last_scan, auto_scan, scan_interval) |
| **代码** | tasks/scheduler.py, tasks/manager.py |
| **状态** | ✅ Complete |

### F011: 实时推送 (WebSocket)

| 属性 | 内容 |
|------|------|
| **目的** | 扫描进度/事件实时推送到前端 |
| **事件** | scan.progress/completed/failed/paused/resumed/cancelled, dashboard.refresh |
| **代码** | api/ws.py, core/events.py |
| **前端** | lib/ws.ts, hooks/useWebSocket.ts |
| **状态** | ✅ Complete |

### F012: 日志系统

| 属性 | 内容 |
|------|------|
| **目的** | 运维日志, 筛选/搜索/分页 |
| **处理** | 双写(终端+SQLite), 5000条自动清理, 分页(page/page_size) |
| **DB** | logs |
| **代码** | services/logger.py, api/logs.py |
| **前端** | LogsPage ("加载更多" 翻页) |
| **状态** | ✅ Complete |

### F013: 设置管理

| 属性 | 内容 |
|------|------|
| **目的** | 管理 MP/TMDB/自动化配置 |
| **处理** | DB upsert → reload_clients() 热更新 (先关旧客户端) |
| **DB** | settings |
| **代码** | api/settings.py, core/app_state.py |
| **前端** | SettingsPage (include_specials 已修复保存) |
| **状态** | ✅ Complete |

### F014: 仪表盘

| 属性 | 内容 |
|------|------|
| **目的** | 首页总览: KPI + 扫描进度 + 历史 + 快捷操作 |
| **处理** | 聚合 6 KPI + 当前 ScanJob + 最近 3 次 |
| **DB** | shows, seasons, subscriptions, scan_jobs, unrecognized_files |
| **代码** | api/dashboard.py |
| **前端** | DashboardPage |
| **状态** | ✅ Complete |

### F015: 扫描中断恢复 (v2.1 新增)

| 属性 | 内容 |
|------|------|
| **目的** | 容器重启后自动恢复未完成扫描 |
| **处理** | 启动时查询 status∈{running,paused} 的 ScanJob → 标记 failed + 写原因 |
| **代码** | main.py `_recover_scan_jobs()` |
| **状态** | ✅ Complete |

---

## 4. 数据模型 / Data Models

### 4.1 表清单

| 表 | 主键 | 用途 | 关键外键 |
|----|------|------|---------|
| shows | tmdb_id | 每部剧 | — |
| seasons | id (auto) | 每季缺集详情 | tmdb_id→shows CASCADE |
| sources | id (auto) | 扫描源 | — |
| scan_jobs | id (auto) | 扫描任务 | — |
| subscriptions | id (auto) | 本地订阅记录 | tmdb_id→shows CASCADE |
| ignored | id (auto) | 忽略记录 | tmdb_id→shows CASCADE |
| settings | key | 系统配置 KV | — |
| sessions | token | 登录会话 | — |
| logs | id (auto) | 操作日志 | — |
| unrecognized_files | id (auto) | 未识别文件 | source_id→sources SET NULL |
| tmdb_cache | (tmdb_id, season) | TMDB 磁盘缓存 | — |

### 4.2 ScanJob 状态机

```
pending → running → completed
                → failed
                → cancelled
        running → paused → running
```

### 4.3 Season 状态

```
complete — 完整
partial — 缺部分
full_missing — 整季缺失
```

---

## 5. API 规范 / API Specification

所有返回: `{success: bool, data?: any, message: string}`

### 5.1 Auth (5 端点)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | /api/auth/status | 登录状态 | No |
| POST | /api/auth/setup | 首次设密 | No |
| POST | /api/auth/login | 登录 | No |
| POST | /api/auth/logout | 退出 | Cookie |
| POST | /api/auth/change-password | 改密 | Yes |

### 5.2 Dashboard (1 端点)

| GET | /api/dashboard | 聚合KPI+扫描+历史 | Yes |

### 5.3 Shows (7 端点)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | /api/shows | 列表(?status/search/page) | Yes |
| GET | /api/shows/{tmdb_id} | 单剧详情 | Yes |
| POST | /api/shows/{tmdb_id}/subscribe | 订阅某季 | Yes |
| POST | /api/shows/{tmdb_id}/ignore | 忽略某季/整部 | Yes |
| DELETE | /api/shows/{tmdb_id}/ignore | 取消忽略 | Yes |
| POST | /api/shows/batch/subscribe | 批量订阅 | Yes |
| POST | /api/shows/batch/ignore | 批量忽略 | Yes |

### 5.4 Scan (6 端点)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | /api/scan/start | 开始扫描 | Yes |
| POST | /api/scan/{job_id}/pause | 暂停 | Yes |
| POST | /api/scan/{job_id}/resume | 继续 | Yes |
| POST | /api/scan/{job_id}/cancel | 取消 | Yes |
| GET | /api/scan/{job_id}/status | 进度(HTTP降级) | Yes |
| GET | /api/scan/history | 历史(?page) | Yes |

### 5.5 Others

| Category | Endpoints |
|----------|----------|
| Subscriptions (3) | GET /api/subscriptions, POST refresh, DELETE {mp_id} |
| Sources (6) | CRUD + check + check-path |
| Settings (3) | GET, PUT (热更新), POST test |
| Logs (2) | GET (?page/page_size/level/category/search), DELETE |
| Other (2) | GET /api/health, POST /api/cache/clear |
| WebSocket (1) | WS /ws (7 种事件推送) |

---

## 6. 前端页面 / Frontend Pages

| 路由 | 页面 | 功能 | 状态覆盖 |
|------|------|------|---------|
| /setup | SetupPage | 设密码 + 步骤指示 | Loading / Error |
| /login | LoginPage | 登录 | Loading / Error |
| /dashboard | DashboardPage | KPI+进度+历史+快捷操作 | Skeleton |
| /shows | MissingPage | 高密度表格(筛选/搜索/批量/展开) | Skeleton / Empty / BatchBar |
| /subscriptions | SubscriptionsPage | 订阅列表+刷新+删除 | Skeleton / Empty |
| /sources | SourcesPage | 源卡片+添加(STRM/Emby)+编辑+测试+按源扫描 | Skeleton / Empty / Form |
| /settings | SettingsPage | 分组卡片(MP/TMDB/自动化/安全) | Skeleton / Saving |
| /logs | LogsPage | 日志表格(筛选/搜索/复制/清空/翻页) | Skeleton / Empty |

---

## 7. 自动任务 / Automated Tasks

| 任务 | 触发 | 频率 | 代码 |
|------|------|------|------|
| 定时扫描 | auto_scan=1 AND 距 last_scan ≥ interval 小时 | 60s 检查 | tasks/scheduler.py |
| 后台扫描 | 手动或自动触发 | 单例, 可暂停/取消 | tasks/manager.py + tasks/scan.py |
| WebSocket 推送 | scan pipeline 发布事件 | 实时 | core/events.py + api/ws.py |
| 扫描恢复 | 容器启动 | 一次 | main.py _recover_scan_jobs() |

---

## 8. 异常处理规范 / Error Handling

| 场景 | 处理 | 用户可见 |
|------|------|---------|
| TMDB 请求失败 | 退旧缓存 → data_quality=degraded | 黄色 "降级" 标签 |
| TMDB 无缓存 | build_fallback_episodes → degraded | 同上 |
| MP 无法连接 | 退回本地 subscriptions 记录 | 警告 toast |
| MP 重复订阅 | 静默记录本地, state=R | — |
| 文件扫描目录不存在 | 跳过该源, 记 unrecognized | 未识别列表 |
| 并发扫描 | RuntimeError | Toast: "已有扫描任务在运行" |
| 扫描中重启 | 启动时标记 failed | 仪表盘历史 |
| 登录错误 | 延迟1秒+限速(60s/10次) | "密码不正确" / 429 |
| Session 过期 | 401 → 跳转 /login | 自动跳转 |

---

## 9. 已知问题 / Known Issues

### P2 — 优化 (v2.1 剩余)

| # | 描述 | 位置 |
|---|------|------|
| P2-5 | 日志无自动刷新 | LogsPage.tsx |
| P2-6 | MissingPage "select all" 复选框非受控 | MissingPage.tsx |
| P2-7 | Emby 扫描器无用户过滤(取第一个非管理员) | emby.py |

### 未来开发

| 优先级 | 功能 |
|--------|------|
| Medium | 电影支持 (Movies) |
| Medium | 导出缺集清单 (CSV) |
| Medium | Webhook 通知 |
| Long | PostgreSQL 支持 |
