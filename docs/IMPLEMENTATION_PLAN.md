# Implementation Plan

## Task 1 — Repo skeleton (branch `nms/topology-v1`)
Create folders: `services/topo-normalizer`, `services/api`, `services/ui`, `inventory/`. Add the compose file.

**Acceptance:** `docker compose up` brings all containers up (api 200 on `/healthz`).

---

## Task 2 — DB migrations
Implement SQL DDL in `services/api/migrations/0001_init.sql` for tables & views in ARCHITECTURE.md §2.

**Acceptance:** tables exist; `edges` has indexes; migrations idempotent.

---

## Task 3 — SuzieQ integration
Place `inventory/sq.yaml` and `inventory/devices.yaml` (SSH creds via Docker secrets). Enable periodic `suzieq poll`.

**Acceptance:** `facts_*` JSON dumps appear in a shared volume; `suzieq-cli show ...` works inside container.

---

## Task 4 — Normalizer
Build a Python service that reads SuzieQ parquet/JSON, writes to `facts_*`, and computes `edges` with scoring (ARCHITECTURE.md §3).

**Acceptance:** After two polling cycles, `edges` shows lldp/cdp (if present) and mac_arp edges with `first_seen/last_seen` advancing.

---

## Task 5 — Canonical links view
Materialized view `vw_links_canonical` that picks highest-score edge per link.

**Acceptance:** A query returns one row per physical link; ties broken per rule.

---

## Task 6 — API endpoints
Implement `/topology/nodes`, `/topology/edges`, `/topology/path`, `/topology/impact` (see ARCHITECTURE.md §5).

**Acceptance:** Swagger/OpenAPI served at `/`.

---

## Task 7 — UI with ELK auto-layout
Build React UI; use **elkjs** to compute layout; render nodes/edges with badges.

**Acceptance:** Map renders for ~100 nodes in <1s on dev laptop; filter by site/role.

---

## Task 8 — Port drill-down
Panel for a selected interface: admin/oper, speed, VLANs, MACs/hosts, upstream/downstream edges, evidence snippets.

**Acceptance:** Click on edge → right panel shows evidence JSON (pretty-printed).

---

## Task 9 — Path query UX
Form: choose endpoints (device/port or device/IP). Results: hop list + edge methods.

**Acceptance:** Known path across your lab renders correctly; changing VLAN filters changes L2 path.

---

## Task 10 — Impact analysis
Given `(device|port)`, perform downstream traversal on `vw_links_canonical` and show likely affected hosts (MAC/ARP).

**Acceptance:** Unplugging an access switch in lab makes its subtree appear under impact in next poll.

---

## Task 11 — Optional sFlow
If enabled, consume sFlow-RT REST to annotate edges with recent utilization and confirm A→B path.

**Acceptance:** UI shows "flow corroborated" badge when live traffic matches path.

---

## Task 12 — Optional NetBox sync
Implement `/adapters/netbox/push` to upsert devices/cables (no PRTG).

**Acceptance:** NetBox shows cables identical to `vw_links_canonical` for selected site.

---

## Task 13 — Hardening

* SSH creds as secrets; least privilege.
* Limit polling concurrency; backoff on failures.
* Health checks & structured logs.

**Acceptance:** All services pass `/healthz`; restart-safe.

---

## Task 14 — CI smoke tests
Fixture JSON → expected edges → expected path.

**Acceptance:** `make test` passes end-to-end.

---

## Task 15 — Runbook
Write `docs/troubleshooting.md` with "Find A→B path", "Who is on port X?", "What's impacted if Y fails?".
