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

# Mirrors de Debian configurables, por defecto los oficiales. Son dos porque el
# archivo principal y el de seguridad se sincronizan por separado: un mirror
# local puede tener uno y no el otro.
#
# Existen porque deb.debian.org y security.debian.org se degradan cada tanto
# (medido: 1 de cada 3 descargas con timeout) y eso hace fallar el build entero
ARG DEBIAN_MIRROR=deb.debian.org
ARG DEBIAN_SECURITY_MIRROR=deb.debian.org

RUN sed -i \
      -e "s|URIs: http://deb.debian.org/debian$|URIs: http://${DEBIAN_MIRROR}/debian|" \
      -e "s|URIs: http://deb.debian.org/debian-security$|URIs: http://${DEBIAN_SECURITY_MIRROR}/debian-security|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf 'Acquire::Retries "10";\n' > /etc/apt/apt.conf.d/99-retries \
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

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

# media tiene que existir en la imagen antes del chown: un volumen nombrado nuevo
# copia contenido y duenio del directorio de la imagen la primera vez que se
# monta. Si no existe, el volumen nace de root y el core, que corre como
# ixforge, no puede escribir los logos que se suben
RUN mkdir -p /app/media && chown -R ixforge:ixforge /app
USER ixforge

EXPOSE 8000
EXPOSE 8001

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["run"]
