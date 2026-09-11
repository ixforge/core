# Los assets (CSS de Tailwind y bundles de JS) se construyen en un stage aparte
# con la imagen oficial de node. Instalar nodejs y npm de Debian al lado de
# python:3.12-slim ya no funciona: npm depende de node-gyp -> libnode-dev ->
# libssl-dev, que exige un libssl3t64 mas viejo que el de la imagen base, y apt
# rechaza el downgrade. Ademas nodejs no hace falta en runtime
FROM node:22-slim AS assets

WORKDIR /build
COPY package.json package-lock.json tailwind.config.js ./
RUN npm ci

# tailwind escanea los templates para saber que clases conservar
COPY src/ixforge/ui/templates/ src/ixforge/ui/templates/
COPY src/ixforge/ui/static/ src/ixforge/ui/static/
RUN npm run build


FROM python:3.12-slim AS base

RUN printf 'Acquire::Retries "5";\n' > /etc/apt/apt.conf.d/99-retries \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
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

# los assets ya vienen construidos del stage de node
COPY --from=assets /build/src/ixforge/ui/static/ src/ixforge/ui/static/

RUN chown -R ixforge:ixforge /app
USER ixforge

EXPOSE 8000
EXPOSE 8001

ENTRYPOINT ["uv", "run", "ixforge"]
CMD ["run"]
