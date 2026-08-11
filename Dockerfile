# ============================================================
# 缺集管家 - Docker 镜像构建文件
# 使用精简版 Python 镜像，镜像体积小、安全
# 依赖版本已锁定（requirements.txt 用 ==），保证每次构建结果一致
# ============================================================

FROM python:3.12-slim

# 设置时区为北京时间（日志时间显示正确）
ENV TZ=Asia/Shanghai

# Python 输出不缓冲（日志实时可见）
ENV PYTHONUNBUFFERED=1

# 安装 tzdata 用于时区，然后清理缓存减小镜像体积
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 先复制依赖清单并安装（利用 Docker 缓存，以后改代码不用重新装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码 + 运维脚本
COPY app ./app
COPY scripts ./scripts

# 对外暴露的端口（网页访问端口）
EXPOSE 8899

# 启动命令：启动 Web 服务，0.0.0.0 表示允许外部访问
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8899"]
