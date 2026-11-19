FROM 1password/op:2.42.0@sha256:b0d7eebcb09bdc9d5862af91533e1851c968d4f969270c906f5da8c574f87e93 AS onepassword
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /opt/collector
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --all-extras --no-editable

FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
LABEL org.opencontainers.image.source="https://github.com/subimagesec/collectors" \
      org.opencontainers.image.title="1Password metadata collector" \
      org.opencontainers.image.description="Customer-operated 1Password metadata collection for Cartography"
COPY --from=onepassword /usr/local/bin/op /usr/local/bin/op
COPY --from=build /opt/collector/.venv /opt/collector/.venv
RUN groupadd --gid 10001 collector \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin collector \
    && install -d -o collector -g collector /data \
    && install -d -m 0755 /usr/share/licenses/onepassword-sdk
COPY --chmod=0644 third-party/onepassword-sdk-LICENSE /usr/share/licenses/onepassword-sdk/LICENSE
ENV PATH="/opt/collector/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OP_CONFIG_DIR=/tmp/op \
    OP_CACHE=false
USER 10001:10001
WORKDIR /data
ENTRYPOINT ["onepassword-collector"]
CMD []
