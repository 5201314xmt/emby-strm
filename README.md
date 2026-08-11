# 缺集管家（Emby 缺集管理 + MoviePilot 自动补全）

一个**给小白用的**媒体库缺集管理工具：

- 扫描你的 **strm 文件目录**（或 Emby 媒体库），自动识别每部剧、每一季**缺了哪些集**
- 网页面板展示缺集情况，**一键订阅**给 MoviePilot 下载补全
- 支持**全自动模式**：定时扫描 + 发现缺集自动订阅，完全不用管
- Docker 一条命令部署，全中文界面

---

## 一、工作原理（30 秒看懂）

```
你的 strm 目录 ──扫描──▶ 目前有哪些集
                           │ 对比
TMDB 数据（经 MoviePilot）─▶ 这部戏每季总共该有多少集
                           │
                       缺集清单（网页展示）
                           │ 一键/自动
                    MoviePilot 订阅下载补全
```

> 注意：你的 strm 文件目录里要**带有 TMDB 编号**（绝大多数 strm 工具生成的都是这样，比如 `权力的游戏 (TMDB-1399)/Season 01/xxx.strm`），程序能自动识别各种常见格式。

---

## 二、部署（3 步）

### 第 1 步：准备

需要的东西：

| 需要什么 | 哪里拿 |
|---|---|
| MoviePilot 地址 | 你安装 MoviePilot 的地址，如 `http://192.168.1.100:3000` |
| MoviePilot API Token | MoviePilot 网页 → **设置 → 安全 → API 令牌** |
| strm 文件目录 | 你放 strm 文件的目录，如 `/volume1/media/tv` |

> TMDB API Key **不需要**！MoviePilot v3 会帮你代理 TMDB 数据。
> 如果用的是老版 MoviePilot（v2 且不支持 TMDB 代理），需要在设置页填一个免费的 TMDB API Key（去 https://www.themoviedb.org/settings/api 申请，教程网上很多）。

### 第 2 步：启动（二选一，推荐方式 A）

**方式 A：docker run 一条命令（最简单，只改两个路径）**

```bash
docker run -d --name queji --restart unless-stopped \
  -p 8899:8899 \
  -v /你的strm目录:/media:ro \
  -v /你的数据目录:/app/data \
  你的镜像地址/queji:latest
```

- `/你的strm目录` → 改成你服务器上 strm 文件所在的真实路径（有多个目录就多写一行 `-v`）
- `/你的数据目录` → 改成你想存数据的地方（如 `/volume1/docker/queji-data`）

**方式 B：docker compose（适合已经用 compose 的用户）**

```bash
git clone https://github.com/你的地址/emby缺集管家.git
cd emby缺集管家
# 复制一份 .env 并改一行（MEDIA_DIR=你的strm目录）
cp .env.example .env
# 或者直接运行一键安装脚本（会问你目录并自动配置）
bash install.sh
```

Linux/群晖 NAS 用户推荐直接跑 `bash install.sh`，全程只回答一个问题。

### 第 3 步：网页设置

浏览器打开 **http://服务器IP:8899**：

1. 首次打开会进入**安装向导**：设置管理员密码 → 填 MoviePilot 地址和 Token → 填 strm 目录 → 一键开始扫描，全程网页操作
2. 之后每次使用需要先**登录**（密码就是向导里设置的那个）

> 为什么有密码？防止局域网里其他人（或公网暴露时）乱动你的订阅。

常用命令：

```bash
docker compose logs -f     # 查看运行日志
docker compose up -d --build   # 升级/重新构建
docker compose down        # 停止
docker compose exec queji python scripts/backup_db.py   # 手动备份数据库
```

数据都在 `./data` 目录（compose）或你挂载的数据目录（docker run），**备份它 = 备份一切**。

---

## 三、网页使用说明

### 概览页
- 统计卡片：剧集数 / 缺集总数 / 整季缺失 / 已订阅
- 大按钮「**开始扫描**」，点一下扫描全库（进度条 + 预计剩余时间）
- 两个懒人开关：
  - **自动扫描**：每隔 N 小时自动扫一次（设置里改间隔）
  - **自动订阅**：扫描后自动把缺的集提交给 MoviePilot
- 「**先看看要订阅什么**」：预览待订阅清单（模拟订阅），确认后才真正提交
- 「订阅所有缺集」：一键全交，适合不挑食的用户（有确认弹窗）

### 缺集列表页
- 筛选：全部 / 缺集补全 / 整季缺失 / 已完整 / 已忽略 / 识别异常 / 未识别文件
- 每部剧一张卡片，每季一行，直接显示缺哪些集，如：`第1季 已有 3/6 集 缺: 3, 5, 6`
- 按钮说明：
  - `订阅缺集` → 把这一季缺的集交给 MoviePilot 下载（MP 会自动跳过已有的集）
  - `订阅整季` → 整季都没有时的订阅按钮
  - `忽略这季` / `忽略整部` → 不想补的剧藏起来，不再提醒
- 已订阅的季会显示绿色「已订阅」标签，状态实时同步

### 订阅管理页
- 查看 MoviePilot 里所有订阅及状态（等待搜索 / 搜索中 / 已完成）
- 可删除订阅、手动刷新状态

### 设置页
| 设置项 | 说明 |
|---|---|
| MoviePilot 地址 / API Token | 必填，Token 在 MP 的 设置→安全 里；显示 ****** 开头表示没修改 |
| strm 文件目录 | 每行一个，填**容器内**的路径（即 compose 里映射的 `/media`） |
| Emby 地址 / API Key | 可选；不挂载目录、走 Emby API 时用 |
| 自动扫描 / 间隔 | 懒人模式 |
| 自动订阅 | 扫描完自动把缺集交给 MP（数据不准的季会自动跳过） |
| 检测特别篇 S00 | 一般不用开 |
| TMDB API Key | 备用；MP v3 无需填 |
| 清空 TMDB 缓存 | 剧集有更新但扫描没发现时点一下，下次扫描重新获取 |
| 修改密码 | 需要当前密码；改完后其他设备要重新登录 |

> 改完点「保存设置」，再用「测试连接」确认 MP / TMDB / Emby 都通了再扫描。

---

## 四、常见问题（FAQ）

**Q：扫描完发现很多"未识别文件"？**
A：说明这些文件的目录/文件名里没有 TMDB 编号或集数。可以看"未识别文件"标签里的原因，把文件重新命名即可。

**Q：为什么订阅后迟迟没下载？**
A：MoviePilot 默认定时搜索（可调）。创建订阅时程序也会尝试让 MP 立即搜索，老版本 MP 不支持时等定时即可。

**Q：会不会把已有的集重复下载？**
A：不会。两层保险：① MoviePilot 订阅会结合媒体库自动跳过已存在的集；② 本工具本地记录每个季的订阅状态，同一季只提交一次，且 MP 拒绝重复订阅。

**Q：扫描要很久怎么办？**
A：TMDB 数据有缓存（磁盘+内存），第二次扫描会快很多。10 万部剧的库冷启动要几小时（受 TMDB 接口限制），但缓存后再次扫描只需几分钟。想彻底刷新数据去设置页「清空 TMDB 缓存」。

**Q：数据不准的季会误订阅吗？**
A：不会。TMDB 临时故障时数据会标记"可能不准"，这些季**永远不会被自动订阅**，网页上也会显示黄色标签提示。

**Q：忘了管理员密码怎么办？**
A：执行下面两条命令重置（只重置密码，扫描结果等数据不会丢）：
```bash
docker compose exec queji python -c "from app import database; database.execute('DELETE FROM settings WHERE key=?', ('admin_password_hash',))"
docker compose restart
```
重启后打开网页会重新进入"设置密码"向导。

**Q：改了 strm 目录结构，怎么刷新？**
A：直接点「开始扫描」即可，每次扫描都会重新计算全量结果。

**Q：数据库在哪？想备份？**
A：`./data/queji.db` 一个文件，备份它就行。

---

## 五、项目结构（想改代码的看这里）

```
app/
├── main.py             # 程序入口 + 所有网页接口
├── auth.py             # 登录认证（密码哈希 + 会话）
├── database.py         # 数据库（SQLite，WAL 模式 + 批量事务）
├── migrations.py       # 数据库自动迁移（升级前自动备份）
├── config.py           # 设置管理（加新配置项只需加一行）
├── logger.py           # 日志
├── models.py           # 数据结构定义
├── moviepilot.py       # MoviePilot 客户端（订阅增删查）
├── tmdb_source.py      # TMDB 数据源（磁盘缓存 + 故障兜底）
├── analyzer.py         # 缺集计算（纯逻辑，有单测）
├── scan_runner.py      # 扫描任务编排
├── scanner/
│   ├── filesystem.py   # strm 文件扫描（自动识别各种命名）
│   └── emby.py         # Emby API 扫描（可选）
└── web/                # 网页前端（原生 JS，无框架：登录页/安装向导/主面板）
scripts/
└── backup_db.py        # 手动备份数据库（容器内执行）
tests/                  # 测试（单元/接口/压力 + 端到端）
```

### 本地开发 / 跑测试

```bash
pip install -r requirements.txt
python -m pytest tests -v          # 单元测试
python -m uvicorn app.main:app --port 8899   # 本地启动
```

端到端测试（需要两个终端）：

```bash
# 终端1：启动模拟 MoviePilot
python tests/mock_mp.py

# 终端2：启动缺集管家 + 跑测试
python -m uvicorn app.main:app --port 18999
python tests/e2e_test.py
```

---

## 六、免责说明

- 请只补全你有权观看的内容
- 本项目只做"发现缺集 + 调用 MoviePilot 订阅"，不参与任何下载行为
