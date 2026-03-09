# 多阶段构建策略：
# Stage 1: 云端编译前端 (Node.js) — 无需本地预编译
# Stage 2: 构建后端运行环境 (Python) 并将编译好的前端代码复制进去

# === Stage 1: 前端编译 ===
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# === Stage 2: Python 后端生产镜像 ===
FROM python:3.12-slim AS backend

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 从 Stage 1 复制编译好的前端产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 复制并安装后端依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目核心文件 (.dockerignore 会自动排除 frontend/node_modules, frontend/dist 等)
COPY . /app/

# 暴露端口 (Cloud Run 默认监听 PORT 环境变量)
EXPOSE 8080

# 启动命令
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
