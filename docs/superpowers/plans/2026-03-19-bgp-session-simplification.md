# BGP Session Simplification + UI Creation

> **Estado: IMPLEMENTADO (documento historico).** Las columnas redundantes
> (`peer_ip`, `peer_asn`, `import_limit`, `export_limit`) fueron removidas de
> `bgp_sessions` (migracion `c4b3520127d7`) y los formularios UI existen. Se
> conserva como registro del cambio.

**Goal:** Remove redundant columns (peer_ip, peer_asn, import_limit, export_limit) from bgp_sessions table, resolve them via joins, and add UI forms for creating BGP sessions.

**Architecture:** peer_ip is resolved from IPAssignment (matched by trunk_vlan_id + af via the pool's af). peer_asn is resolved from Member via trunk_vlan → trunk → member. The agent status endpoint joins to resolve peer_ip for matching. BGPSessionRead becomes a manually constructed dict instead of from_attributes since the fields are computed. Two UI entry points: standalone form at /admin/bgp-sessions/new and inline form in route server detail.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Jinja2, Alpine.js, HTMX

---

### Task 1: Alembic migration — drop columns

**Files:**
- Create: `alembic/versions/XXXX_drop_bgp_session_redundant_columns.py`

- [ ] **Step 1: Generate migration**

```bash
uv run alembic revision --autogenerate -m "Drop peer_ip, peer_asn, import_limit, export_limit from bgp_sessions"
```

Then edit the migration to be explicit:

```python
def upgrade() -> None:
    op.drop_column("bgp_sessions", "peer_ip")
    op.drop_column("bgp_sessions", "peer_asn")
    op.drop_column("bgp_sessions", "import_limit")
    op.drop_column("bgp_sessions", "export_limit")


def downgrade() -> None:
    op.add_column("bgp_sessions", sa.Column("peer_ip", postgresql.INET(), nullable=True))
    op.add_column("bgp_sessions", sa.Column("peer_asn", sa.Integer(), nullable=True))
    op.add_column("bgp_sessions", sa.Column("import_limit", sa.Integer(), nullable=True))
    op.add_column("bgp_sessions", sa.Column("export_limit", sa.Integer(), nullable=True))
```

- [ ] **Step 2: Run migration on testing DB**

```bash
docker compose -f docker/docker-compose.testing.yml up -d
TEST_DATABASE_URL=postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test uv run alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add alembic/
git commit -m "migration: drop peer_ip, peer_asn, import_limit, export_limit from bgp_sessions"
```

---

### Task 2: Update model — remove columns

**Files:**
- Modify: `src/ixforge/models/bgp_session.py`

- [ ] **Step 1: Remove columns and constraints from model**

Remove from `BGPSession`:
- `peer_ip` mapped_column
- `peer_asn` mapped_column
- `import_limit` mapped_column
- `export_limit` mapped_column
- `CheckConstraint("peer_asn > 0", ...)`

Keep: `id`, `ixp_id`, `route_server_id`, `trunk_vlan_id`, `admin_state`, `oper_state`, `af`, `max_prefixes`, `created_at`, `updated_at`.

The UniqueConstraint `(route_server_id, trunk_vlan_id, af)` stays as-is.

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/models/bgp_session.py
git commit -m "model: remove peer_ip, peer_asn, import_limit, export_limit from BGPSession"
```

---

### Task 3: Update schemas

**Files:**
- Modify: `src/ixforge/schemas/bgp_session.py`

- [ ] **Step 1: Simplify BGPSessionCreate**

Remove: `peer_ip`, `peer_asn`, `import_limit`, `export_limit`, and the `_validate_peer_ip_matches_af` validator.

Result:
```python
class BGPSessionCreate(BaseModel):
    route_server_id: uuid.UUID
    trunk_vlan_id: uuid.UUID
    af: Literal[4, 6]
    max_prefixes: int | None = Field(default=None, gt=0)
```

- [ ] **Step 2: Update BGPSessionRead**

Remove `from_attributes` config since peer_ip/peer_asn will be manually constructed. Remove `import_limit` and `export_limit`.

```python
class BGPSessionRead(BaseModel):
    id: uuid.UUID
    route_server_id: uuid.UUID
    trunk_vlan_id: uuid.UUID
    peer_ip: str
    peer_asn: int
    admin_state: BGPAdminState
    oper_state: BGPOperState
    af: Literal[4, 6]
    max_prefixes: int | None
    created_at: datetime
    updated_at: datetime
```

Note: `peer_ip` and `peer_asn` stay in the Read schema — they are computed, not stored.

- [ ] **Step 3: Commit**

```bash
git add src/ixforge/schemas/bgp_session.py
git commit -m "schemas: simplify BGPSessionCreate, remove redundant fields from Read"
```

---

### Task 4: Update service — resolve peer_ip/peer_asn via joins

**Files:**
- Modify: `src/ixforge/services/bgp_sessions.py`

- [ ] **Step 1: Add helper to resolve peer_ip and peer_asn**

```python
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.member import Member


async def _resolve_peer_info(
    session: AsyncSession,
    trunk_vlan_id: uuid.UUID,
    af: int,
) -> tuple[str, int]:
    """Resolve peer_ip and peer_asn from trunk_vlan relationships.

    peer_ip: IPAssignment.address where pool.af matches the session af
    peer_asn: Member.asn via trunk_vlan → trunk → member
    """
    # Resolve peer_ip
    stmt_ip = (
        select(IPAssignment.address)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(
            IPAssignment.trunk_vlan_id == trunk_vlan_id,
            IPPool.af == af,
        )
        .limit(1)
    )
    peer_ip = await session.scalar(stmt_ip)
    if peer_ip is None:
        raise ValidationError(
            f"No IPv{af} address assigned to this trunk VLAN. "
            "Assign an IP before creating a BGP session"
        )

    # Resolve peer_asn
    stmt_asn = (
        select(Member.asn)
        .join(Trunk, Member.id == Trunk.member_id)
        .join(TrunkVLAN, Trunk.id == TrunkVLAN.trunk_id)
        .where(TrunkVLAN.id == trunk_vlan_id)
    )
    peer_asn = await session.scalar(stmt_asn)
    if peer_asn is None:
        raise ValidationError("Could not resolve member ASN for this trunk VLAN")

    return str(peer_ip), peer_asn
```

- [ ] **Step 2: Update create() to not set peer_ip/peer_asn/import_limit/export_limit**

```python
async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: BGPSessionCreate,
) -> BGPSession:
    rs = await session.get(RouteServer, data.route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer")

    trunk_vlan = await session.get(TrunkVLAN, data.trunk_vlan_id)
    if trunk_vlan is None or trunk_vlan.ixp_id != ixp_id:
        raise NotFoundError("TrunkVLAN")

    trunk = await session.get(Trunk, trunk_vlan.trunk_id)
    if trunk is None or trunk.state != TrunkState.active:
        raise ValidationError("Trunk must be active to create a BGP session")

    # Validate that an IP exists for this af
    await _resolve_peer_info(session, data.trunk_vlan_id, data.af)

    bgp_session = BGPSession(
        ixp_id=ixp_id,
        route_server_id=data.route_server_id,
        trunk_vlan_id=data.trunk_vlan_id,
        af=data.af,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.unknown,
        max_prefixes=data.max_prefixes,
    )
    session.add(bgp_session)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(
            "BGP session already exists for this route server, trunk VLAN, and address family"
        ) from None

    await session.refresh(bgp_session)
    return bgp_session
```

- [ ] **Step 3: Add helper to build BGPSessionRead from model**

Since BGPSessionRead can no longer use `from_attributes` (peer_ip/peer_asn are not on the model), add a helper:

```python
async def _to_read(session: AsyncSession, bgp: BGPSession) -> dict:
    """Build BGPSessionRead dict with computed peer_ip and peer_asn."""
    peer_ip, peer_asn = await _resolve_peer_info(session, bgp.trunk_vlan_id, bgp.af)
    return {
        "id": bgp.id,
        "route_server_id": bgp.route_server_id,
        "trunk_vlan_id": bgp.trunk_vlan_id,
        "peer_ip": peer_ip,
        "peer_asn": peer_asn,
        "admin_state": bgp.admin_state,
        "oper_state": bgp.oper_state,
        "af": bgp.af,
        "max_prefixes": bgp.max_prefixes,
        "created_at": bgp.created_at,
        "updated_at": bgp.updated_at,
    }
```

- [ ] **Step 4: Update list_sessions and list_sessions_for_member**

These use `paginate()` with `schema=BGPSessionRead` and `from_attributes`. Since peer_ip/peer_asn are computed, the pagination needs to return raw models and then enrich them. Change these to return enriched dicts:

```python
async def list_sessions(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    stmt = select(BGPSession).where(
        BGPSession.route_server_id == route_server_id,
        BGPSession.ixp_id == ixp_id,
    )
    page = await paginate(
        session, stmt, params,
        sort_column=BGPSession.created_at,
        id_column=BGPSession.id,
        schema=None,  # Raw models
    )
    items = [await _to_read(session, item) for item in page.items]
    return CursorPage(items=[BGPSessionRead(**i) for i in items], next_cursor=page.next_cursor)
```

Note: Check if `paginate()` supports `schema=None`. If not, the function needs to accept raw model output. Inspect `services/base.py:paginate` to see how it works and adapt accordingly.

- [ ] **Step 5: Commit**

```bash
git add src/ixforge/services/bgp_sessions.py
git commit -m "service: resolve peer_ip/peer_asn from relationships instead of stored columns"
```

---

### Task 5: Update API endpoints

**Files:**
- Modify: `src/ixforge/api/v1/bgp_sessions.py`

- [ ] **Step 1: Update create endpoint return**

The create endpoint currently returns `BGPSession` model directly with `response_model=BGPSessionRead`. Since `from_attributes` won't work anymore, return the dict from `_to_read`:

```python
@bgp_sessions_router.post("", response_model=BGPSessionRead, status_code=201)
async def create_bgp_session(
    body: BGPSessionCreate,
    db: DBSession,
    ixp_id: IXPId,
    _admin: AdminUser,
) -> dict:
    bgp = await bgp_svc.create(db, ixp_id, body)
    return await bgp_svc._to_read(db, bgp)
```

- [ ] **Step 2: Update get endpoint**

```python
@bgp_sessions_router.get("/{session_id}", response_model=BGPSessionRead)
async def get_bgp_session(
    session_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    user: CurrentUser,
) -> dict:
    bgp_session = await bgp_svc.get(db, ixp_id, session_id)
    # member access check stays the same
    if user.role == UserRole.member:
        ...
    return await bgp_svc._to_read(db, bgp_session)
```

- [ ] **Step 3: Update patch (admin state) endpoint**

```python
async def update_bgp_session(...) -> dict:
    bgp = await bgp_svc.update_admin_state(db, ixp_id, session_id, body.admin_state.value)
    return await bgp_svc._to_read(db, bgp)
```

- [ ] **Step 4: Commit**

```bash
git add src/ixforge/api/v1/bgp_sessions.py
git commit -m "api: return computed peer_ip/peer_asn in BGP session responses"
```

---

### Task 6: Update agent status endpoint

**Files:**
- Modify: `src/ixforge/api/v1/agent.py`

- [ ] **Step 1: Update report_agent_status to resolve peer_ip via join**

The agent reports by `(peer_ip, af)`. Now peer_ip is not on the model, so we need to join:

```python
# Load all BGP sessions for this RS with their peer IPs resolved
stmt = (
    select(BGPSession, IPAssignment.address)
    .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
    .join(IPAssignment, IPAssignment.trunk_vlan_id == TrunkVLAN.id)
    .join(IPPool, IPAssignment.pool_id == IPPool.id)
    .where(
        BGPSession.route_server_id == route_server_id,
        IPPool.af == BGPSession.af,
    )
)
result = await db.execute(stmt)
sessions_by_peer: dict[tuple[str, int], BGPSession] = {
    (str(addr), s.af): s for s, addr in result.all()
}
```

- [ ] **Step 2: Update event data to resolve peer_ip/peer_asn**

The events currently reference `session.peer_ip` and `session.peer_asn`. Replace with the resolved values:

```python
# In the loop, peer_ip comes from the dict key
for report in body.sessions:
    bgp = sessions_by_peer.get((report.peer_ip, report.af))
    if bgp is None:
        not_found += 1
        continue
    ...
    # In event data, use report.peer_ip (already the resolved value from dict key)
    data={
        "peer_ip": report.peer_ip,
        "peer_asn": peer_asn,  # resolve from member via join or cache
        ...
    }
```

For peer_asn in events, pre-load a mapping of trunk_vlan_id → member.asn:

```python
# Pre-load member ASNs
stmt_asn = (
    select(TrunkVLAN.id, Member.asn)
    .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
    .join(Member, Trunk.member_id == Member.id)
    .where(TrunkVLAN.id.in_(
        select(BGPSession.trunk_vlan_id)
        .where(BGPSession.route_server_id == route_server_id)
    ))
)
asn_result = await db.execute(stmt_asn)
asn_by_tv: dict[uuid.UUID, int] = {tv_id: asn for tv_id, asn in asn_result.all()}
```

- [ ] **Step 3: Commit**

```bash
git add src/ixforge/api/v1/agent.py
git commit -m "agent: resolve peer_ip via join for BGP status matching"
```

---

### Task 7: Update config generation

**Files:**
- Modify: `src/ixforge/services/config_generation.py`

- [ ] **Step 1: Update _build_peers to resolve peer_ip/peer_asn via joins**

Currently reads `bgp_session.peer_ip` and `bgp_session.peer_asn`. Change the query to join IPAssignment and use Member.asn:

```python
async def _build_peers(
    session: AsyncSession,
    route_server_id: uuid.UUID,
    af: int,
) -> list[PeerContext]:
    stmt = (
        select(BGPSession, Member, IPAssignment.address)
        .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(Member, Trunk.member_id == Member.id)
        .join(IPAssignment, IPAssignment.trunk_vlan_id == TrunkVLAN.id)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(
            BGPSession.route_server_id == route_server_id,
            BGPSession.af == af,
            BGPSession.admin_state == BGPAdminState.up,
            Trunk.state == TrunkState.active,
            Member.state == MemberState.active,
            IPPool.af == af,
        )
        .order_by(Member.asn, IPAssignment.address)
    )
    result = await session.execute(stmt)

    seen_names: set[str] = set()
    peers: list[PeerContext] = []
    for bgp_session, member, peer_ip in result.all():
        peer_ip_str = str(peer_ip)
        protocol_name = _sanitize_protocol_name(member.short_name, peer_ip_str, af)
        # collision handling stays the same
        ...
        peers.append(PeerContext(
            protocol_name=protocol_name,
            member_name=member.name,
            peer_ip=peer_ip_str,
            peer_asn=member.asn,
            max_prefixes=bgp_session.max_prefixes,
        ))
    return peers
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/services/config_generation.py
git commit -m "config: resolve peer_ip/peer_asn from relationships in BIRD config generation"
```

---

### Task 8: Update trunks service — release IP check

**Files:**
- Modify: `src/ixforge/services/trunks.py`

- [ ] **Step 1: Update IP release validation**

Currently checks `BGPSession.peer_ip == assignment.address`. Since peer_ip is no longer stored, check if any BGP session references this trunk_vlan_id with the matching AF:

```python
# In release_ip function, replace peer_ip check:
ip_pool = await session.get(IPPool, assignment.pool_id)
has_bgp = await session.scalar(
    select(BGPSession.id).where(
        BGPSession.trunk_vlan_id == assignment.trunk_vlan_id,
        BGPSession.af == ip_pool.af,
    ).limit(1)
)
if has_bgp is not None:
    raise ConflictError(
        f"Cannot release IP {assignment.address}: has an active BGP session. "
        "Delete the BGP session first."
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/services/trunks.py
git commit -m "trunks: update IP release check to not reference peer_ip column"
```

---

### Task 9: Update tests

**Files:**
- Modify: `tests/factories.py`
- Modify: `tests/test_bgp_sessions.py`
- Modify: `tests/test_config_generation.py`
- Modify: `tests/test_agent.py`
- Modify: `tests/test_trunks.py`
- Modify: `tests/test_member_access.py`
- Modify: `tests/ui/test_bgp_sessions.py`

- [ ] **Step 1: Update BGPSessionFactory**

Remove `peer_ip`, `peer_asn`, `import_limit`, `export_limit` fields from the factory.

- [ ] **Step 2: Update test_bgp_sessions.py**

All tests that create BGP sessions via API need to:
- Remove `peer_ip`, `peer_asn`, `import_limit`, `export_limit` from request payloads
- Ensure test fixtures create the required IPAssignment before creating the BGP session
- Update assertions that check for peer_ip/peer_asn in responses (they should still appear as computed values)

- [ ] **Step 3: Update test_config_generation.py**

Tests that create BGPSession objects directly need to:
- Remove peer_ip/peer_asn from factory/constructor calls
- Add IPAssignment fixtures so peer_ip can be resolved

- [ ] **Step 4: Update test_agent.py**

Tests for agent status reporting need IP assignments in place so the join-based lookup works.

- [ ] **Step 5: Update test_trunks.py**

Update the IP release test that checks for BGP session conflict.

- [ ] **Step 6: Update test_member_access.py and ui/test_bgp_sessions.py**

Remove references to peer_ip/peer_asn in request bodies and factory calls.

- [ ] **Step 7: Run all tests**

```bash
uv run pytest -v --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add tests/
git commit -m "tests: update all BGP session tests for removed columns"
```

---

### Task 10: Update UI templates — remove peer_ip/peer_asn display references

**Files:**
- Modify: `src/ixforge/ui/templates/bgp_sessions/list_rows.html`
- Modify: `src/ixforge/ui/templates/bgp_sessions/detail.html`
- Modify: `src/ixforge/ui/templates/route_servers/detail.html`
- Modify: `src/ixforge/ui/templates/trunks/detail.html`
- Modify: `src/ixforge/ui/templates/portal/bgp_sessions.html`
- Modify: `src/ixforge/ui/routes/bgp_sessions.py`

- [ ] **Step 1: Update templates**

peer_ip and peer_asn still appear in the API response (computed), so template display stays mostly the same. Remove any references to `import_limit` and `export_limit` from `detail.html`.

- [ ] **Step 2: Commit**

```bash
git add src/ixforge/ui/
git commit -m "ui: remove import_limit/export_limit from BGP session templates"
```

---

### Task 11: Add BGP session creation — standalone form

**Files:**
- Modify: `src/ixforge/ui/routes/bgp_sessions.py`
- Create: `src/ixforge/ui/templates/bgp_sessions/form.html`
- Modify: `src/ixforge/ui/app.py`

- [ ] **Step 1: Add bgp_session_new handler**

```python
@require_auth
async def bgp_session_new(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api

    rs_data = await api.get("/api/v1/route-servers", token, params={"limit": 200})
    route_servers = rs_data.get("items", [])
    members_data = await api.get("/api/v1/members", token, params={"limit": 200})
    members = members_data.get("items", [])
    trunks_data = await api.get("/api/v1/trunks", token, params={"limit": 200})
    trunks = trunks_data.get("items", [])

    # Build trunk_vlans with IPs for each trunk
    trunk_vlans = []
    for t in trunks:
        try:
            tvs = await api.get(f"/api/v1/trunks/{t['id']}/vlans", token)
            for tv in tvs:
                tv["trunk_name"] = t.get("name", "")
                tv["member_id"] = t.get("member_id", "")
                tv["member_name"] = t.get("member_name", "")
                trunk_vlans.append(tv)
        except APIError:
            pass

    if request.method == "GET":
        preselect_rs_id = request.query_params.get("route_server_id", "")
        return render(request, "bgp_sessions/form.html", {
            "bgp_session": None,
            "route_servers": route_servers,
            "members": members,
            "trunk_vlans_json": json.dumps(trunk_vlans),
            "preselect_rs_id": preselect_rs_id,
            "errors": {},
            "page_title": "Nueva Sesion BGP",
        })

    form = await request.form()
    payload = {
        "route_server_id": str(form.get("route_server_id", "")),
        "trunk_vlan_id": str(form.get("trunk_vlan_id", "")),
        "af": int(form.get("af", 4)),
    }
    max_prefixes = str(form.get("max_prefixes", "")).strip()
    if max_prefixes:
        payload["max_prefixes"] = int(max_prefixes)

    try:
        await api.post("/api/v1/bgp-sessions", token, json=payload)
        add_flash(request, "Sesion BGP creada", "success")
        return RedirectResponse("/admin/bgp-sessions", status_code=302)
    except APIError as e:
        if e.status_code in (400, 409, 422):
            return render(request, "bgp_sessions/form.html", {
                "bgp_session": payload,
                "route_servers": route_servers,
                "members": members,
                "trunk_vlans_json": json.dumps(trunk_vlans),
                "preselect_rs_id": "",
                "errors": e.detail,
                "page_title": "Nueva Sesion BGP",
            })
        raise
```

- [ ] **Step 2: Create form template**

Create `src/ixforge/ui/templates/bgp_sessions/form.html` with:
- Route Server dropdown
- Miembro dropdown (filters trunk_vlans via Alpine.js)
- Trunk VLAN dropdown (dynamic, filtered by member)
- AF dropdown (IPv4 / IPv6)
- Max Prefixes (optional number)

- [ ] **Step 3: Register route**

In `src/ixforge/ui/app.py`:
```python
Route("/admin/bgp-sessions/new", bgp_sessions.bgp_session_new, methods=["GET", "POST"]),
```

- [ ] **Step 4: Add "Nueva Sesion BGP" button to list template**

In `src/ixforge/ui/templates/bgp_sessions/list.html`, add button next to the title.

- [ ] **Step 5: Commit**

```bash
git add src/ixforge/ui/
git commit -m "ui: add standalone BGP session creation form"
```

---

### Task 12: Add BGP session creation — inline form in route server detail

**Files:**
- Modify: `src/ixforge/ui/templates/route_servers/detail.html`
- Modify: `src/ixforge/ui/routes/route_servers.py`
- Modify: `src/ixforge/ui/app.py`

- [ ] **Step 1: Add route handler for creating BGP session from RS detail**

In `src/ixforge/ui/routes/route_servers.py`:
```python
@require_auth
async def route_server_add_bgp_session(request: Request) -> Response:
    token = require_token(request)
    api: APIClient = request.app.state.api
    rs_id = request.path_params["route_server_id"]
    form = await request.form()

    payload = {
        "route_server_id": rs_id,
        "trunk_vlan_id": str(form.get("trunk_vlan_id", "")),
        "af": int(form.get("af", 4)),
    }
    max_prefixes = str(form.get("max_prefixes", "")).strip()
    if max_prefixes:
        payload["max_prefixes"] = int(max_prefixes)

    try:
        await api.post("/api/v1/bgp-sessions", token, json=payload)
        add_flash(request, "Sesion BGP creada", "success")
    except APIError as e:
        add_flash(request, f"Error creando sesion BGP: {safe_detail(e)}", "error")

    return RedirectResponse(f"/admin/route-servers/{rs_id}", status_code=302)
```

- [ ] **Step 2: Add inline form to route server detail template**

In the BGP Sessions card of `route_servers/detail.html`, add a form below the table:
```html
<div class="border-t dark:border-gray-700 pt-4">
  <h3 class="text-sm font-semibold mb-3">Agregar Sesion BGP</h3>
  <form method="post" action="/admin/route-servers/{{ rs.id }}/bgp-sessions">
    <!-- trunk_vlan selector, af, max_prefixes, submit button -->
  </form>
</div>
```

The route server detail handler needs to pass trunk_vlans data to the template.

- [ ] **Step 3: Update route server detail handler to pass trunk_vlans**

Add trunk_vlans loading to the `route_server_detail` handler so the inline form has data.

- [ ] **Step 4: Register route**

```python
Route("/admin/route-servers/{route_server_id}/bgp-sessions", route_servers.route_server_add_bgp_session, methods=["POST"]),
```

- [ ] **Step 5: Commit**

```bash
git add src/ixforge/ui/
git commit -m "ui: add inline BGP session creation in route server detail"
```

---

### Task 13: Run migration on dev DB and verify

- [ ] **Step 1: Run migration on dev DB**

```bash
docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge upgrade
```

- [ ] **Step 2: Verify UI works end-to-end**

- Visit `/admin/bgp-sessions/new` and create a session
- Visit a route server detail and create a session inline
- Verify the session shows peer_ip and peer_asn correctly (resolved from relationships)

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -v --tb=short
```

- [ ] **Step 4: Run linting and type checking**

```bash
uv run ruff check src/ tests/
uv run mypy src/
```
