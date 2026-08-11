# 缺集管家 v2.0

自动扫描 STRM/Emby 媒体库 → 对比 TMDB 计算缺集 → 一键提交 MoviePilot 补全。

**Docker 一条命令部署 | 暗色 MoviePilot 风格面板 | 模块化前后端**

---

## 一、工作原理

```
你的 STRM 目录 ──扫描──▶ 目前有哪些集
                         │ 对比
TMDB 数据源 ─────────▶ 该有多少集
                         │
                    缺集清单 → 一键/自动提交 MoviePilot 订阅
```

> STRM 文件名需包含 TMDB 编号（绝大多数工具默认生成），程序自动识别各种格式。

---

## 二、部署（3 步）

### 第 1 步：获取代码

```bash
git clone https://github.com/5201314xmt/emby-strm.git
cd emby-strm
```

### 第 2 步：配置

```bash
cp .env.example .env
```

编辑 `.env`，必填项：

```env
MEDIA_DIR=/你的strm目录的宿主机绝对路径
# 例：/mnt/nas/video/strm 或 C:\Users\xxx\Videos\strm

# 可选
APP_PORT=8899                # 网页端口，默认 8899
DATA_DIR=./data              # 数据存储目录
```

> 有多个 STRM 目录？取消 `docker-compose.yml` 中第 27 行注释，并在 `.env` 加 `MEDIA_DIR2=...`

### 第 3 步：启动

```bash
docker compose up -d --build
```

浏览器打开 **`http://服务器IP:8899`**。

> 首次打开进入安装向导：设置管理员密码 → 后续在设置页填 MoviePilot 地址和 Token → 添加扫描源 → 开始扫描。

常用命令：

```bash
docker compose logs -f              # 查看日志
docker compose up -d --build        # 升级重构建
docker compose down                 # 停止
```

数据都在 `./data` 目录，**复制它 = 备份一切**。

---

## 三、网页功能

### 仪表盘

6 个 KPI 卡片（剧集数 / 缺集总数 / 整季缺失 / 已订阅 / 部分缺失 / 未识别）+ 扫描进度条 + 历史记录 + 快捷操作按钮。

### 缺集列表（高密度表格）

- **筛选**：全部 / 缺集补全 / 整季缺失 / 已完成 / 已忽略 / 异常
- **搜索**：剧名关键字
- **行内操作**：订阅 / 忽略某季 / 忽略整部剧
- **批量操作**：勾选多行 → 批量订阅 / 批量忽略
- **展开详情**：点击箭头展开，查看每集号列表
- **状态标签**：complete / partial / full_missing / degraded（数据降级）

### 订阅管理

查看 MoviePilot 订阅列表 + 同步状态 + 删除订阅。

### 扫描源

添加 / 编辑 / 删除 STRM 目录或 Emby 源，每个源独立管理。

### 设置（分组卡片）

| 分组 | 内容 |
|------|------|
| MoviePilot | 地址、Token、连接状态 |
| TMDB | API Key（v3 无需填写）、语言 |
| 自动化 | 自动扫描开关、间隔、自动订阅、特别篇 |
| 安全 | 修改密码 |

### 日志

按级别/分类筛选 + 关键字搜索 + 可复制消息。

---

## 四、常见问题

**Q：扫描发现很多"未识别文件"？**  
A：文件/目录名缺少 TMDB 编号或集数信息。在未识别列表可查看原因。

**Q：会不会重复下载已有集？**  
A：不会。MoviePilot 会跳过已有集；本地记录避免重复提交。

**Q：TMDB 故障时会不会批量误订阅？**  
A：不会。故障数据标记 `degraded`，自动订阅跳过这些季。手动订阅会提示风险。

**Q：忘了密码？**  
A：执行：
```bash
docker compose exec queji python -c "import sqlite3; sqlite3('/app/data/queji.db').execute('DELETE FROM settings WHERE key=\"admin_password_hash\"').connection.commit()"
docker compose restart
```
重启后重新设置密码。

**Q：想用 Emby 而非 STRM 目录？**  
A：在扫描源页添加类型为 `emby` 的源，填 Emby 地址和 API Key。

**Q：第二/多次扫描为什么很快？**  
A：TMDB 数据有三级缓存（内存 → 磁盘 → 网络），缓存后大幅加速。

**Q：怎么刷新 TMDB 数据？**  
A：设置页 → 清空 TMDB 缓存 → 重新扫描。

---

## 五、项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py             # pydantic-settings 配置
│   │   ├── core/                 # 基础设施
│   │   │   ├── database.py       # SQLAlchemy async + WAL
│   │   │   ├── security.py       # 密码哈希 + 会话
│   │   │   └── events.py         # 事件总线（WebSocket 推送）
│   │   ├── models/               # 11 张表 ORM 模型
│   │   ├── schemas/              # Pydantic 请求/响应
│   │   ├── api/                  # 30+ REST 端点 + WebSocket
│   │   ├── services/             # 业务逻辑
│   │   │   ├── scanner/          # STRM / Emby 扫描器
│   │   │   ├── tmdb.py           # TMDB 三级缓存
│   │   │   ├── analyzer.py       # 缺集计算引擎
│   │   │   └── moviepilot.py     # MoviePilot 客户端
│   │   └── tasks/                # 扫描任务编排 + 调度
│   ├── alembic/                  # 数据库迁移
│   └── requirements.txt
│
├── frontend/
│   └── src/
│       ├── components/           # 布局 + 共享组件
│       ├── pages/                # 6 页面
│       ├── stores/               # Zustand 状态管理
│       ├── hooks/                # 自定义 hooks
│       └── lib/                  # API 客户端 + WebSocket
│
├── Dockerfile                    # 多阶段构建
├── docker-compose.yml
└── .env.example
```

---

## 六、技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 + SQLite (aiosqlite) |
| 前端 | React 18 + TypeScript + Tailwind CSS + Vite |
| 实时 | WebSocket 推送（进度 / 日志 / 事件） |
| 部署 | Docker 多阶段构建（npm build → Python image） |

---

## 七、免责声明

- 请只补全你有权观看的内容
- 本项目只做"发现缺集 + 调用 MoviePilot 订阅"，不参与任何下载行为
