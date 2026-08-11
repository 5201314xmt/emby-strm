#!/usr/bin/env bash
# ============================================================
# 缺集管家 v2.0 - 一键安装脚本
# 用法：  bash install.sh
# 自动问你的 STRM 目录，生成 .env，构建并启动
# ============================================================
set -e

echo "=============================================="
echo "  缺集管家 v2.0 - 一键安装"
echo "=============================================="

# 1. 检查 docker
if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 没找到 Docker，请先安装："
  echo "  群晖：套件中心安装 Container Manager"
  echo "  其他 Linux：curl -fsSL https://get.docker.com | bash"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "[错误] docker compose 不可用，请升级 Docker（20.10+）"
  exit 1
fi

# 2. 询问 STRM 目录
if [ -n "$MEDIA_DIR" ]; then
  media_dir="$MEDIA_DIR"
  echo "使用环境变量 MEDIA_DIR=$media_dir"
else
  echo ""
  echo "你的 STRM 文件放在哪个目录？（服务器上的真实路径）"
  echo "例：/volume1/media/tv 或 /mnt/nas/strm"
  read -r -p "目录路径: " media_dir
fi
if [ -z "$media_dir" ]; then
  echo "[错误] 目录不能为空"
  exit 1
fi

echo ""
echo "你的 STRM 目录：$media_dir"
echo "该目录会被只读挂载到容器内 /media"

# 3. 询问第二个目录（可选）
echo ""
read -r -p "还有其他 STRM 目录吗？直接回车跳过: " media_dir2

# 4. 生成 .env
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  {
    echo "# 缺集管家 v2.0 配置（由 install.sh 自动生成）"
    echo "MEDIA_DIR=$media_dir"
    echo "DATA_DIR=./data"
    echo "APP_PORT=8899"
  } > "$ENV_FILE"

  if [ -n "$media_dir2" ]; then
    echo "MEDIA_DIR2=$media_dir2" >> "$ENV_FILE"
    echo ""
    echo "提示：第二个目录需要取消 docker-compose.yml 中 MEDIA_DIR2 那行的注释"
  fi

  echo "已生成 .env 文件"
else
  echo ".env 已存在，保留现有配置"
fi

# 5. 启动
echo ""
echo "正在构建并启动（首次需下载镜像 + 编译前端，约 3-5 分钟）..."
docker compose up -d --build

# 6. 等待就绪
echo ""
echo -n "等待启动"
for i in $(seq 1 30); do
  sleep 2
  if curl -sf "http://127.0.0.1:${APP_PORT:-8899}/api/health" >/dev/null 2>&1; then
    echo ""
    echo "=============================================="
    echo "  安装完成！"
    echo ""
    echo "  浏览器打开： http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '你的服务器IP'):${APP_PORT:-8899}"
    echo ""
    echo "  首次打开会进入设置密码向导"
    echo "  然后去设置页填 MoviePilot 地址和 Token"
    echo "  添加 STRM 扫描源 → 开始扫描"
    echo "=============================================="
    exit 0
  fi
  echo -n "."
done

echo ""
echo "[提示] 容器已启动，健康检查可能需要更长时间"
echo "  查看日志： docker compose logs -f"
