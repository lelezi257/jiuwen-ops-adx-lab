ARG PYTHON_BASE=python:3.11-slim-bookworm
ARG DOCKER_CLI_IMAGE=docker:29.1.3-cli
FROM ${DOCKER_CLI_IMAGE} AS dockercli
FROM ${PYTHON_BASE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG UV_INDEX_URL=https://pypi.org/simple
ARG APT_MIRROR_SITE=
RUN if [ -n "$APT_MIRROR_SITE" ]; then sed -i "s|http://deb.debian.org|$APT_MIRROR_SITE|g" /etc/apt/sources.list.d/debian.sources; fi
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
COPY deploy /app/deploy
COPY scripts /app/scripts
COPY lab /app/lab
COPY contracts /app/contracts
COPY web /app/web
CMD ["python","-m","uvicorn","lab.control:app","--host","0.0.0.0","--port","8080"]
