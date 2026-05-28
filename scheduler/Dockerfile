# Based on https://github.com/astral-sh/uv-docker-example
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:d9fb7d2b1c1922d191f1f77cb68b119c0a231f876f3affcce9bfac86e564c20a

RUN groupadd --system --gid 1000 nonroot \
 && useradd --system --gid 1000 --uid 1000 --create-home nonroot

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_TOOL_BIN_DIR=/usr/local/bin

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY pyproject.toml uv.lock /app/

COPY ./src/scheduler /app/scheduler

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT []

USER nonroot

CMD ["uv", "run", "python", "-m", "scheduler.main"]
