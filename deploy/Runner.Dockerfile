ARG PYTHON_BASE=python:3.11-slim-bookworm
FROM ${PYTHON_BASE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_SYSTEM_PYTHON=1
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG UV_INDEX_URL=https://pypi.org/simple
ARG APT_MIRROR_SITE=
RUN if [ -n "$APT_MIRROR_SITE" ]; then sed -i "s|http://deb.debian.org|$APT_MIRROR_SITE|g" /etc/apt/sources.list.d/debian.sources; fi
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.9.5
COPY config/framework.lock.json /app/config/framework.lock.json
COPY scripts/fetch_framework.py /app/scripts/fetch_framework.py
RUN python scripts/fetch_framework.py
RUN uv pip install --no-cache -r vendor/requirements-framework.txt
RUN python -c 'import json,subprocess; subprocess.run(["uv","pip","install","--no-deps",*json.load(open("vendor/projects.json"))],check=True)'
RUN python -c 'import sysconfig; from pathlib import Path; (Path(sysconfig.get_paths()["purelib"])/"application_plugins").mkdir(exist_ok=True)'
COPY lab /app/lab
COPY scripts/qualify_jiuwen.py /app/scripts/qualify_jiuwen.py
RUN ln -s /app/vendor /vendor
CMD ["python","-m","uvicorn","lab.runner:app","--host","0.0.0.0","--port","8080"]
