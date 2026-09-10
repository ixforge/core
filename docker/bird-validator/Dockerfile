# Imagen minima para validar configs BIRD con bird -p en los tests
#
# La version de BIRD tiene que coincidir con la que corre en los route servers
# del deployment: la sintaxis cambia entre 2.x menores y un config que pasa aca
# no garantiza nada sobre una version distinta
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends bird2 \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["bird"]
