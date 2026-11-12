FROM 1password/op:2.42.0@sha256:b0d7eebcb09bdc9d5862af91533e1851c968d4f969270c906f5da8c574f87e93 AS onepassword
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /opt/collector
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --all-extras --no-editable

FROM python:3.15.0-slim-bookworm@sha256:0e019bbdfb5d9874cb2389f1c2884b64aa2ac97c99960b5bc521cef978c0617d
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
