"""
============================================================
缺集管家 - 应用包
============================================================
本包包含：
  main.py          程序入口 + 网页接口
  database.py      数据库（SQLite）
  config.py        用户设置管理
  logger.py        日志
  models.py        数据模型（数据结构定义）
  moviepilot.py    MoviePilot 客户端（订阅增删查）
  tmdb_source.py   TMDB 数据源（MP 代理 / 直连，自动切换）
  analyzer.py      缺集计算（纯逻辑，方便测试）
  scan_runner.py   扫描任务编排（后台线程 + 进度）
  scanner/         strm 文件扫描器 + Emby 扫描器
  web/             网页前端（index.html / style.css / app.js）
============================================================
"""
