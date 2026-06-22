# apk-site multi-stage image (Wave F / T-B04)
# python:3.11-slim, non-root, env-driven portal mode via APP_PORTAL_MODE

FROM python:3.11-slim AS builder

WORKDIR /build
COPY portals/common/core/requirements.txt portals/common/core/requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app/portals/common/core

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY portals/ /app/portals/

RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_PORTAL_MODE=admin \
    USE_SQLITE=true

EXPOSE 5003

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5003/health', timeout=3)"

CMD ["python", "-m", "waitress", "--listen=0.0.0.0:5003", "app_new:app"]
