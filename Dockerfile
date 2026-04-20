# ============================================================
# 多阶段构建
# ============================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install -e .

# ============================================================
# 运行阶段
# ============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# 从 builder 复制已安装的包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8899

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8899/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8899"]
