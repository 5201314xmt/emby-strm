# ============================================================
# 缺集管家 v2.0 —— Docker 多阶段构建
#
# 阶段 1：构建前端（Node.js → 静态文件）
# 阶段 2：Python 运行环境（包含静态文件）
#
# 用户只需: docker compose up -d
# ============================================================

# ========== 阶段 1：构建前端（仅在构建镜像时运行） ==========
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# 先复制 package.json 和 lockfile
COPY frontend/package.json frontend/package-lock.json ./
# 严格按 lockfile 安装（保证构建可复现）
RUN npm ci

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build

# ========== 阶段 2：Python 运行环境 ==========
FROM python:3.12-slim

# 时区
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

# 安装 tzdata
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码 + 创建数据目录
RUN mkdir -p /app/data
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic

# 复制前端构建产物
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# 对外端口
EXPOSE 8899

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8899", "--log-level", "info"]
