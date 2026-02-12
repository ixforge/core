# API Reference

Base URL: `/api/v1`
Interactive docs: `/api/v1/docs` (Swagger) | `/api/v1/redoc` (ReDoc)

## Authentication

| Method | Header | Description |
|--------|--------|-------------|
| JWT | `Authorization: Bearer <token>` | 30-minute expiry, obtained via `/auth/login` |
| API Key | `X-API-Key: <raw_key>` | Scoped keys, created via `/users/{id}/api-keys` |

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

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | - | Login, returns JWT |
| GET | `/auth/me` | JWT/Key | Current user info |

### Users (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users` | List users |
| POST | `/users` | Create user |
| GET | `/users/{id}` | Get user |
| PATCH | `/users/{id}` | Update user |
| POST | `/users/{id}/api-keys` | Create API key (returns raw key once) |
| GET | `/users/{id}/api-keys` | List API keys |

### Members

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/members` | JWT/Key | List (admin: all, member: own) |
| POST | `/members` | Admin | Create member |
| GET | `/members/{id}` | JWT/Key | Get member |
| PATCH | `/members/{id}` | Admin | Update member |
| POST | `/members/{id}/transition` | Admin | Change state (`{"state": "active"}`) |

States: `prospect` -> `provisioning` -> `active` <-> `suspended` -> `terminated`

### Contacts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/members/{id}/contacts` | Member/Admin | List contacts |
| POST | `/members/{id}/contacts` | Member/Admin | Create contact |
| PATCH | `/contacts/{id}` | Member/Admin | Update contact |
| DELETE | `/contacts/{id}` | Member/Admin | Delete contact |

### Switches (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/switches` | List switches |
| POST | `/switches` | Create switch |
| GET | `/switches/{id}` | Get switch |
| PATCH | `/switches/{id}` | Update switch |
| DELETE | `/switches/{id}` | Delete switch |

### Ports (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ports?switch_id=` | List ports for switch |
| POST | `/ports` | Create port |
| GET | `/ports/{id}` | Get port |
| PATCH | `/ports/{id}` | Update port |
| DELETE | `/ports/{id}` | Delete port |
| POST | `/ports/{id}/assign` | Assign to member (`{"member_id": "..."}`) |
| POST | `/ports/{id}/release` | Release from member |

### VLANs (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vlans` | List VLANs |
| POST | `/vlans` | Create VLAN |
| GET | `/vlans/{id}` | Get VLAN |
| PATCH | `/vlans/{id}` | Update VLAN |
| DELETE | `/vlans/{id}` | Delete VLAN |

### IP Pools (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ip-pools?vlan_id=` | List pools for VLAN |
| POST | `/ip-pools` | Create pool |
| GET | `/ip-pools/{id}` | Get pool |
| DELETE | `/ip-pools/{id}` | Delete pool |
| GET | `/ip-pools/{id}/assignments` | List IP assignments |
| POST | `/ip-pools/{id}/assign` | Allocate IP (`{"connection_id": "...", "address": "..."}`, address optional) |
| DELETE | `/ip-assignments/{id}` | Release IP |

### Connections (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/connections?member_id=` | List connections for member |
| POST | `/connections` | Create connection |
| GET | `/connections/{id}` | Get connection |
| PATCH | `/connections/{id}` | Update connection |
| POST | `/connections/{id}/transition` | Change state (`{"state": "active"}`) |
| POST | `/connections/{id}/vlans` | Assign VLAN |
| DELETE | `/connections/{id}/vlans/{vlan_id}` | Unassign VLAN |
| POST | `/connections/{id}/ips` | Assign IP (`{"pool_id": "...", "address": "..."}`) |
| DELETE | `/connections/{id}/ips/{assignment_id}` | Release IP |

States: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`

### Route Servers (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/route-servers` | List route servers |
| POST | `/route-servers` | Create route server |
| GET | `/route-servers/{id}` | Get route server |
| PATCH | `/route-servers/{id}` | Update route server |
| DELETE | `/route-servers/{id}` | Delete route server |

### Config Generation (admin only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/route-servers/{id}/config/generate` | Generate BIRD config |
| GET | `/route-servers/{id}/config/history` | Config version history |
| GET | `/route-servers/{id}/config/current` | Latest config version |
| GET | `/route-servers/{id}/config/diff?from=&to=` | Unified diff between versions |

### BGP Sessions (admin only)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/bgp-sessions?route_server_id=` | List sessions |
| GET | `/bgp-sessions/{id}` | Get session |
| PATCH | `/bgp-sessions/{id}` | Update admin state (`{"admin_state": "up"}`) |

### Agent API (API Key with `agent:route_server` scope)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/route-servers/{id}/agent/config` | Poll latest config (hash + content) |
| POST | `/route-servers/{id}/agent/status` | Report BGP session states |
| POST | `/route-servers/{id}/agent/heartbeat` | Agent heartbeat |

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
| GET | `/monitoring/targets` | Switches (SNMP), ports, member IPs |

### Metrics

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | - | Prometheus metrics (not in OpenAPI) |
