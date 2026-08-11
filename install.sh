#!/usr/bin/env bash
# ============================================================
# 缺集管家 - 一键安装脚本（Linux / 群晖 NAS 等）
# 用法：  bash install.sh
# 它会问你 strm 目录在哪，然后自动生成 .env 并启动
# ============================================================
set -e

echo "=============================================="
echo "  缺集管家 - 一键安装"
echo "=============================================="

# 1. 检查 docker 是否可用
if ! command -v docker >/dev/null 2>&1; then
  echo "[错误] 没找到 docker，请先安装 Docker："
  echo "  群晖：套件中心安装 Container Manager"
  echo "  其他 Linux：参考 https://docs.docker.com/engine/install/"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "[错误] docker compose 不可用，请升级 Docker 到新版（20.10+）"
  exit 1
fi

# 2. 询问 strm 目录
if [ -n "$MEDIA_DIR" ]; then
  media_dir="$MEDIA_DIR"
  echo "使用环境变量 MEDIA_DIR=$media_dir"
else
  echo ""
  echo "你的 strm 文件放在哪个目录？（服务器上的真实路径，如 /volume1/media/tv）"
  read -r -p "目录路径: " media_dir
fi
if [ -z "$media_dir" ]; then
  echo "[错误] 目录不能为空"
  exit 1
fi

# 3. 生成 .env（已有就跳过，不覆盖用户改过的东西）
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "正在生成 .env 文件..."
  {
    echo "# 缺集管家配置（由 install.sh 自动生成）"
    echo "MEDIA_DIR=$media_dir"
    echo "DATA_DIR=./data"
    echo "APP_PORT=8899"
  } > "$ENV_FILE"
  echo "已生成 $ENV_FILE"
else
  echo ""
  echo "$ENV_FILE 已存在，保留你的现有配置（不会覆盖）"
fi

# 4. 启动
echo ""
echo "正在启动缺集管家（首次会自动构建镜像，需要几分钟）..."
docker compose up -d --build

# 5. 等待健康检查通过
echo ""
echo -n "等待启动"
for i in $(seq 1 30); do
  sleep 2
  if curl -sf "http://127.0.0.1:${APP_PORT:-8899}/api/health" >/dev/null 2>&1; then
    echo ""
    echo "=============================================="
    echo "  安装完成！"
    echo "  打开浏览器访问：  http://你的服务器IP:${APP_PORT:-8899}"
    echo "  按网页提示完成设置即可（全程网页操作）"
    echo "=============================================="
    exit 0
  fi
  echo -n "."
done

echo ""
echo "[提示] 容器已启动但还没就绪，请稍后刷新网页；"
echo "  查看日志： docker compose logs -f"
exit 0
