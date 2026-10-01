# Customer Profile Service (SVC-CPS) — Cloud Run container image
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    PORT=8080 \
    CPS_ENV=prod

WORKDIR /srv

COPY pyproject.toml requirements.txt ./
RUN uv pip install --no-cache -r requirements.txt

COPY app ./app
COPY openapi.yaml ./openapi.yaml

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin cps \
    && chown -R 10001:10001 /srv
USER 10001

EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers"]
