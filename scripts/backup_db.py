"""
============================================================
数据库手动备份工具（供 Docker 里执行）
用法：
  docker compose exec queji python scripts/backup_db.py
  （备份文件生成在 ./data/backups/ 目录，和程序自动备份放一起）

说明：
  - 程序每次数据库升级前也会自动备份，这里提供手动备份入口
  - 想彻底备份数据：把 ./data 整个目录复制走即可
============================================================
"""

import sys
import os

# 让脚本可以 import app 包（不管从哪个目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import migrations  # noqa: E402


def main():
    path = migrations.backup_db()
    if path:
        print(f"备份成功：{path}")
        print("提示：回滚时把这份备份改名为 queji.db 覆盖原文件即可")
    else:
        print("备份失败（见上方错误信息）")
        sys.exit(1)


if __name__ == "__main__":
    main()
