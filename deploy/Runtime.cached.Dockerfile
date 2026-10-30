# Optional local build cache only; deploy/Dockerfile remains the clean build.
FROM jiuwen-ops-runtime:framework-cache
COPY deploy /app/deploy
COPY scripts /app/scripts
COPY lab /app/lab
COPY contracts /app/contracts
COPY config /app/config
COPY web /app/web
