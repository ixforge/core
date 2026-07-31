# API Reference

Base URL: `/api/v1`
Interactive docs: `/api/v1/docs` (Swagger) | `/api/v1/redoc` (ReDoc)

## Authentication

| Method | Header | Description |
|--------|--------|-------------|
| JWT | `Authorization: Bearer <token>` | 30-minute expiry, obtained via `/auth/login` |
| API Key | `X-API-Key: <raw_key>` | Scoped keys (raw value returned once at creation) |

API keys are bound to **either** a user (`POST /users/{id}/api-keys`) **or** a
route server (`POST /route-servers/{id}/api-keys`), never both. A key only works
on the endpoints of its scope; it does **not** authenticate the rest of the API
(members, users, trunks, ...), which requires a JWT. Valid scopes:

| Scope | Used by | Grants |
|-------|---------|--------|
| `agent:route_server` | Route server agents | The `/route-servers/{id}/agent/*` endpoints for the bound RS |
| `monitoring:read` | The collector | `GET /monitoring/targets` |

## Pagination

Top-level collection endpoints (`/members`, `/users`, `/trunks`, `/connections`,
`/bgp-sessions`, ...) use cursor-based pagination. Nested sub-resource lists (a
trunk's VLANs, a VLAN's IPs, a route server's keys, ...) return a plain array.

Cursor-based pagination:

```
GET /members?limit=50&cursor=<opaque_string>
```

Response:
```json
{
  "items": [...],
  "next_cursor": "abc123...",
  "has_more": true
}
```

## Error Format

Every error uses this envelope. `details` is usually an object, but for
validation errors (422) it is the list of Pydantic field errors.

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Member not found",
    "details": {}
  }
}
```

Codes: `NOT_FOUND` (404), `CONFLICT` (409), `VALIDATION_ERROR` (422), `FORBIDDEN` (403), `UNAUTHORIZED` (401).

---

## Endpoints

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | - | Health check with component status |

### Setup

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/setup/status` | - | Check if IXP is configured |
| POST | `/setup` | - | Initial IXP + admin user creation |

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | - | Login, returns JWT |
| GET | `/auth/me` | JWT | Current user info |

### IXP Settings

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ixp` | JWT | Get IXP settings |
| PATCH | `/ixp` | Admin | Update IXP settings |

### Users

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users` | Admin | List users |
| POST | `/users` | Admin | Create user |
| GET | `/users/me` | JWT | Current user |
| GET | `/users/{id}` | Admin | Get user |
| PATCH | `/users/{id}` | Admin | Update user |
| DELETE | `/users/{id}` | Admin | Delete user (must be inactive, not self, not last admin) |
| POST | `/users/{id}/api-keys` | Create API key (returns raw key once) |
| GET | `/users/{id}/api-keys` | List API keys |
| DELETE | `/users/{id}/api-keys/{key_id}` | Revoke API key |

### Members

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/members` | JWT | List (admin: all, member: own) |
| POST | `/members` | Admin | Create member |
| GET | `/members/asn-lookup?asn=` | JWT | Lookup ASN name (local -> 7-day cache -> PeeringDB) |
| GET | `/members/{id}` | JWT | Get member |
| GET | `/members/{id}/asn-name` | JWT | Get member ASN name |
| PATCH | `/members/{id}` | Admin | Update member |
| DELETE | `/members/{id}` | Admin | Delete member (must be `terminated`) |
| POST | `/members/{id}/transition` | Admin | Change state (`{"state": "active"}`) |
| POST | `/members/{id}/logo` | Admin | Upload member logo |
| DELETE | `/members/{id}/logo` | Admin | Delete member logo |

States: `prospect` -> `provisioning` -> `active` <-> `suspended`; `provisioning`,
`active` and `suspended` can go to `terminated`

### Contacts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/members/{id}/contacts` | Member/Admin | List contacts |
| POST | `/members/{id}/contacts` | Member/Admin | Create contact |
| PATCH | `/contacts/{id}` | Member/Admin | Update contact |
| DELETE | `/contacts/{id}` | Member/Admin | Delete contact |

### Locations (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/locations` | List locations |
| POST | `/locations` | Create location |
| GET | `/locations/{id}` | Get location |
| PATCH | `/locations/{id}` | Update location |
| DELETE | `/locations/{id}` | Delete location |

### Switches (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/switches` | List switches |
| POST | `/switches` | Create switch |
| GET | `/switches/{id}` | Get switch |
| PATCH | `/switches/{id}` | Update switch |
| DELETE | `/switches/{id}` | Delete switch |

### VLANs (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vlans` | List VLANs |
| POST | `/vlans` | Create VLAN |
| GET | `/vlans/{id}` | Get VLAN |
| PATCH | `/vlans/{id}` | Update VLAN |
| DELETE | `/vlans/{id}` | Delete VLAN |
| GET | `/vlans/{id}/members` | List VLAN member assignments |
| POST | `/vlans/{id}/members` | Assign member to VLAN |
| DELETE | `/vlans/{id}/members/{member_id}` | Unassign member from VLAN |

### IP Pools (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ip-pools?vlan_id=` | List pools for VLAN |
| POST | `/ip-pools` | Create pool |
| GET | `/ip-pools/available?vlan_id=` | Pool availability (next IP, stats) |
| GET | `/ip-pools/{id}` | Get pool |
| DELETE | `/ip-pools/{id}` | Delete pool |
| GET | `/ip-pools/{id}/assignments` | List IP assignments in a pool |
| POST | `/ip-pools/{id}/assign` | Allocate an IP (`{"trunk_vlan_id": "..."}`; optional `"address"` for manual, else sequential) |
| DELETE | `/ip-assignments/{id}` | Release IP assignment |

### Trunks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/trunks?member_id=` | JWT | List trunks (admin: all, member: own) |
| POST | `/trunks` | Admin | Create trunk (`{"member_id": "...", "name": "ae0"}`) |
| GET | `/trunks/{id}` | JWT | Get trunk |
| PATCH | `/trunks/{id}` | Admin | Update trunk |
| DELETE | `/trunks/{id}` | Admin | Delete trunk (must be decommissioned) |
| POST | `/trunks/{id}/transition` | Admin | Change state (`{"state": "active"}`) |
| GET | `/trunks/{id}/vlans` | JWT | List trunk VLAN assignments |
| POST | `/trunks/{id}/vlans` | Admin | Assign VLAN to trunk (`{"vlan_id": "..."}`) |
| DELETE | `/trunks/{id}/vlans/{tv_id}` | Admin | Unassign VLAN |
| GET | `/trunks/{id}/vlans/{tv_id}/ips` | JWT | List IPs of a trunk VLAN |
| POST | `/trunks/{id}/vlans/{tv_id}/ips` | Admin | Assign IP (`{"pool_id": "...", "address": "..."}`; `address` optional) |
| DELETE | `/trunks/{id}/vlans/{tv_id}/ips/{assignment_id}` | Admin | Release IP |
| GET | `/trunks/{id}/connections` | JWT | List trunk connections |
| POST | `/trunks/{id}/connections` | Admin | Add connection to trunk |

States: `draft` -> `provisioning` -> `active` <-> `disabled`; `provisioning` and
`disabled` can go to `decommissioned`

### Connections

Connections are created under their trunk via `POST /trunks/{id}/connections` (see Trunks);
the endpoints below operate on existing connections.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/connections?switch_id=` | JWT | List connections (admin: all, member: own) |
| GET | `/connections/{id}` | JWT | Get connection |
| PATCH | `/connections/{id}` | Admin | Update connection |
| DELETE | `/connections/{id}` | Admin | Delete connection (must be `decommissioned`) |
| POST | `/connections/{id}/transition` | Admin | Change state (`{"state": "active"}`) |

States: `draft` -> `provisioning` -> `active` <-> `disabled`; `provisioning` and
`disabled` can go to `decommissioned`

### Route Servers (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/route-servers` | List route servers |
| POST | `/route-servers` | Create route server |
| GET | `/route-servers/{id}` | Get route server |
| PATCH | `/route-servers/{id}` | Update route server |
| DELETE | `/route-servers/{id}` | Delete route server |
| GET | `/route-servers/{id}/vlans` | List RS VLAN assignments |
| POST | `/route-servers/{id}/vlans` | Assign VLAN to RS |
| DELETE | `/route-servers/{id}/vlans/{vlan_id}` | Unassign VLAN |
| GET | `/route-servers/{id}/ips` | List RS IP assignments |
| POST | `/route-servers/{id}/ips` | Assign IP to RS |
| DELETE | `/route-servers/{id}/ips/{assignment_id}` | Release IP |
| GET | `/route-servers/{id}/api-keys` | List agent API keys for RS |
| POST | `/route-servers/{id}/api-keys` | Create agent API key bound to RS (returns raw key once, scope `agent:route_server`) |
| DELETE | `/route-servers/{id}/api-keys/{key_id}` | Revoke agent API key |

### Config Generation (admin only)

`GET /route-servers/{id}/config/diff?to=<version>` diffs a config version against
the previous one; pass `&from=<version>` to compare two explicit versions.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/route-servers/{id}/config/generate` | Generate BIRD config |
| GET | `/route-servers/{id}/config/history` | Config version history |
| GET | `/route-servers/{id}/config/current` | Latest config version |
| GET | `/route-servers/{id}/config/diff?from=&to=` | Unified diff between versions |

### Route Server Templates (admin only)

BIRD templates are stored per-IXP in the database and rendered by config
generation. The default set is installed at IXP setup; `bird_v4.conf.j2` and
`bird_v6.conf.j2` are protected and cannot be deleted.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/rs-templates` | List templates |
| POST | `/rs-templates` | Create template |
| POST | `/rs-templates/validate` | Validate Jinja2 syntax without saving |
| GET | `/rs-templates/{id}` | Get template |
| PATCH | `/rs-templates/{id}` | Update template content/description |
| DELETE | `/rs-templates/{id}` | Delete template (fails if protected or referenced) |
| POST | `/rs-templates/{id}/preview` | Render a preview against a route server (`{"route_server_id": "..."}`) |

### BGP Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/bgp-sessions?route_server_id=` | JWT | List sessions for a route server (param required; admin: all, member: own) |
| POST | `/bgp-sessions` | Admin | Create session (`{"route_server_id", "trunk_vlan_id", "af"}`) |
| GET | `/bgp-sessions/{id}` | JWT | Get session |
| PATCH | `/bgp-sessions/{id}` | Admin | Update admin state (`{"admin_state": "up"}`) |
| DELETE | `/bgp-sessions/{id}` | Admin | Delete session |

Note: `peer_ip` and `peer_asn` are computed from IP assignments and member ASN respectively, not stored on the session.

### Agent API (API Key with `agent:route_server` scope)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/route-servers/{id}/agent/config` | Poll latest config (hash + content) |
| POST | `/route-servers/{id}/agent/status` | Report BGP session states |
| POST | `/route-servers/{id}/agent/heartbeat` | Agent heartbeat |
| POST | `/route-servers/{id}/agent/config/applied` | Confirm config applied |

### Events

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events` | JWT | Audit log (admin: all, member: own). Filters: `resource_type`, `resource_id` |

### Custom Fields

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/custom-fields` | JWT | List definitions. Filter: `entity_type` |
| POST | `/custom-fields` | Admin | Create definition |
| PATCH | `/custom-fields/{id}` | Admin | Update definition |
| DELETE | `/custom-fields/{id}` | Admin | Delete definition |

### IX-F Export

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ixf/member-export` | - | IX-F Member Export JSON v1.0 (public, rate-limited, cached 5min) |

### Monitoring (API Key with `monitoring:read` scope)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/monitoring/targets` | Switches (SNMP), connections, member IPs |

### Metrics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | - | Prometheus metrics. Served at the app root (`/metrics`), outside the `/api/v1` base, and not in OpenAPI |
