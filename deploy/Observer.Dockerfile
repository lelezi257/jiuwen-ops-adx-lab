ARG RUNNER_IMAGE=jiuwen-ops-runner:local
ARG NODE_BASE=node:22-bookworm-slim
FROM ${RUNNER_IMAGE} AS framework
FROM ${NODE_BASE} AS ui
COPY --from=framework /app/vendor/swarm /source
WORKDIR /source/jiuwenswarm/channels/web/frontend
RUN npm ci --no-audit --no-fund && npm run build
FROM ${RUNNER_IMAGE}
COPY --from=ui /source/jiuwenswarm/channels/web/frontend/dist /opt/jiuwen-native-web
COPY web/observe.html /opt/jiuwen-native-web/ops-observe.html
COPY lab/native_observer.py /app/lab/native_observer.py
COPY scripts/start_native_observer.py scripts/check_native_observer.py /app/scripts/
CMD ["python","/app/scripts/start_native_observer.py"]
