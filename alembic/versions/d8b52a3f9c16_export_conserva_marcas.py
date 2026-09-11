"""El export conserva las marcas de upstream

Borrar todo (rsasn, *) se lleva puesta la marca que el route server le pone a
las rutas del upstream, y esa marca existe justamente para que el miembro la
vea. En PatagoniaIX, Apoapsis la usa para no reenviarle transito a su cache de
Microsoft: 123.441 rutas dependian de ella.

Ahora el borrado se expresa como el complemento en rangos de las marcas
configuradas, asi que sigue limpiando control de anuncio y tipo de miembro pero
deja pasar la marca.

Solo toca las filas que siguen igual que como las dejo 9f2c7a1b4d3e.

Revision ID: d8b52a3f9c16
Revises: c7a41f2e8b05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8b52a3f9c16"
down_revision: str | None = "c7a41f2e8b05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ARCHIVO = "protocols/bgp_peer.j2"

CONTENIDO_ANTERIOR = '# {{ peer.member_name | bird_str }} (AS{{ peer.peer_asn }}) en {{ peer.peer_ip }}\n{% if af == 4 %}\nipv4 table t_{{ peer.slug }};\n{% else %}\nipv6 table t_{{ peer.slug }};\n{% endif %}\n\nfilter f_import_{{ peer.slug }}\n{% if peer.prefixes is not none %}\nprefix set allnet;\n{% endif %}\nip set allips;\nint set allas;\n{\n{% if af == 4 %}\n    if ( net ~ [ 0.0.0.0/0{25,32} ] ) then {\n{% else %}\n    if ( net ~ [ ::/0{49,128} ] ) then {\n{% endif %}\n        bgp_large_community.add( IXP_LC_FILTERED_PREFIX_LEN_TOO_LONG );\n        accept;\n    }\n\n{% if af == 4 %}\n    if !(avoid_martians4()) then {\n{% else %}\n    if !(avoid_martians6()) then {\n{% endif %}\n        bgp_large_community.add( IXP_LC_FILTERED_BOGON );\n        accept;\n    }\n\n    if( bgp_path.len < 1 ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_SHORT );\n        accept;\n    }\n\n    if (bgp_path.first != {{ peer.peer_asn }} ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_FIRST_AS_NOT_PEER_AS );\n        accept;\n    }\n\n    allips = [ {{ peer.all_peer_ips | join(\', \') }} ];\n\n    if !( from = bgp_next_hop ) then {\n        if( bgp_next_hop ~ allips ) then {\n            bgp_large_community.add( IXP_LC_INFO_SAME_AS_NEXT_HOP );\n        } else {\n            bgp_large_community.add( IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP );\n            accept;\n        }\n    }\n\n    if filter_has_transit_path() then accept;\n\n    if( bgp_path.len > 64 ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_LONG );\n        accept;\n    }\n\n    allas = [ {{ peer.origin_asns | join(\', \') }} ];\n\n    if !(bgp_path.last_nonaggregated ~ allas) then {\n        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_ORIGIN_AS_FILTERED );\n        accept;\n    }\n\n{% if route_server.rpki_enabled %}\n    if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_VALID ) then {\n        bgp_large_community.add( IXP_LC_INFO_RPKI_VALID );\n    } else {\n        if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_INVALID ) then {\n            bgp_large_community.add( IXP_LC_INFO_RPKI_INVALID );\n{% if route_server.rpki_policy == \'reject_invalid\' %}\n            bgp_large_community.add( IXP_LC_FILTERED_RPKI_INVALID );\n{% endif %}\n        } else {\n            bgp_large_community.add( IXP_LC_INFO_RPKI_UNKNOWN );\n        }\n    }\n{% else %}\n    bgp_large_community.add( IXP_LC_INFO_RPKI_NOT_CHECKED );\n{% endif %}\n\n{% if peer.prefixes is not none %}\n    allnet = [ {{ peer.prefixes | join(\', \') }} ];\n\n    if ! (net ~ allnet) then {\n        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED );\n        bgp_large_community.add( IXP_LC_INFO_IRRDB_FILTERED_STRICT );\n        accept;\n    } else {\n        bgp_large_community.add( IXP_LC_INFO_IRRDB_VALID );\n    }\n{% else %}\n    bgp_large_community.add( IXP_LC_INFO_IRRDB_NOT_CHECKED );\n{% endif %}\n\n    honor_graceful_shutdown();\n\n{% if peer.member_type_community %}\n{% if route_server.asn <= 65535 %}\n    bgp_community.add( (routeserverasn, {{ peer.member_type_community }}) );\n{% else %}\n    # el ASN del IXP no entra en una community estandar (16 bits), se usa la\n    # forma large equivalente\n    bgp_large_community.add( (routeserverasn, 1002, {{ peer.member_type_community }}) );\n{% endif %}\n{% endif %}\n\n    accept;\n}\n\n# el export strippea nuestras propias communities de filtrado y looking glass.\n# Las dos formas: dejar pasar las estandar (routeserverasn, *) filtra menos de\n# lo que el operador cree, porque las de control de anuncio y las de marca de\n# upstream llegarian al miembro\nfilter f_export_{{ peer.slug }}\n{\n    bgp_large_community.delete( [( routeserverasn, *, * )] );\n{% if route_server.asn <= 65535 %}\n    bgp_community.delete( [( routeserverasn, * )] );\n{% endif %}\n    accept;\n}\n\nprotocol bgp pb_{{ peer.slug }} from tb_rsclient_v{{ af }} {\n    description "{{ peer.member_name | bird_str }}";\n    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};\n\n{% if af == 4 %}\n    ipv4 {\n{% else %}\n    ipv6 {\n{% endif %}\n{% if peer.max_prefixes %}\n        import limit {{ peer.max_prefixes }} action restart;\n{% endif %}\n        import filter f_import_{{ peer.slug }};\n        table t_{{ peer.slug }};\n        export filter f_export_{{ peer.slug }};\n    };\n}\n\nprotocol pipe pp_{{ peer.slug }} {\n    description "Pipe for {{ peer.member_name | bird_str }}";\n{% if af == 4 %}\n    table master4;\n{% else %}\n    table master6;\n{% endif %}\n    peer table t_{{ peer.slug }};\n    import filter f_export_to_master;\n    export where ixp_community_filter({{ peer.peer_asn }});\n}\n'

CONTENIDO_NUEVO = '# {{ peer.member_name | bird_str }} (AS{{ peer.peer_asn }}) en {{ peer.peer_ip }}\n{% if af == 4 %}\nipv4 table t_{{ peer.slug }};\n{% else %}\nipv6 table t_{{ peer.slug }};\n{% endif %}\n\nfilter f_import_{{ peer.slug }}\n{% if peer.prefixes is not none %}\nprefix set allnet;\n{% endif %}\nip set allips;\nint set allas;\n{\n{% if af == 4 %}\n    if ( net ~ [ 0.0.0.0/0{25,32} ] ) then {\n{% else %}\n    if ( net ~ [ ::/0{49,128} ] ) then {\n{% endif %}\n        bgp_large_community.add( IXP_LC_FILTERED_PREFIX_LEN_TOO_LONG );\n        accept;\n    }\n\n{% if af == 4 %}\n    if !(avoid_martians4()) then {\n{% else %}\n    if !(avoid_martians6()) then {\n{% endif %}\n        bgp_large_community.add( IXP_LC_FILTERED_BOGON );\n        accept;\n    }\n\n    if( bgp_path.len < 1 ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_SHORT );\n        accept;\n    }\n\n    if (bgp_path.first != {{ peer.peer_asn }} ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_FIRST_AS_NOT_PEER_AS );\n        accept;\n    }\n\n    allips = [ {{ peer.all_peer_ips | join(\', \') }} ];\n\n    if !( from = bgp_next_hop ) then {\n        if( bgp_next_hop ~ allips ) then {\n            bgp_large_community.add( IXP_LC_INFO_SAME_AS_NEXT_HOP );\n        } else {\n            bgp_large_community.add( IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP );\n            accept;\n        }\n    }\n\n    if filter_has_transit_path() then accept;\n\n    if( bgp_path.len > 64 ) then {\n        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_LONG );\n        accept;\n    }\n\n    allas = [ {{ peer.origin_asns | join(\', \') }} ];\n\n    if !(bgp_path.last_nonaggregated ~ allas) then {\n        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_ORIGIN_AS_FILTERED );\n        accept;\n    }\n\n{% if route_server.rpki_enabled %}\n    if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_VALID ) then {\n        bgp_large_community.add( IXP_LC_INFO_RPKI_VALID );\n    } else {\n        if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_INVALID ) then {\n            bgp_large_community.add( IXP_LC_INFO_RPKI_INVALID );\n{% if route_server.rpki_policy == \'reject_invalid\' %}\n            bgp_large_community.add( IXP_LC_FILTERED_RPKI_INVALID );\n{% endif %}\n        } else {\n            bgp_large_community.add( IXP_LC_INFO_RPKI_UNKNOWN );\n        }\n    }\n{% else %}\n    bgp_large_community.add( IXP_LC_INFO_RPKI_NOT_CHECKED );\n{% endif %}\n\n{% if peer.prefixes is not none %}\n    allnet = [ {{ peer.prefixes | join(\', \') }} ];\n\n    if ! (net ~ allnet) then {\n        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED );\n        bgp_large_community.add( IXP_LC_INFO_IRRDB_FILTERED_STRICT );\n        accept;\n    } else {\n        bgp_large_community.add( IXP_LC_INFO_IRRDB_VALID );\n    }\n{% else %}\n    bgp_large_community.add( IXP_LC_INFO_IRRDB_NOT_CHECKED );\n{% endif %}\n\n    honor_graceful_shutdown();\n\n{% if peer.member_type_community %}\n{% if route_server.asn <= 65535 %}\n    bgp_community.add( (routeserverasn, {{ peer.member_type_community }}) );\n{% else %}\n    # el ASN del IXP no entra en una community estandar (16 bits), se usa la\n    # forma large equivalente\n    bgp_large_community.add( (routeserverasn, 1002, {{ peer.member_type_community }}) );\n{% endif %}\n{% endif %}\n\n    accept;\n}\n\n# el export strippea nuestras propias communities de filtrado y looking glass.\n# Las dos formas: dejar pasar las estandar (routeserverasn, *) filtra menos de\n# lo que el operador cree, porque las de control de anuncio y las de marca de\n# upstream llegarian al miembro\nfilter f_export_{{ peer.slug }}\n{\n    bgp_large_community.delete( [( routeserverasn, *, * )] );\n{% if route_server.asn <= 65535 %}\n{% set borrado = route_server.communities_conservadas | rangos_a_borrar %}\n{% if borrado %}\n    bgp_community.delete( [{{ borrado }}] );\n{% endif %}\n{% endif %}\n    accept;\n}\n\nprotocol bgp pb_{{ peer.slug }} from tb_rsclient_v{{ af }} {\n    description "{{ peer.member_name | bird_str }}";\n    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};\n\n{% if af == 4 %}\n    ipv4 {\n{% else %}\n    ipv6 {\n{% endif %}\n{% if peer.max_prefixes %}\n        import limit {{ peer.max_prefixes }} action restart;\n{% endif %}\n        import filter f_import_{{ peer.slug }};\n        table t_{{ peer.slug }};\n        export filter f_export_{{ peer.slug }};\n    };\n}\n\nprotocol pipe pp_{{ peer.slug }} {\n    description "Pipe for {{ peer.member_name | bird_str }}";\n{% if af == 4 %}\n    table master4;\n{% else %}\n    table master6;\n{% endif %}\n    peer table t_{{ peer.slug }};\n    import filter f_export_to_master;\n    export where ixp_community_filter({{ peer.peer_asn }});\n}\n'


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
            "y quedaron como estaban. El export les sigue borrando la marca de upstream"
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
