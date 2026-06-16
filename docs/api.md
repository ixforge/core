# API Reference

Base URL: `/api/v1`
Interactive docs: `/api/v1/docs` (Swagger) | `/api/v1/redoc` (ReDoc)

## Authentication

| Method | Header | Description |
|--------|--------|-------------|
| JWT | `Authorization: Bearer <token>` | 30-minute expiry, obtained via `/auth/login` |
| API Key | `X-API-Key: <raw_key>` | Scoped keys (raw value returned once at creation) |

API keys are bound to **either** a user (`POST /users/{id}/api-keys`) **or** a
route server (`POST /route-servers/{id}/api-keys`), never both. Valid scopes:

| Scope | Used by | Grants |
|-------|---------|--------|
| `agent:route_server` | Route server agents | The `/route-servers/{id}/agent/*` endpoints for the bound RS |
| `monitoring:read` | The collector | `GET /monitoring/targets` |

## Pagination

List endpoints use cursor-based pagination:

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
| GET | `/auth/me` | JWT/Key | Current user info |

### IXP Settings (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ixp` | Get IXP settings |
| PATCH | `/ixp` | Update IXP settings |

### Users (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users` | List users |
| POST | `/users` | Create user |
| GET | `/users/me` | Current user |
| GET | `/users/{id}` | Get user |
| PATCH | `/users/{id}` | Update user |
| DELETE | `/users/{id}` | Delete user |
| POST | `/users/{id}/api-keys` | Create API key (returns raw key once) |
| GET | `/users/{id}/api-keys` | List API keys |

### Members

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/members` | JWT/Key | List (admin: all, member: own) |
| POST | `/members` | Admin | Create member |
| GET | `/members/asn-lookup?asn=` | Admin | Lookup ASN name via PeeringDB/RIPE |
| GET | `/members/{id}` | JWT/Key | Get member |
| GET | `/members/{id}/asn-name` | JWT/Key | Get member ASN name |
| PATCH | `/members/{id}` | Admin | Update member |
| DELETE | `/members/{id}` | Admin | Delete member |
| POST | `/members/{id}/transition` | Admin | Change state (`{"state": "active"}`) |
| POST | `/members/{id}/logo` | Admin | Upload member logo |
| DELETE | `/members/{id}/logo` | Admin | Delete member logo |

States: `prospect` -> `provisioning` -> `active` <-> `suspended` -> `terminated`

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
| DELETE | `/ip-assignments/{id}` | Release IP assignment |

### Trunks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/trunks?member_id=` | JWT/Key | List trunks (admin: all, member: own) |
| POST | `/trunks` | Admin | Create trunk (`{"member_id": "...", "name": "ae0"}`) |
| GET | `/trunks/{id}` | JWT/Key | Get trunk |
| PATCH | `/trunks/{id}` | Admin | Update trunk |
| DELETE | `/trunks/{id}` | Admin | Delete trunk (must be decommissioned) |
| POST | `/trunks/{id}/transition` | Admin | Change state (`{"state": "active"}`) |
| GET | `/trunks/{id}/vlans` | JWT/Key | List trunk VLAN assignments |
| POST | `/trunks/{id}/vlans` | Admin | Assign VLAN to trunk (`{"vlan_id": "..."}`) |
| DELETE | `/trunks/{id}/vlans/{tv_id}` | Admin | Unassign VLAN |
| GET | `/trunks/{id}/connections` | JWT/Key | List trunk connections |
| POST | `/trunks/{id}/connections` | Admin | Add connection to trunk |

States: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`

### Connections

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/connections?switch_id=` | JWT/Key | List connections (admin: all, member: own) |
| GET | `/connections/{id}` | JWT/Key | Get connection |
| PATCH | `/connections/{id}` | Admin | Update connection |
| DELETE | `/connections/{id}` | Admin | Delete connection |
| POST | `/connections/{id}/transition` | Admin | Change state (`{"state": "active"}`) |

States: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`

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
| GET | `/bgp-sessions?route_server_id=` | JWT/Key | List sessions for a route server (param required; admin: all, member: own) |
| POST | `/bgp-sessions` | Admin | Create session (`{"route_server_id", "trunk_vlan_id", "af"}`) |
| GET | `/bgp-sessions/{id}` | JWT/Key | Get session |
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
| GET | `/events` | JWT/Key | Audit log (admin: all, member: own). Filters: `resource_type`, `resource_id` |

### Custom Fields

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/custom-fields` | JWT/Key | List definitions. Filter: `entity_type` |
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
| GET | `/metrics` | - | Prometheus metrics (not in OpenAPI) |
