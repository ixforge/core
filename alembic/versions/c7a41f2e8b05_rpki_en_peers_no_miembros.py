"""RPKI en los peers que no son miembros

El upstream es de donde viene la mayoria de las rutas que el route server
redistribuye, y su bloque no validaba nada. Ahora etiqueta igual que un miembro
y, con reject_invalid, marca para descarte; el pipe hacia master pasa a usar
f_export_to_master para que la marca sirva de algo.

Solo toca las filas que siguen igual que como las dejo 9f2c7a1b4d3e: si un
operador edito su template, se respeta y se avisa.

Revision ID: c7a41f2e8b05
Revises: 9f2c7a1b4d3e
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7a41f2e8b05"
down_revision: str | None = "9f2c7a1b4d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ARCHIVO = "protocols/rs_peer.j2"

CONTENIDO_ANTERIOR = '# {{ peer.name | bird_str }} (AS{{ peer.peer_asn }}, {{ peer.peer_type }})\n{% if af == 4 %}\nipv4 table t_{{ peer.slug }};\n{% else %}\nipv6 table t_{{ peer.slug }};\n{% endif %}\n\nprotocol bgp pb_{{ peer.slug }} {\n    description "{{ peer.name | bird_str }}";\n    local as {{ peer.local_asn }};\n    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};\n{% if peer.passive %}\n    passive yes;\n{% endif %}\n\n{% if af == 4 %}\n    ipv4 {\n{% else %}\n    ipv6 {\n{% endif %}\n{% if peer.max_prefixes %}\n        import limit {{ peer.max_prefixes }} action restart;\n{% endif %}\n        import filter {\n{% if peer.mark_community %}\n            bgp_community.add( ({{ peer.mark_community | bird_community }}) );\n{% endif %}\n            accept;\n        };\n        export all;\n        table t_{{ peer.slug }};\n    };\n}\n\nprotocol pipe pp_{{ peer.slug }} {\n    description "Pipe for {{ peer.name | bird_str }}";\n{% if af == 4 %}\n    table master4;\n{% else %}\n    table master6;\n{% endif %}\n    peer table t_{{ peer.slug }};\n    import all;\n{% if peer.mark_community %}\n    export where !(bgp_community ~ [({{ peer.mark_community | bird_community }})]);\n{% else %}\n    export all;\n{% endif %}\n}\n'

CONTENIDO_NUEVO = '# {{ peer.name | bird_str }} (AS{{ peer.peer_asn }}, {{ peer.peer_type }})\n{% if af == 4 %}\nipv4 table t_{{ peer.slug }};\n{% else %}\nipv6 table t_{{ peer.slug }};\n{% endif %}\n\nprotocol bgp pb_{{ peer.slug }} {\n    description "{{ peer.name | bird_str }}";\n    local as {{ peer.local_asn }};\n    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};\n{% if peer.passive %}\n    passive yes;\n{% endif %}\n\n{% if af == 4 %}\n    ipv4 {\n{% else %}\n    ipv6 {\n{% endif %}\n{% if peer.max_prefixes %}\n        import limit {{ peer.max_prefixes }} action restart;\n{% endif %}\n        import filter {\n{% if peer.mark_community %}\n            bgp_community.add( ({{ peer.mark_community | bird_community }}) );\n{% endif %}\n{% if route_server.rpki_enabled %}\n            if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_VALID ) then {\n                bgp_large_community.add( IXP_LC_INFO_RPKI_VALID );\n            } else {\n                if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_INVALID ) then {\n                    bgp_large_community.add( IXP_LC_INFO_RPKI_INVALID );\n{% if route_server.rpki_policy == \'reject_invalid\' %}\n                    bgp_large_community.add( IXP_LC_FILTERED_RPKI_INVALID );\n{% endif %}\n                } else {\n                    bgp_large_community.add( IXP_LC_INFO_RPKI_UNKNOWN );\n                }\n            }\n{% else %}\n            bgp_large_community.add( IXP_LC_INFO_RPKI_NOT_CHECKED );\n{% endif %}\n            accept;\n        };\n        export all;\n        table t_{{ peer.slug }};\n    };\n}\n\nprotocol pipe pp_{{ peer.slug }} {\n    description "Pipe for {{ peer.name | bird_str }}";\n{% if af == 4 %}\n    table master4;\n{% else %}\n    table master6;\n{% endif %}\n    peer table t_{{ peer.slug }};\n    import filter f_export_to_master;\n{% if peer.mark_community %}\n    export where !(bgp_community ~ [({{ peer.mark_community | bird_community }})]);\n{% else %}\n    export all;\n{% endif %}\n}\n'


def upgrade() -> None:
    conn = op.get_bind()
    resultado = conn.execute(
        sa.text(
            "UPDATE route_server_templates SET content = :nuevo, updated_at = now() "
            "WHERE filename = :archivo AND content = :anterior"
        ),
        {"nuevo": CONTENIDO_NUEVO, "archivo": ARCHIVO, "anterior": CONTENIDO_ANTERIOR},
    )
    total = conn.execute(
        sa.text("SELECT count(*) FROM route_server_templates WHERE filename = :archivo"),
        {"archivo": ARCHIVO},
    ).scalar_one()
    sin_tocar = total - resultado.rowcount
    if sin_tocar:
        print(
            f"aviso: {sin_tocar} de {total} plantillas {ARCHIVO} estaban editadas "
            "y quedaron como estaban. Sin RPKI en los peers que no son miembros"
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE route_server_templates SET content = :anterior, updated_at = now() "
            "WHERE filename = :archivo AND content = :nuevo"
        ),
        {"nuevo": CONTENIDO_NUEVO, "archivo": ARCHIVO, "anterior": CONTENIDO_ANTERIOR},
    )
