ARG PYTHON_VERSION=3.14.2
FROM python:${PYTHON_VERSION}-alpine AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

FROM base AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apk add --no-cache \
  build-base \
  libffi-dev \
  mariadb-connector-c-dev \
  pkgconf

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project

COPY . ./
RUN uv sync --frozen

FROM build AS docs

RUN uv sync --frozen --no-install-project --extra=docs --extra=test
RUN uv run sphinx-build -W -d build/doctrees docs build/html

FROM base AS runtime

EXPOSE 80

ENV PATH="/app/.venv/bin:$PATH"

RUN apk add --no-cache \
  mariadb-connector-c \
  nftables \
  py3-nftables

WORKDIR /app

COPY --from=build /app ./
COPY --from=docs /app/build/html ./docs/html
