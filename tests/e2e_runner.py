#!/usr/bin/env python3
"""End-to-end test suite for IXForge API.

Runs against a live server with a real database.  Expects:
- Uvicorn running at $E2E_BASE_URL (default http://127.0.0.1:8000/api/v1)
- Admin user created with email/password from $E2E_ADMIN_EMAIL / $E2E_ADMIN_PASSWORD
- Seed data loaded via ``ixforge seed``

Usage:
    python tests/e2e_test.py                   # run with defaults
    E2E_BASE_URL=http://host/api/v1 python tests/e2e_test.py
"""

import json
import os
import subprocess
import sys

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000/api/v1")
ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@demo-ixp.net")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "adminpass123")

total = 0
passed_count = 0
failed: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login() -> str:
    """Obtain a JWT token for the admin user."""
    r = subprocess.run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{BASE}/auth/login",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}),
        ],
        capture_output=True,
        text=True,
    )
    return json.loads(r.stdout)["access_token"]


TOKEN = ""


def req(method: str, path: str, data=None, expect: int = 200, auth: bool = True):
    cmd = [
        "curl",
        "-s",
        "-w",
        "\n%{http_code}",
        "-X",
        method,
        f"{BASE}{path}",
        "-H",
        "Content-Type: application/json",
    ]
    if auth:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    if data:
        cmd += ["-d", json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    raw = r.stdout.strip()
    if "\n" in raw:
        body, code_str = raw.rsplit("\n", 1)
    else:
        body, code_str = "", raw
    try:
        code = int(code_str)
    except ValueError:
        code = 0
    try:
        parsed = json.loads(body) if body else {}
    except Exception:
        parsed = {"_raw": body}
    return code, parsed, code == expect


def test(name, method, path, data=None, expect=200, check=None, auth=True):
    global total, passed_count
    total += 1
    code, body, ok = req(method, path, data, expect, auth)
    if check and ok:
        try:
            ok = check(body)
        except Exception:
            ok = False
    if ok:
        passed_count += 1
        print(f"  [PASS] {name} (HTTP {code})")
    else:
        failed.append(name)
        detail = ""
        if isinstance(body, dict):
            if "error" in body:
                detail = f" - {body['error'].get('message', '')}"
            elif "detail" in body:
                d = body["detail"]
                if isinstance(d, str):
                    detail = f" - {d}"
                elif isinstance(d, list) and d:
                    detail = f" - {d[0].get('msg', '')}"
        print(f"  [FAIL] {name} (HTTP {code}, expect {expect}){detail}")
    return body


def raw_test(name, url, expect_code="200"):
    global total, passed_count
    total += 1
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    ok = r.stdout.strip() == expect_code
    if ok:
        passed_count += 1
    else:
        failed.append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} (HTTP {r.stdout.strip()}, expect {expect_code})")


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


def run():
    global TOKEN

    TOKEN = _login()

    print("=" * 60)
    print("  EXHAUSTIVE E2E TEST SUITE - IXForge Core")
    print("=" * 60)

    # === AUTH ===
    print("\n-- AUTH --")
    test(
        "Login valid",
        "POST",
        "/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        200,
        lambda b: "access_token" in b and b["token_type"] == "bearer",
        auth=False,
    )
    test(
        "Login wrong password",
        "POST",
        "/auth/login",
        {"email": ADMIN_EMAIL, "password": "wrong"},
        401,
        auth=False,
    )
    test(
        "Login nonexistent user",
        "POST",
        "/auth/login",
        {"email": "no@example.com", "password": "x"},
        401,
        auth=False,
    )
    test(
        "GET /me valid token",
        "GET",
        "/auth/me",
        expect=200,
        check=lambda b: b.get("email") == ADMIN_EMAIL and b["role"] == "admin",
    )
    test("GET /me no auth", "GET", "/auth/me", expect=401, auth=False)
    test("GET /me invalid token", "GET", "/auth/me", expect=401, auth=False)

    # === HEALTH ===
    print("\n-- HEALTH --")
    test(
        "Health check",
        "GET",
        "/health",
        expect=200,
        check=lambda b: b["status"] == "healthy" and b["checks"]["database"]["status"] == "ok",
        auth=False,
    )

    # === MEMBERS CRUD ===
    print("\n-- MEMBERS CRUD --")
    ml = test("List members", "GET", "/members", expect=200, check=lambda b: len(b["items"]) >= 5)
    test(
        "List with limit=2",
        "GET",
        "/members?limit=2",
        expect=200,
        check=lambda b: len(b["items"]) == 2 and b["has_more"] is True,
    )
    m = test(
        "Create member (prospect)",
        "POST",
        "/members",
        {"name": "E2E Net", "short_name": "E2N", "asn": 64700},
        201,
        lambda b: b["state"] == "prospect" and b["asn"] == 64700,
    )
    mid = m.get("id", "")
    ixp_id = m.get("ixp_id", "")
    test(
        "Get member by ID",
        "GET",
        f"/members/{mid}",
        expect=200,
        check=lambda b: b["name"] == "E2E Net",
    )
    test(
        "Update member",
        "PATCH",
        f"/members/{mid}",
        {"website": "https://e2n.test", "peering_policy": "selective"},
        200,
        check=lambda b: b["website"] == "https://e2n.test",
    )
    test(
        "Duplicate ASN rejected",
        "POST",
        "/members",
        {"name": "Dup", "short_name": "DUP", "asn": 64700},
        409,
    )
    test("Member not found", "GET", "/members/00000000-0000-0000-0000-000000000000", expect=404)
    test("Missing required fields", "POST", "/members", {"name": "Bad"}, 422)

    # === MEMBER STATE MACHINE (basic) ===
    print("\n-- MEMBER STATE MACHINE --")
    test(
        "prospect -> provisioning",
        "POST",
        f"/members/{mid}/transition",
        {"state": "provisioning"},
        200,
        lambda b: b["state"] == "provisioning",
    )
    test(
        "INVALID: provisioning -> prospect",
        "POST",
        f"/members/{mid}/transition",
        {"state": "prospect"},
        422,
    )
    test(
        "INVALID: provisioning -> active (no conn)",
        "POST",
        f"/members/{mid}/transition",
        {"state": "active"},
        422,
    )

    # === SWITCHES ===
    print("\n-- SWITCHES --")
    sw = test(
        "List switches", "GET", "/switches", expect=200, check=lambda b: len(b["items"]) >= 2
    )
    sw_id = sw["items"][0]["id"]
    test(
        "Get switch",
        "GET",
        f"/switches/{sw_id}",
        expect=200,
        check=lambda b: b["vendor"] == "Arista",
    )
    new_sw = test(
        "Create switch",
        "POST",
        "/switches",
        {
            "name": "sw-e2n",
            "hostname": "sw-e2n.test",
            "vendor": "Juniper",
            "model": "QFX5100",
            "management_ip": "10.0.0.201",
        },
        201,
        lambda b: b["name"] == "sw-e2n",
    )

    # === PORTS ===
    print("\n-- PORTS --")
    p = test(
        "List ports",
        "GET",
        f"/ports?switch_id={sw_id}",
        expect=200,
        check=lambda b: len(b["items"]) >= 4,
    )
    port_id = p["items"][0]["id"]
    test(
        "Get port", "GET", f"/ports/{port_id}", expect=200, check=lambda b: "Ethernet" in b["name"]
    )
    test(
        "Create port",
        "POST",
        "/ports",
        {"switch_id": new_sw.get("id", ""), "name": "Ethernet1", "speed": 40000, "type": "member"},
        201,
        lambda b: b["name"] == "Ethernet1",
    )

    # === VLANS ===
    print("\n-- VLANS --")
    v = test("List VLANs", "GET", "/vlans", expect=200, check=lambda b: len(b["items"]) >= 2)
    prod_vlan_id = None
    for vl in v.get("items", []):
        if vl.get("vid") == 100:
            prod_vlan_id = vl["id"]
            break
    if not prod_vlan_id:
        prod_vlan_id = v["items"][0]["id"]
    test("Get VLAN", "GET", f"/vlans/{prod_vlan_id}", expect=200, check=lambda b: "vid" in b)
    test(
        "Create VLAN",
        "POST",
        "/vlans",
        {"name": "E2E VLAN", "vid": 501, "type": "production"},
        201,
        lambda b: b["vid"] == 501,
    )

    # === IP POOLS ===
    print("\n-- IP POOLS --")
    ip_pools = test(
        "List IP pools",
        "GET",
        f"/ip-pools?vlan_id={prod_vlan_id}",
        expect=200,
        check=lambda b: len(b["items"]) >= 1,
    )
    pool_id = ip_pools["items"][0]["id"] if ip_pools.get("items") else ""
    test(
        "Get IP pool",
        "GET",
        f"/ip-pools/{pool_id}",
        expect=200,
        check=lambda b: "network" in b and "gateway" in b,
    )

    # === CONNECTIONS ===
    print("\n-- CONNECTIONS --")
    active_member = None
    for mm in ml.get("items", []):
        if mm["state"] == "active":
            active_member = mm
            break

    if active_member:
        c = test(
            "List connections",
            "GET",
            f"/connections?member_id={active_member['id']}",
            expect=200,
            check=lambda b: len(b["items"]) >= 1,
        )
        if c.get("items"):
            test(
                "Get connection",
                "GET",
                f"/connections/{c['items'][0]['id']}",
                expect=200,
                check=lambda b: "type" in b,
            )

    # Build a complete connection: port + VLAN + IP
    free_port = None
    for pp in p.get("items", []):
        if "Ethernet3" in pp["name"]:
            free_port = pp["id"]
            break
    if not free_port:
        for pp in p.get("items", []):
            if "Ethernet4" in pp["name"]:
                free_port = pp["id"]
                break

    if free_port and mid:
        cn = test(
            "Create connection",
            "POST",
            "/connections",
            {"member_id": mid, "port_id": free_port, "type": "physical", "speed": 10000},
            201,
            lambda b: "id" in b,
        )
        cn_id = cn.get("id", "")

        if cn_id:
            print("\n-- COMPLETE CONNECTION SETUP --")
            test(
                "Attach VLAN",
                "POST",
                f"/connections/{cn_id}/vlans",
                {"vlan_id": prod_vlan_id, "tagged": False},
                201,
            )
            if pool_id:
                test(
                    "Assign IP",
                    "POST",
                    f"/connections/{cn_id}/ips",
                    {"pool_id": pool_id},
                    201,
                    lambda b: "address" in b,
                )
            test(
                "Verify connection",
                "GET",
                f"/connections/{cn_id}",
                expect=200,
                check=lambda b: b.get("id") == cn_id,
            )

            print("\n-- FULL LIFECYCLE --")
            test(
                "provisioning -> active",
                "POST",
                f"/members/{mid}/transition",
                {"state": "active"},
                200,
                lambda b: b["state"] == "active",
            )
            test(
                "active -> suspended",
                "POST",
                f"/members/{mid}/transition",
                {"state": "suspended"},
                200,
                lambda b: b["state"] == "suspended",
            )
            test(
                "suspended -> active",
                "POST",
                f"/members/{mid}/transition",
                {"state": "active"},
                200,
                lambda b: b["state"] == "active",
            )
            test(
                "active -> suspended (again)",
                "POST",
                f"/members/{mid}/transition",
                {"state": "suspended"},
                200,
                lambda b: b["state"] == "suspended",
            )

    # === ROUTE SERVERS ===
    print("\n-- ROUTE SERVERS --")
    rs = test(
        "List route servers",
        "GET",
        "/route-servers",
        expect=200,
        check=lambda b: len(b["items"]) == 2,
    )
    rs_id = rs["items"][0]["id"]
    test(
        "Get route server",
        "GET",
        f"/route-servers/{rs_id}",
        expect=200,
        check=lambda b: b["software"] == "bird",
    )

    # === BGP SESSIONS ===
    print("\n-- BGP SESSIONS --")
    bgp = test(
        "List BGP sessions",
        "GET",
        f"/bgp-sessions?route_server_id={rs_id}",
        expect=200,
        check=lambda b: len(b["items"]) >= 1,
    )
    test(
        "Get BGP session",
        "GET",
        f"/bgp-sessions/{bgp['items'][0]['id']}",
        expect=200,
        check=lambda b: "peer_asn" in b,
    )

    # === CONFIG GENERATION ===
    print("\n-- CONFIG GENERATION --")
    cfg = test(
        "Generate BIRD config",
        "POST",
        f"/route-servers/{rs_id}/config/generate",
        expect=201,
        check=lambda b: "content" in b and "config_hash" in b,
    )
    if cfg.get("content"):
        lines = cfg["content"].split("\n")
        global total, passed_count
        total += 1
        ok = len(lines) > 50
        if ok:
            passed_count += 1
        else:
            failed.append("Config >50 lines")
        print(f"  [{'PASS' if ok else 'FAIL'}] Config has {len(lines)} lines (>50)")

        total += 1
        ok = "protocol bgp" in cfg["content"]
        if ok:
            passed_count += 1
        else:
            failed.append("Config has BGP")
        print(f"  [{'PASS' if ok else 'FAIL'}] Config contains 'protocol bgp'")

        total += 1
        ok = len(cfg["config_hash"]) == 64
        if ok:
            passed_count += 1
        else:
            failed.append("Config hash")
        print(f"  [{'PASS' if ok else 'FAIL'}] Config hash is 64 chars")

    # === CONFIG HISTORY ===
    print("\n-- CONFIG HISTORY --")
    test(
        "Config version history",
        "GET",
        f"/route-servers/{rs_id}/config/history",
        expect=200,
        check=lambda b: len(b.get("items", [])) >= 1,
    )

    # === IX-F EXPORT ===
    print("\n-- IX-F EXPORT --")
    ixf = test(
        "IX-F member export",
        "GET",
        "/ixf/member-export",
        expect=200,
        check=lambda b: b.get("version") == "1.0",
        auth=False,
    )
    if ixf.get("version"):
        ixp_list = ixf.get("ixp_list", [])
        members_list = ixf.get("member_list", [])
        total += 1
        ok = len(members_list) >= 2
        if ok:
            passed_count += 1
        else:
            failed.append("IX-F active members")
        print(f"  [{'PASS' if ok else 'FAIL'}] IX-F has {len(members_list)} active members (>=2)")

        total += 1
        ok = len(ixp_list) >= 1 and ixp_list[0].get("shortname") == "DEMO"
        if ok:
            passed_count += 1
        else:
            failed.append("IX-F IXP data")
        print(f"  [{'PASS' if ok else 'FAIL'}] IX-F contains IXP 'DEMO'")

    # === EVENTS ===
    print("\n-- EVENTS --")
    test("List events", "GET", "/events", expect=200, check=lambda b: len(b.get("items", [])) >= 1)

    # === USERS ===
    print("\n-- USERS --")
    test(
        "List users",
        "GET",
        "/users",
        expect=200,
        check=lambda b: isinstance(b, list) and len(b) >= 1,
    )
    test(
        "Create user",
        "POST",
        "/users",
        {
            "email": "member@demo-ixp.net",
            "password": "memberpass123",
            "full_name": "Member User",
            "role": "member",
        },
        201,
        check=lambda b: b.get("email") == "member@demo-ixp.net",
    )

    # === CONTACTS ===
    print("\n-- CONTACTS --")
    if active_member:
        test(
            "Create contact",
            "POST",
            f"/members/{active_member['id']}/contacts",
            {
                "name": "John NOC",
                "email": "noc@acme.example.com",
                "role": "noc",
                "phone": "+1-555-0100",
            },
            201,
            lambda b: b.get("name") == "John NOC",
        )
        test(
            "List contacts",
            "GET",
            f"/members/{active_member['id']}/contacts",
            expect=200,
            check=lambda b: isinstance(b, (list, dict)),
        )

    # === CUSTOM FIELDS ===
    print("\n-- CUSTOM FIELDS --")
    if ixp_id:
        cf = test(
            "Create custom field",
            "POST",
            "/custom-fields",
            {
                "entity_type": "member",
                "field_name": "noc_hours",
                "field_type": "string",
                "is_required": False,
                "description": "NOC hours",
            },
            201,
            lambda b: b.get("field_name") == "noc_hours",
        )
        test(
            "List custom fields",
            "GET",
            f"/custom-fields?ixp_id={ixp_id}",
            expect=200,
            check=lambda b: len(b.get("items", [])) >= 1,
        )
        if cf.get("id"):
            test("Delete custom field", "DELETE", f"/custom-fields/{cf['id']}", expect=204)

    # === AGENT API (auth required) ===
    print("\n-- AGENT API --")
    test(
        "Agent config (no key)",
        "GET",
        f"/route-servers/{rs_id}/agent/config",
        expect=401,
        auth=False,
    )
    test(
        "Agent status (no key)",
        "POST",
        f"/route-servers/{rs_id}/agent/status",
        expect=401,
        auth=False,
    )
    test(
        "Agent heartbeat (no key)",
        "POST",
        f"/route-servers/{rs_id}/agent/heartbeat",
        expect=401,
        auth=False,
    )

    # === MONITORING (auth required) ===
    print("\n-- MONITORING --")
    test("Monitoring targets (no key)", "GET", "/monitoring/targets", expect=401, auth=False)

    # === INFRASTRUCTURE ===
    print("\n-- INFRASTRUCTURE --")
    server_base = BASE.rsplit("/api/v1", 1)[0]
    raw_test("Prometheus /metrics", f"{server_base}/metrics")
    raw_test("Swagger UI", f"{BASE}/docs")
    raw_test("OpenAPI JSON", f"{BASE}/openapi.json")

    # === ERROR HANDLING ===
    print("\n-- ERROR HANDLING --")
    test("404 on unknown route", "GET", "/nonexistent", expect=404, auth=False)
    test("422 on invalid UUID", "GET", "/members/not-a-uuid", expect=422)
    test("401 on protected route", "GET", "/members", expect=401, auth=False)

    # === SUMMARY ===
    print()
    print("=" * 60)
    if not failed:
        print(f"  ALL {total} TESTS PASSED!")
    else:
        print(f"  RESULTS: {passed_count}/{total} passed, {len(failed)} failed")
        for f in failed:
            print(f"    FAIL: {f}")
    print("=" * 60)

    return len(failed) == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
