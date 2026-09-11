FROM 1password/op:2.32.1@sha256:4ac3658f1e91a27ec9503f2134d4b2b77769b36d35b2e370ac89b5976573a17b AS onepassword
FROM ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 AS uv

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /opt/collector
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --all-extras --no-editable

FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
LABEL org.opencontainers.image.source="https://github.com/subimagesec/collectors" \
      org.opencontainers.image.title="SubImage Collectors" \
      org.opencontainers.image.description="Customer-operated metadata collectors for Cartography"
COPY --from=onepassword /usr/local/bin/op /usr/local/bin/op
COPY --from=build /opt/collector/.venv /opt/collector/.venv
RUN groupadd --gid 10001 collector \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin collector \
    && install -d -o collector -g collector /data
ENV PATH="/opt/collector/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OP_CONFIG_DIR=/tmp/op \
    OP_CACHE=false
USER 10001:10001
WORKDIR /data
ENTRYPOINT ["subimage-collector"]
CMD ["--help"]
