ARG PYTHON_VERSION=3.14.2
FROM python:${PYTHON_VERSION}-alpine AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

FROM base AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apk add --no-cache \
  build-base \
  pkgconf

WORKDIR /app

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project

COPY . ./
RUN uv sync --frozen

FROM base AS runtime

EXPOSE 80

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=build /app ./
