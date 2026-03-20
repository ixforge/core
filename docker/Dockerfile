FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 ixforge && \
    useradd --uid 1000 --gid ixforge --create-home ixforge

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
RUN mkdir -p src/ixforge && touch src/ixforge/__init__.py
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

COPY package.json tailwind.config.js ./
COPY src/ixforge/ui/static/css/input.css src/ixforge/ui/static/css/input.css
RUN npm install && npm run build && rm -rf node_modules

RUN chown -R ixforge:ixforge /app
USER ixforge

EXPOSE 8000
EXPOSE 8001

ENTRYPOINT ["uv", "run", "ixforge"]
CMD ["run"]
