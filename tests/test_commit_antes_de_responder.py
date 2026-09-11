"""El commit tiene que ocurrir ANTES de mandar la respuesta.

Medido contra un deployment real: con el commit en el codigo posterior al yield
de la dependencia de sesion, crear un route server y pedirle una API key acto
seguido fallaba con 404 en 4 de cada 6 intentos, porque FastAPI ejecuta ese
codigo despues de entregar la respuesta. Y peor, la API devolvia 201 antes de
saber si el commit iba a funcionar.

Estos tests verifican la propiedad (el orden), no intentan ganarle a la
carrera: reproducirla en proceso depende del timing del event loop y del pool
de conexiones, y un test que a veces pasa no protege de nada.
"""

import pytest
from starlette.types import Message, Receive, Scope, Send

from ixforge.main import CommitBeforeResponse


class _SesionFalsa:
    def __init__(self, falla: bool = False) -> None:
        self.eventos: list[str] = []
        self.falla = falla

    async def commit(self) -> None:
        self.eventos.append("commit")
        if self.falla:
            raise RuntimeError("se cayo la base")

    async def rollback(self) -> None:
        self.eventos.append("rollback")


async def _correr(sesion: _SesionFalsa, estado: int = 201) -> tuple[list[str], list[Message]]:
    """Corre el middleware sobre una app que responde y devuelve el orden real"""
    enviados: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": estado, "headers": []})
        sesion.eventos.append("primer byte")
        await send({"type": "http.response.body", "body": b'{"id":"x"}'})

    async def send(message: Message) -> None:
        enviados.append(message)

    scope: Scope = {"type": "http", "path": "/api/v1/route-servers",
                    "state": {"db_session": sesion}}

    async def receive() -> Message:
        return {"type": "http.request"}

    await CommitBeforeResponse(app)(scope, receive, send)
    return sesion.eventos, enviados


async def test_el_commit_ocurre_antes_del_primer_byte():
    sesion = _SesionFalsa()

    eventos, enviados = await _correr(sesion)

    assert eventos == ["commit", "primer byte"], (
        f"orden real {eventos}: el commit tiene que ocurrir antes de que "
        "cualquier byte salga al cliente"
    )
    assert enviados[0]["status"] == 201


async def test_si_el_commit_falla_el_cliente_recibe_500_y_no_201():
    """Lo peor posible es confirmar un cambio que no se guardo"""
    sesion = _SesionFalsa(falla=True)

    eventos, enviados = await _correr(sesion)

    assert "rollback" in eventos
    assert enviados[0]["status"] == 500, (
        f"el cliente recibio {enviados[0]['status']} para un cambio que no se guardo"
    )
    cuerpo = b"".join(m.get("body", b"") for m in enviados if m["type"] == "http.response.body")
    assert b"INTERNAL_ERROR" in cuerpo
    assert b'"id"' not in cuerpo, "se filtro el cuerpo original de exito"


async def test_no_commitea_respuestas_de_error():
    """Un 422 o un 409 no deben commitear lo que haya quedado en la sesion"""
    sesion = _SesionFalsa()

    eventos, enviados = await _correr(sesion, estado=422)

    assert "commit" not in eventos
    assert enviados[0]["status"] == 422


@pytest.mark.parametrize("tipo", ["websocket", "lifespan"])
async def test_deja_pasar_lo_que_no_es_http(tipo: str):
    llamadas = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        llamadas.append(scope["type"])

    async def send(message: Message) -> None:
        pass

    async def receive() -> Message:
        return {"type": "x"}

    await CommitBeforeResponse(app)({"type": tipo}, receive, send)

    assert llamadas == [tipo]
