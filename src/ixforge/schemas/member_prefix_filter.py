"""Schemas de filtros de prefijos por miembro y familia."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ixforge.enums import PrefixFilterSource


class MemberPrefixFilterWrite(BaseModel):
    """El af no va en el body: viene en la URL

    La validacion de que cada prefijo sea de la familia correcta vive en el
    servicio, que es donde el af se conoce
    """

    origin_asns: list[int] | None = Field(default=None)
    prefixes: list[str] | None = Field(default=None)
    as_set: str | None = Field(default=None, max_length=255)
    source: PrefixFilterSource = PrefixFilterSource.manual

    @field_validator("origin_asns")
    @classmethod
    def validate_origin_asns(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        for asn in v:
            if not (1 <= asn <= 4294967295):
                raise ValueError(f"ASN fuera de rango: {asn}")
        return v

    # La lista vacia se acepta y significa "no autorizar ningun prefijo". Se
    # renderea como allnet = [ ] y, como net ~ [] nunca matchea, marca todo como
    # filtrado por prefijo.
    #
    # Una version anterior la rechazaba, con el argumento de que por API casi
    # nunca es lo que se quiso. Es un caso de uso real: un colector de rutas que
    # recibe y no anuncia debe tener lista blanca vacia, no ausente. Para
    # desactivar el filtro se manda null, que es distinto y sigue funcionando


class MemberPrefixFilterRead(BaseModel):
    id: uuid.UUID
    ixp_id: uuid.UUID
    member_id: uuid.UUID
    af: int
    origin_asns: list[int] | None
    prefixes: list[str] | None
    as_set: str | None
    source: PrefixFilterSource
    last_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
