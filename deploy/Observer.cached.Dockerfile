# Optional original frontend cache. It must match config/framework.lock.json.
FROM jiuwen-ops-observer:frontend-cache
COPY lab /app/lab
COPY web/observe.html /opt/jiuwen-native-web/ops-observe.html
COPY scripts/start_native_observer.py scripts/check_native_observer.py /app/scripts/
CMD ["python","/app/scripts/start_native_observer.py"]
