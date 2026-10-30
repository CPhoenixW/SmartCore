FROM node:22-bookworm-slim

WORKDIR /runtime/dsh

ENV NODE_ENV=production \
    NODE_OPTIONS=--disable-warning=ExperimentalWarning \
    DSH_PATCH_FILE=/runtime/dsh/bridge/patch.yml \
    DSH_MCP_SERVER_FILE=/runtime/dsh/bridge/mcp-server.mjs \
    DSH_BIN=/runtime/dsh/node_modules/.bin/dsh \
    DSH_CWD=/runtime \
    DSH_HOME_ROOT=/data/dsh-home \
    DSH_SCOPE_ROOT=/data/scopes

ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision="${VCS_REF}"

COPY dsh/package.json dsh/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

COPY dsh/bridge ./bridge

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin smartcore \
    && mkdir -p /data/dsh-home /data/scopes \
    && chown -R smartcore:smartcore /runtime/dsh /data

USER smartcore

EXPOSE 18790
CMD ["node", "/runtime/dsh/bridge/server.mjs"]
