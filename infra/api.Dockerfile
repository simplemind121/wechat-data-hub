FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv==0.9.17 && \
    uv sync --frozen --no-dev --no-editable && \
    uv cache clean && \
    useradd --uid 10001 --no-create-home hub && \
    mkdir -p /var/lib/wechat-hub && chown 10001:10001 /var/lib/wechat-hub && \
    chmod 700 /var/lib/wechat-hub
ENV PATH="/app/.venv/bin:$PATH" DATA_ROOT=/var/lib/wechat-hub
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "wdh_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
