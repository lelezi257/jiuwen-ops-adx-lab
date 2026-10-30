# Optional verified dependency cache. All application code is replaced below.
FROM jiuwen-ops-runner:framework-cache
COPY lab /app/lab
COPY scripts/qualify_jiuwen.py /app/scripts/qualify_jiuwen.py
COPY config/framework.lock.json /app/config/framework.lock.json
CMD ["python","-m","uvicorn","lab.execution_host:app","--host","0.0.0.0","--port","8080"]
