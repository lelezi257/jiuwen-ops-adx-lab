ARG PYTHON_BASE=python:3.11-slim-bookworm
FROM ${PYTHON_BASE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG UV_INDEX_URL=https://pypi.org/simple
ARG APT_MIRROR_SITE=
RUN if [ -n "$APT_MIRROR_SITE" ]; then sed -i "s|http://deb.debian.org|$APT_MIRROR_SITE|g" /etc/apt/sources.list.d/debian.sources; fi
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2 'psycopg[binary]==3.2.9' prometheus-client==0.22.1 httpx==0.28.1
ARG SOURCE_SHA=unknown
ENV SOURCE_SHA=$SOURCE_SHA
LABEL org.opencontainers.image.revision=$SOURCE_SHA
COPY apps/order_api /app
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8080"]
