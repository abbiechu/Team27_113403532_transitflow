# TransitFlow Database Design Document

**Author:** irischue1218-code  
**Date:** 2026-05-29 (Updated: 2026-06-11)  
**Branch:** feature/design-document  
**Project:** TransitFlow — Intelligent Rail Assistant  

---

## Table of Contents

1. [Entity-Relationship Diagram](#1-entity-relationship-diagram)
2. [Normalisation Justification](#2-normalisation-justification)
3. [Graph Database Design Rationale](#3-graph-database-design-rationale)
4. [Vector / RAG Design](#4-vector--rag-design)
5. [AI Tool Usage Evidence](#5-ai-tool-usage-evidence)
6. [Reflection & Trade-offs](#6-reflection--trade-offs)

---

## 1. Entity-Relationship Diagram

### 1.1 ER Diagram

The diagram below was produced using dbdiagram.io. Cardinality notation follows crow's foot convention (`||--o{` = one-to-many, `||--||` = one-to-one, `|o--o|` = optional).

> **Note for markers:** A rendered version of this diagram is available at:  
> `https://dbdiagram.io/d/transitflow-schema` *(replace with your actual shared link before submission)*  
> The full DBML source is reproduced below so the schema can be verified without visiting the link.

```dbml
// dbdiagram.io source — paste at https://dbdiagram.io to render
// Schema matches databases/relational/schema.sql exactly.

Table users {
  // UUID chosen over SERIAL: user_id appears in auth tokens and API responses.
  // Sequential integers would allow enumeration attacks (IDOR); UUID prevents this.
  user_id         UUID         [pk, default: `gen_random_uuid()`]
  legacy_user_id  VARCHAR(10)  [unique, note: "e.g. RU01 — seeding compatibility only"]
  full_name       VARCHAR(100) [not null]
  email           VARCHAR(150) [unique, not null]
  password_hash   VARCHAR(255) [not null, note: "bcrypt hash, never plain text"]
  phone           VARCHAR(20)
  date_of_birth   DATE
  secret_question VARCHAR(255)
  secret_answer   VARCHAR(255) [note: "stored lowercase for case-insensitive comparison"]
  registered_at   TIMESTAMPTZ  [default: `now()`]
  // Soft delete: FALSE preserves booking history and financial audit trails
  is_active       BOOLEAN      [not null, default: true]
}

Table metro_stations {
  station_id                           VARCHAR(10) [pk]
  name                                 VARCHAR(100) [not null]
  is_interchange_metro                 BOOLEAN [not null, default: false]
  is_interchange_national_rail         BOOLEAN [not null, default: false]
  interchange_national_rail_station_id VARCHAR(10) [ref: > national_rail_stations.station_id,
                                        note: "ON DELETE SET NULL"]
}

Table metro_station_lines {
  station_id VARCHAR(10) [ref: > metro_stations.station_id, note: "ON DELETE CASCADE"]
  line       VARCHAR(10) [not null]

  indexes {
    (station_id, line) [pk]
  }
}

Table national_rail_stations {
  station_id                   VARCHAR(10) [pk]
  name                         VARCHAR(100) [not null]
  is_interchange_national_rail BOOLEAN [not null, default: false]
  is_interchange_metro         BOOLEAN [not null, default: false]
  interchange_metro_station_id VARCHAR(10) [ref: > metro_stations.station_id]
}

Table national_rail_station_lines {
  station_id VARCHAR(10) [ref: > national_rail_stations.station_id, note: "ON DELETE CASCADE"]
  line       VARCHAR(10) [not null]

  indexes {
    (station_id, line) [pk]
  }
}

Table metro_schedules {
  schedule_id            VARCHAR(20)  [pk]
  line                   VARCHAR(10)  [not null]
  direction              VARCHAR(20)  [not null]
  origin_station_id      VARCHAR(10)  [not null, ref: > metro_stations.station_id]
  destination_station_id VARCHAR(10)  [not null, ref: > metro_stations.station_id]
  first_train_time       TIME         [not null]
  last_train_time        TIME         [not null]
  base_fare_usd          NUMERIC(6,2) [not null]
  per_stop_rate_usd      NUMERIC(6,2) [not null]
  frequency_min          INTEGER      [not null]
}

Table metro_schedule_stops {
  // Junction table (3NF): stop_order depends on (schedule_id, station_id),
  // not on schedule_id alone — separating it removes the partial dependency.
  schedule_id                 VARCHAR(20) [ref: > metro_schedules.schedule_id, note: "ON DELETE CASCADE"]
  station_id                  VARCHAR(10) [ref: > metro_stations.station_id]
  stop_order                  INTEGER     [not null]
  travel_time_from_origin_min INTEGER     [not null, default: 0]

  indexes {
    (schedule_id, station_id) [pk]
  }
}

Table metro_schedule_days {
  schedule_id VARCHAR(20) [ref: > metro_schedules.schedule_id, note: "ON DELETE CASCADE"]
  day_of_week VARCHAR(10) [not null]

  indexes {
    (schedule_id, day_of_week) [pk]
  }
}

Table national_rail_schedules {
  schedule_id            VARCHAR(20) [pk]
  line                   VARCHAR(10) [not null]
  service_type           VARCHAR(20) [not null, note: "'normal' or 'express'"]
  direction              VARCHAR(20) [not null]
  origin_station_id      VARCHAR(10) [not null, ref: > national_rail_stations.station_id]
  destination_station_id VARCHAR(10) [not null, ref: > national_rail_stations.station_id]
  first_train_time       TIME        [not null]
  last_train_time        TIME        [not null]
  frequency_min          INTEGER     [not null]
}

Table national_rail_fare_classes {
  // One schedule has multiple fare classes (standard, first).
  // Storing fare info here avoids repeating it on every booking.
  schedule_id       VARCHAR(20)  [ref: > national_rail_schedules.schedule_id, note: "ON DELETE CASCADE"]
  fare_class        VARCHAR(20)  [not null, note: "'standard' or 'first'"]
  base_fare_usd     NUMERIC(6,2) [not null]
  per_stop_rate_usd NUMERIC(6,2) [not null]

  indexes {
    (schedule_id, fare_class) [pk]
  }
}

Table national_rail_schedule_stops {
  schedule_id                 VARCHAR(20) [ref: > national_rail_schedules.schedule_id, note: "ON DELETE CASCADE"]
  station_id                  VARCHAR(10) [ref: > national_rail_stations.station_id]
  stop_order                  INTEGER     [not null]
  travel_time_from_origin_min INTEGER     [not null, default: 0]
  // Express services pass through some stations without stopping
  is_passing_stop             BOOLEAN     [not null, default: false]

  indexes {
    (schedule_id, station_id) [pk]
  }
}

Table national_rail_schedule_days {
  schedule_id VARCHAR(20) [ref: > national_rail_schedules.schedule_id, note: "ON DELETE CASCADE"]
  day_of_week VARCHAR(10) [not null]

  indexes {
    (schedule_id, day_of_week) [pk]
  }
}

Table national_rail_seat_layouts {
  // Composite PK: seat_id alone is not globally unique across schedules
  seat_id     VARCHAR(10)  [not null]
  schedule_id VARCHAR(20)  [not null, ref: > national_rail_schedules.schedule_id, note: "ON DELETE CASCADE"]
  coach       VARCHAR(5)   [not null]
  fare_class  VARCHAR(20)  [not null]

  indexes {
    (seat_id, schedule_id) [pk]
  }
}

Table national_rail_bookings {
  // UUID: booking_id is customer-facing (receipts, cancellations).
  // Sequential integers would expose total booking volume and allow ID guessing.
  booking_id             UUID         [pk, default: `gen_random_uuid()`]
  legacy_booking_id      VARCHAR(10)  [unique, note: "e.g. BK001 — seeding compatibility"]
  user_id                UUID         [not null, ref: > users.user_id, note: "ON DELETE RESTRICT"]
  schedule_id            VARCHAR(20)  [not null, ref: > national_rail_schedules.schedule_id]
  origin_station_id      VARCHAR(10)  [not null, ref: > national_rail_stations.station_id]
  destination_station_id VARCHAR(10)  [not null, ref: > national_rail_stations.station_id]
  travel_date            DATE         [not null]
  departure_time         TIME         [not null]
  ticket_type            VARCHAR(20)  [not null, note: "'single' or 'return'"]
  fare_class             VARCHAR(20)  [not null]
  coach                  VARCHAR(5)
  seat_id                VARCHAR(10)
  stops_travelled        INTEGER      [not null]
  amount_usd             NUMERIC(8,2) [not null]
  status                 VARCHAR(20)  [not null, default: "confirmed",
                          note: "'confirmed' | 'completed' | 'cancelled'"]
  booked_at              TIMESTAMPTZ  [not null, default: `now()`]
  travelled_at           TIMESTAMPTZ
}

Table metro_trips {
  trip_id                UUID         [pk, default: `gen_random_uuid()`]
  legacy_trip_id         VARCHAR(10)  [unique]
  user_id                UUID         [not null, ref: > users.user_id, note: "ON DELETE RESTRICT"]
  schedule_id            VARCHAR(20)  [not null, ref: > metro_schedules.schedule_id]
  origin_station_id      VARCHAR(10)  [not null, ref: > metro_stations.station_id]
  destination_station_id VARCHAR(10)  [not null, ref: > metro_stations.station_id]
  travel_date            DATE         [not null]
  ticket_type            VARCHAR(20)  [not null, note: "'single' or 'day_pass'"]
  stops_travelled        INTEGER
  amount_usd             NUMERIC(8,2) [not null]
  status                 VARCHAR(20)  [not null, default: "confirmed"]
  travelled_at           TIMESTAMPTZ
}

Table payments {
  payment_id               UUID         [pk, default: `gen_random_uuid()`]
  legacy_payment_id        VARCHAR(10)  [unique]
  // Polymorphic FK: exactly one of the two FKs below is non-null.
  // CHECK constraint enforces this: (NR_booking IS NOT NULL AND metro IS NULL) OR vice versa.
  national_rail_booking_id UUID         [ref: > national_rail_bookings.booking_id,
                             note: "ON DELETE RESTRICT; XOR with metro_trip_id"]
  metro_trip_id            UUID         [ref: > metro_trips.trip_id, note: "ON DELETE RESTRICT"]
  amount_usd               NUMERIC(8,2) [not null]
  payment_method           VARCHAR(30)  [not null]
  status                   VARCHAR(20)  [not null, default: "completed"]
  paid_at                  TIMESTAMPTZ  [not null, default: `now()`]
}

Table feedback {
  feedback_id              UUID         [pk, default: `gen_random_uuid()`]
  legacy_feedback_id       VARCHAR(10)  [unique]
  user_id                  UUID         [not null, ref: > users.user_id]
  // Can reference a national rail booking OR a metro trip (same pattern as payments)
  national_rail_booking_id UUID         [ref: > national_rail_bookings.booking_id]
  metro_trip_id            UUID         [ref: > metro_trips.trip_id]
  rating                   INTEGER      [not null, note: "CHECK: 1–5"]
  comment                  TEXT
  submitted_at             TIMESTAMPTZ  [not null, default: `now()`]
}
```

### 1.2 Cardinality Summary

| Relationship | Cardinality | Notes |
|---|---|---|
| `users` → `national_rail_bookings` | 1 : N | One user has zero or many bookings |
| `users` → `metro_trips` | 1 : N | One user has zero or many metro trips |
| `national_rail_schedules` → `national_rail_schedule_stops` | 1 : N | One schedule has one or many stops |
| `metro_schedules` → `metro_schedule_stops` | 1 : N | One schedule has one or many stops |
| `national_rail_schedules` → `national_rail_fare_classes` | 1 : N | One schedule has one or many fare classes |
| `national_rail_schedules` → `national_rail_seat_layouts` | 1 : N | One schedule has one or many seats |
| `national_rail_schedules` → `national_rail_schedule_days` | 1 : N | One schedule operates on one or many days |
| `metro_schedules` → `metro_schedule_days` | 1 : N | One schedule operates on one or many days |
| `metro_stations` → `metro_station_lines` | 1 : N | One station can be on multiple lines |
| `national_rail_stations` → `national_rail_station_lines` | 1 : N | One station can be on multiple lines |
| `national_rail_bookings` → `payments` | 1 : 0..1 | One booking has at most one payment |
| `metro_trips` → `payments` | 1 : 0..1 | One trip has at most one payment |
| `national_rail_bookings` → `feedback` | 1 : 0..1 | One booking has at most one feedback entry |
| `metro_trips` → `feedback` | 1 : 0..1 | One trip has at most one feedback entry |
| `metro_stations` ↔ `national_rail_stations` | 0..1 : 0..1 | Optional interchange link (bidirectional FK) |

### 1.3 Key Tables Overview

**USERS** — Stores user profiles with bcrypt-hashed passwords (`password_hash VARCHAR(255)`). `legacy_user_id` (e.g., `RU01`) maintained for seeding compatibility. `is_active` implements soft delete. `secret_question` and `secret_answer` support the password-reset flow; the answer is stored in lowercase to enable case-insensitive comparison in `verify_secret_answer()`.

**METRO_STATIONS & NATIONAL_RAIL_STATIONS** — Separate tables because the two network types have different domain-specific properties. Station lines are in separate junction tables (`metro_station_lines`, `national_rail_station_lines`) rather than array columns, enabling indexed lookups by line. `interchange_*_station_id` FKs capture cross-network connection points.

**METRO_SCHEDULES & NATIONAL_RAIL_SCHEDULES** — Separate because their operating models differ fundamentally. Metro stores `base_fare_usd` and `per_stop_rate_usd` directly on the schedule (all seats are equal). National rail stores fares in a separate `national_rail_fare_classes` table because different fare classes (standard, first) have different rates on the same schedule.

**SCHEDULE_STOPS tables** — Normalised junction tables (3NF). Each stop row stores `stop_order` and `travel_time_from_origin_min`. National rail stops also carry `is_passing_stop = TRUE` for stations that express services pass through without stopping — this flag is checked in `query_national_rail_availability` to exclude passing stops from the join.

**NATIONAL_RAIL_SEAT_LAYOUTS** — Composite PK of `(seat_id, schedule_id)` because `seat_id` values (e.g., `A1`) repeat across different schedules. Maps each seat to its coach and fare class for availability checking and booking.

**NATIONAL_RAIL_BOOKINGS** — Status lifecycle: `confirmed → completed` or `confirmed → cancelled`. Stores `stops_travelled` at booking time (denormalised from stop order difference) to avoid recalculating it during cancellation refund computation.

**METRO_TRIPS** — No `seat_id` or `coach` fields (pay-as-you-go, no seat assignment). No cancellation workflow. The `status` field records whether the trip was completed or is pending.

**PAYMENTS** — Unified table with polymorphic FKs. The `CONSTRAINT payment_one_booking CHECK (...)` in `schema.sql` enforces that exactly one of `national_rail_booking_id` and `metro_trip_id` is non-null at the database level — this cannot be violated even by direct SQL inserts.

---

## 2. Normalisation Justification

### 2.1 Third Normal Form (3NF): Schedule Stops as Junction Tables

The most consequential normalisation decision is separating schedule stops into their own tables (`metro_schedule_stops`, `national_rail_schedule_stops`) rather than storing them as array columns or a flattened row.

**The functional dependency that motivates this:**

In an unnormalised design:

```
metro_schedules row:
  schedule_id | line | direction | stop1_id | stop1_time | stop2_id | stop2_time | ...
```

Here `stop1_time` depends on `(schedule_id, stop1_id)` — a subset of the hypothetical composite key — not on `schedule_id` alone. This is a **partial dependency**, which violates **2NF**. Extending the reasoning: if we add a composite PK of `(schedule_id, station_id)`, then `line` and `direction` depend only on `schedule_id`, not on the full composite key. This transitive dependency violates **3NF**.

The normalised design removes both violations:

```
metro_schedules:       schedule_id → line, direction, first_train_time, base_fare_usd, ...
metro_schedule_stops:  (schedule_id, station_id) → stop_order, travel_time_from_origin_min
```

Every non-key attribute in each table now depends on the **whole** primary key and **only** the primary key — satisfying 3NF. In practice:
- Schedule attributes (`line`, `direction`) are stored once, not repeated per stop.
- Adding a stop requires inserting one row, not altering the schema.
- The query `WHERE station_id = 'MS05'` across `metro_schedule_stops` can be indexed efficiently.

The same reasoning applies to `national_rail_schedule_stops`, which additionally carries `is_passing_stop` — a stop-level attribute that would be impossible to represent cleanly in a flattened schema.

**Lines as a separate junction table:** Station lines (which metro lines serve MS01, etc.) are also extracted into `metro_station_lines` and `national_rail_station_lines` rather than stored as `TEXT[]` array columns on the station tables. An array column is non-atomic (violates 1NF in the relational sense) and prevents indexed lookups of the form `WHERE 'M1' = ANY(lines)`. The junction table approach allows `WHERE line = 'M1'` with a standard B-tree index.

### 2.2 Deliberate De-normalisation: `stops_travelled` on Bookings

One deliberate deviation from strict normalisation is storing `stops_travelled` directly on `national_rail_bookings`. This value could be computed at query time from `national_rail_schedule_stops` (destination stop_order minus origin stop_order).

It is stored on the booking because:
1. `execute_cancellation()` uses `stops_travelled` to calculate the refund amount — recomputing it would require a JOIN to `national_rail_schedule_stops` inside the cancellation transaction, adding complexity.
2. It captures the value at booking time. If a schedule is modified after booking, the stored `stops_travelled` still reflects what the passenger paid for.

The trade-off is one extra integer per booking row. Given that booking rows are small and this value is read-heavy (refund calculation), the storage cost is negligible compared to the query simplification.

### 2.3 Deliberate De-normalisation: Unified Payments Table

The `payments` table contains two nullable foreign keys (`national_rail_booking_id` and `metro_trip_id`), with exactly one non-null enforced by a `CHECK` constraint. A strictly 3NF design would create two separate payment tables.

We kept a single table because:
- Both transaction types share identical payment attributes (`amount_usd`, `payment_method`, `status`, `paid_at`).
- `query_user_bookings()` retrieves all payment history with queries against a single table and one index on `user_id`.
- The `CHECK` constraint (`CONSTRAINT payment_one_booking CHECK (...)` in `schema.sql`) enforces the business rule at the database level — the nullable columns do not introduce ambiguity.

### 2.4 Password Hashing: Algorithm, Rationale, and Salt

**Algorithm chosen: bcrypt**

All user passwords are hashed with **bcrypt** before storage. `register_user()` in `databases/relational/queries.py` calls:

```python
password_hash = bcrypt.hashpw(
    password.encode("utf-8"), bcrypt.gensalt()
).decode("utf-8")
```

The bcrypt output string (e.g., `$2b$12$...`) embeds the algorithm identifier, cost factor, salt, and hash — it is entirely self-describing. `login_user()` verifies with `bcrypt.checkpw(input_password.encode(), stored_hash.encode())`. The hash is deleted from the returned dict before it is returned to the application layer, so it is never exposed.

**Why bcrypt instead of MD5 or SHA-256:**

MD5 and SHA-256 are general-purpose hash functions designed to be *fast* — a modern GPU can compute billions of SHA-256 hashes per second. This makes them unsuitable for passwords: an attacker who obtains the hash database can brute-force billions of candidates per second.

bcrypt is a **key-derivation function** (KDF) with a configurable **cost factor** (work factor). Increasing the cost factor by 1 doubles computation time. At the default of 12 rounds, one bcrypt hash takes ~250 ms on a modern CPU — fast enough for legitimate login (one hash per attempt) but orders of magnitude slower for brute-force attacks.

Alternative modern KDFs — **argon2id** and **scrypt** — are also acceptable. Argon2id is the current OWASP recommendation because it adds *memory-hardness* (requiring large amounts of RAM per computation), making GPU and ASIC attacks harder. For this project, bcrypt was chosen because the `bcrypt` Python library was already a project dependency and its security properties are well-understood for web applications.

**Note on cost factor in seeding vs production:** `seed_postgres.py` uses `bcrypt.gensalt(rounds=4)` rather than the default `rounds=12`. This is intentional — seeding 20 users at cost factor 12 would take ~6 seconds; `rounds=4` completes in under a second. The comment in `seed_postgres.py` documents this: *"rounds=4 speeds up seeding significantly while still hashing correctly."* In production, new registrations via `register_user()` use `bcrypt.gensalt()` (default rounds=12).

**How salt prevents rainbow-table attacks:**

A **salt** is a random value generated uniquely per password before hashing. bcrypt generates a 128-bit random salt internally and embeds it in the output string. Two users with the same password produce completely different hashes:

```
User A:  bcrypt("password123", salt_A) → $2b$12$xK9p...abc
User B:  bcrypt("password123", salt_B) → $2b$12$mN3q...xyz
```

A **rainbow table** is a precomputed lookup table mapping common passwords to their hashes. Without per-user salt, an attacker could instantly find "password123" in the table. With a unique 128-bit salt, building a rainbow table would require one precomputed table per possible salt value — a 2¹²⁸ space that is computationally infeasible to enumerate.

### 2.5 Transactional Integrity: `execute_booking` Atomicity

The booking creation function (`execute_booking()` in `databases/relational/queries.py`) inserts both a booking record and a payment record as a single atomic operation:

```python
conn = psycopg2.connect(PG_DSN)
conn.autocommit = False          # explicit transaction — no auto-commit
try:
    with conn.cursor(...) as cur:
        # ... seat check, fare lookup ...
        cur.execute("INSERT INTO national_rail_bookings ...")
        cur.execute("INSERT INTO payments ...")  # same transaction
        conn.commit()                            # both committed together
except Exception as e:
    conn.rollback()              # neither row persists if either fails
    return False, f"Booking failed: {str(e)}"
finally:
    conn.close()
```

The connection is opened with `autocommit = False` (as opposed to the `_connect()` helper which uses `autocommit = True` for read-only queries). This means both INSERT statements are part of a single transaction. If the payment insert fails for any reason, `conn.rollback()` in the `except` block removes the booking insert as well — leaving no orphaned booking without a payment record. This satisfies the ACID **atomicity** requirement: the operation either fully succeeds or fully fails with no partial state.

---

## 3. Graph Database Design Rationale

### 3.1 What Data Is Stored as Nodes, Relationships, and Properties — and Why

**Nodes** represent entities with independent identity that routing algorithms need to visit, start from, or end at. In TransitFlow, `MetroStation` and `NationalRailStation` nodes map directly to physical locations. A station is a node (not a row in an intermediate table) because Dijkstra and BFS algorithms operate on *nodes* — they visit nodes, accumulate cost along edges, and terminate when a target node is reached. If stations were rows in a relational table, the algorithm would need to be simulated in SQL, not natively executed by the graph engine.

**Relationships** represent physical connections that make travel between two adjacent stations possible in one leg:
- `METRO_LINK` — directed metro track segment between adjacent metro stations on a given line.
- `RAIL_LINK` — directed national rail segment between adjacent rail stations.
- `INTERCHANGE_TO` — walking transfer connection between a metro station and a rail station at the same physical interchange point.

Connections are *relationships* (not nodes) because they are the traversal medium — the routing algorithm moves *along* relationships to accumulate cost. Modelling connections as nodes (an intermediate "link" entity) would double the number of hops per leg and complicate every routing query.

**Properties** store attributes used for filtering or as edge weights:
- `station_id` (node) — the merge key for idempotent seeding and the MATCH parameter in every routing query.
- `travel_time_min` (METRO_LINK, RAIL_LINK) — the primary edge weight for `query_shortest_route` (APOC Dijkstra minimises this).
- `standard_fare_usd`, `first_fare_usd` (RAIL_LINK); `per_stop_rate_usd` (METRO_LINK) — edge weights for `query_cheapest_route`; fare class selects which property to minimise.
- `transfer_time_min` (INTERCHANGE_TO) — fixed at 5 minutes; accumulated alongside `travel_time_min` in `query_interchange_path` via `coalesce(r.travel_time_min, r.transfer_time_min, 0)`.

### 3.2 Node Identity: `station_id` as Unique Identifier

Each node uses `station_id` (e.g., `MS01`, `NR05`) as its identity property. The seeder uses:

```python
session.run(
    "MERGE (n:MetroStation {station_id: $station_id}) SET n.name = $name, ...",
    station_id=s["station_id"], ...
)
```

`MERGE` on `station_id` means the property acts as an effective primary key — a node is created only if one with that ID does not already exist, making the seeder idempotent. `station_id` was chosen because:

1. **Human-readable:** Station IDs appear directly in user queries and API parameters. Using them as node identifiers avoids a translation step between user input and graph lookup.
2. **Stable:** Names can be renamed; IDs are fixed in the source JSON. Using `name` as identity would require updating all relationships if a station is renamed.
3. **Network-prefixed:** `MS*` always identifies a `MetroStation`; `NR*` always a `NationalRailStation`. The helper function `_infer_label(station_id)` in `queries.py` exploits this convention:

```python
def _infer_label(station_id: str) -> str:
    if station_id.upper().startswith("MS"):
        return "MetroStation"
    return "NationalRailStation"
```

This eliminates the need to pass a `network` parameter for most routing queries — the label is inferred automatically from the ID prefix.

### 3.3 Why Graph > SQL for Routing: Concrete Algorithmic Argument

The core argument is algorithmic. Route-finding requires **graph traversal algorithms** (Dijkstra for weighted shortest paths, BFS for ripple analysis) that operate naturally on a graph structure. Implementing them in SQL requires recursive CTEs that simulate graph traversal — verbose, error-prone, and significantly slower.

**Concrete comparison — weighted shortest path:**

SQL (Recursive CTE):
```sql
WITH RECURSIVE paths AS (
  SELECT from_id, to_id, travel_time, 1 AS hops,
         ARRAY[from_id, to_id] AS visited
  FROM metro_links WHERE from_id = 'MS01'
  UNION ALL
  SELECT p.from_id, ml.to_id, p.travel_time + ml.travel_time,
         p.hops + 1, p.visited || ml.to_id
  FROM paths p
  JOIN metro_links ml ON p.to_id = ml.from_id
  WHERE p.hops < 15 AND NOT ml.to_id = ANY(p.visited)
)
SELECT * FROM paths WHERE to_id = 'MS09'
ORDER BY travel_time LIMIT 1;
```

~15 lines. Manual cycle detection (`NOT ... = ANY(p.visited)`). Worst-case **O(n²)** because all partial paths are materialised at each recursive step.

Neo4j (APOC Dijkstra):
```cypher
MATCH (start:MetroStation {station_id: 'MS01'})
MATCH (end:MetroStation   {station_id: 'MS09'})
CALL apoc.algo.dijkstra(start, end, 'METRO_LINK', 'travel_time_min')
YIELD path, weight
RETURN path, weight AS total_time_min
```

4 lines. Cycle detection handled internally. **O((V + E) log V)** — significantly faster on dense transit networks.

**Additional operations compared:**

| Operation | SQL | Neo4j |
|---|---|---|
| Avoid a specific station | Rewrite the entire CTE with a `NOT IN` subquery | Add `WHERE NONE(n IN nodes(path) WHERE n.station_id = $avoid_id)` |
| Cross-network path (metro + rail) | UNION across three tables with recursive CTEs per segment | `shortestPath` with `[:METRO_LINK\|INTERCHANGE_TO\|RAIL_LINK*]` |
| Delay ripple (stations within N hops) | Recursive CTE with explicit depth counter | `MATCH (start)-[*1..$hops]->(affected)` — one line |

### 3.4 Two Query Types Enabled by the Graph Model

**Query type 1: Weighted shortest path (`query_shortest_route`, `query_cheapest_route`)**

Both functions use `apoc.algo.dijkstra`, which reads edge weight properties directly during traversal:

```cypher
// query_shortest_route — minimise travel_time_min
CALL apoc.algo.dijkstra(start, end, 'METRO_LINK', 'travel_time_min')
YIELD path, weight

// query_cheapest_route — minimise standard_fare_usd or first_fare_usd
// fare_prop is selected in Python based on the fare_class parameter
CALL apoc.algo.dijkstra(start, end, 'RAIL_LINK', 'standard_fare_usd')
YIELD path, weight
```

The graph model enables this because edge weights are first-class properties on relationships. SQL has no native equivalent — it must simulate weight accumulation with a `SUM` column in a recursive CTE.

**Query type 2: Cross-network interchange routing (`query_interchange_path`)**

```cypher
MATCH path = shortestPath(
    (start:MetroStation {station_id: $origin_id})
    -[:METRO_LINK|INTERCHANGE_TO|RAIL_LINK*..20]->
    (end:NationalRailStation {station_id: $destination_id})
)
WITH path,
     reduce(t = 0, r IN relationships(path) |
         t + coalesce(r.travel_time_min, r.transfer_time_min, 0)
     ) AS total_time
```

The graph model enables this in a single query because `INTERCHANGE_TO` relationships directly connect `MetroStation` nodes to `NationalRailStation` nodes. The pipe operator `|` in the relationship pattern allows traversal across all three relationship types in one path expression. In SQL, this would require joining the metro link table, the interchange table, and the rail link table, with separate recursive CTEs for each network segment.

### 3.5 Graph Schema: Node and Relationship Properties

Node properties as implemented in `seed_neo4j.py`:

```
MetroStation:         station_id, name, lines[], is_interchange_metro, is_interchange_national_rail
NationalRailStation:  station_id, name, lines[], is_interchange_metro, is_interchange_national_rail
```

Relationship properties:
```
METRO_LINK:     line, travel_time_min, base_fare_usd (0.80), per_stop_rate_usd (0.30)
RAIL_LINK:      line, travel_time_min, standard_fare_usd (1.50), first_fare_usd (2.50)
INTERCHANGE_TO: transfer_time_min (5, fixed)
```

**Why two directed INTERCHANGE_TO edges per interchange pair:**
Neo4j relationships are always directed. The seeder creates both directions:
```python
# metro → rail
MERGE (m)-[x:INTERCHANGE_TO]->(r) SET x.transfer_time_min = 5
# rail → metro
MERGE (r)-[x:INTERCHANGE_TO]->(m) SET x.transfer_time_min = 5
```
This allows `shortestPath` to traverse the interchange regardless of travel direction without requiring `<-[:INTERCHANGE_TO]->` bidirectional syntax in every query.

---

## 4. Vector / RAG Design

### 4.1 What Is Embedded and Why Cosine Similarity Is Appropriate

**What is embedded:** Each entry in the four policy JSON files (`refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json`) is converted to a vector embedding and stored in `policy_documents`. The full content field of each entry (serialised as JSON) is embedded, not just the title — the full text contains the semantic information the query needs to match against.

`seed_vectors.py` builds one document per policy entry:

```python
docs.append({
    "title": policy["label"],
    "category": "refund",
    "source_file": "refund_policy.json",
    "content": json.dumps(policy, indent=2),  # full policy text as content
})
```

**Why cosine similarity:**

Cosine similarity measures the *angle* between two vectors in the embedding space, regardless of their *magnitude*. This is the correct metric for text embeddings for two reasons:

1. **Magnitude independence:** An embedding model may produce vectors with different magnitudes for short titles versus long policy paragraphs, even when they describe the same topic. Cosine similarity is unaffected by vector length — it normalises both vectors to unit length before computing the dot product, so only the *direction* matters. Euclidean distance would penalise longer texts purely because their vectors have larger magnitude, producing irrelevant results.

2. **Semantic direction:** Embedding models are trained so that texts with similar *meaning* produce vectors that point in similar *directions* in the high-dimensional space. The cosine of the angle between two such vectors quantifies directional similarity. A cosine similarity close to 1.0 means nearly the same semantic direction (highly relevant); near 0 means orthogonal (unrelated).

In pgvector, the `<=>` operator computes cosine *distance* (1 − cosine similarity). `query_policy_vector_search()` sorts ascending by distance so the most semantically similar policies are returned first:

```python
# from databases/relational/queries.py
sql = """
    SELECT title, category, content,
           1 - (embedding <=> %s::vector) AS similarity
    FROM policy_documents
    WHERE 1 - (embedding <=> %s::vector) > %s   -- VECTOR_SIMILARITY_THRESHOLD
    ORDER BY embedding <=> %s::vector
    LIMIT %s                                      -- VECTOR_TOP_K
"""
```

The threshold (`VECTOR_SIMILARITY_THRESHOLD`) and top-k limit (`VECTOR_TOP_K`) are read from `skeleton/config.py`, keeping them configurable without code changes.

### 4.2 The Full RAG Pipeline

**Stage 1 — Query embedding:** When the user asks a policy question, the question text is passed to the same embedding model used during seeding — `nomic-embed-text` for Ollama (768 dimensions) or `text-embedding-004` for Gemini (3072 dimensions) — via `llm.embed(query)`. The result is a float vector of the same dimension as stored embeddings.

**Stage 2 — Similarity search:** The query vector is sent to PostgreSQL as a parameter. `query_policy_vector_search(embedding)` executes the cosine distance search and returns the top-K matching documents above the similarity threshold. The HNSW index (`policy_documents_embedding_idx`) navigates a hierarchical graph structure to find approximate nearest neighbours in sub-linear time — without it, the search would perform a full table scan.

**Stage 3 — Retrieved documents passed to LLM:** The top-K matching policy texts are concatenated and injected into the LLM's system prompt as context by `skeleton/agent.py`. The LLM never sees the vectors — only the text content. The agent's `_normalise_result` function formats them as key-value text.

**Stage 4 — Answer generation:** The LLM reads the original question alongside the retrieved policy context and generates a natural-language answer grounded in the retrieved documents. Because the answer is constructed from actual policy text, it cannot contradict the stored policy — unlike a plain LLM response which may hallucinate policy details.

### 4.3 Embedding Dimension Choice and Provider-Switch Risk

**Dimension in use:** This implementation uses **768 dimensions** (Ollama `nomic-embed-text`). The `policy_documents` table is defined as `embedding vector(768)` in `schema.sql`.

**What happens if the provider is switched after seeding:**

Vectors stored by Ollama (768 dimensions) are not comparable with vectors generated by Gemini (3072 dimensions). They live in entirely different vector spaces with different axis counts. If the database is seeded with Ollama and a query is issued using a Gemini embedding, the `<=>` operator raises:

```
ERROR: expected 768 dimensions, not 3072
```

The policy search fails entirely until the database is reseeded. Additionally, even if dimensions matched by coincidence (two different 768-dim models), the geometric relationships would differ — cosine similarity scores would be meaningless because the axes have different semantic interpretations.

**To fix a provider switch:**
1. Update `schema.sql`: change `vector(768)` → `vector(3072)` for Gemini.
2. Reset: `docker compose down -v && docker compose up -d`.
3. Re-seed: `python skeleton/seed_vectors.py` (regenerates all embeddings with the new model).

### 4.4 Why pgvector Over Full-Text Search

Full-text search (`LIKE '%delay%'` or PostgreSQL `tsvector`) matches on keywords. If the policy says "compensation for late services" and the user asks "refund for a delayed train", keyword search returns nothing — "late" ≠ "delayed" at the character level.

Vector search matches on **meaning**. The embedding model has learned that "delay", "late arrival", and "service disruption" occupy nearby regions of the vector space. A query about "delayed train" retrieves documents about "late services" because their vectors are geometrically close — regardless of the specific words used.

---

## 5. AI Tool Usage Evidence

The following examples document how AI tools (Claude) were used during development. Each includes **Context** (what was being attempted), **Prompt** (what was asked), and **Outcome** (what happened and any corrections required).

---

### Example 1 — Schema design: normalising schedule stops

**Context:** During initial schema design, the question arose whether stop sequences should be stored as a `TEXT[]` array column on the schedules table or as a separate junction table. The normalisation implications were unclear.

**Prompt:**
> "I'm designing a PostgreSQL schema for a transit system. Each metro schedule has a list of stops in order. Should I store them as an array column on the schedules table, or create a separate schedule_stops junction table with a stop_order column? What are the normalisation implications?"

**Outcome:** The AI correctly explained that storing stops as an array violates 1NF (non-atomic values) and prevents indexed lookups such as `WHERE station_id = 'MS05'`. It recommended the junction table approach with `(schedule_id, station_id)` as the composite PK and `stop_order` as a non-key attribute. This was applied directly: `metro_schedule_stops` and `national_rail_schedule_stops` in `schema.sql` both use this design. The AI's explanation was accurate and needed no correction.

---

### Example 2 — Password hashing: bcrypt vs argon2id (AI needed correction)

**Context:** The schema required hashed password storage. The choice between bcrypt, argon2id, and scrypt was not immediately clear.

**Prompt:**
> "For a Python web application storing user passwords, should I use bcrypt, argon2id, or scrypt? What are the practical differences in terms of resistance to GPU attacks and ease of implementation in Python?"

**Outcome:** The AI correctly identified argon2id as the current OWASP recommendation due to its memory-hardness, and explained that bcrypt lacks memory-hardness, making it more susceptible to GPU attacks. However, it suggested `argon2-cffi` as the implementation library without noting that `bcrypt` was already a dependency in this project's `requirements.txt`. The AI's recommendation was technically sound but impractical given the project constraints. The decision was made to use bcrypt with `rounds=12` in production (via `bcrypt.gensalt()` default) and `rounds=4` in seeding (via `bcrypt.gensalt(rounds=4)`) for speed. This example demonstrates that AI tool suggestions require validation against actual project dependencies and constraints.

---

### Example 3 — Cypher syntax for cross-network routing (AI output required adjustment)

**Context:** Implementing `query_interchange_path()` required a Cypher query traversing three relationship types in sequence (METRO_LINK → INTERCHANGE_TO → RAIL_LINK). The correct syntax was unfamiliar.

**Prompt:**
> "In Neo4j, I have MetroStation nodes connected by METRO_LINK, NationalRailStation nodes connected by RAIL_LINK, and INTERCHANGE_TO edges connecting the two node types. How do I write a shortestPath query that finds the path from a MetroStation to a NationalRailStation, crossing the interchange in between?"

**Outcome:** The AI correctly provided the pipe-operator syntax:
```cypher
MATCH path = shortestPath(
  (start:MetroStation {station_id: $from})
  -[:METRO_LINK|INTERCHANGE_TO|RAIL_LINK*..20]->
  (end:NationalRailStation {station_id: $to})
)
RETURN path
```
However, the example returned only `path` without computing `total_time_min`. During testing, the agent's normaliser expected a `total_time_min` field in the return dict. The query was manually corrected to add:
```cypher
WITH path,
     reduce(t = 0, r IN relationships(path) |
         t + coalesce(r.travel_time_min, r.transfer_time_min, 0)
     ) AS total_time
RETURN ... total_time AS total_time_min
```
The structural suggestion was correct; the return shape required manual adjustment to match the agent contract.

---

### Example 4 — Debugging `execute_booking` atomicity

**Context:** During testing, a scenario was constructed where the payment INSERT inside `execute_booking()` was made to fail artificially. The booking row was found in the database even though the payment insert had failed — the function had returned `(False, ...)` but left an orphaned booking.

**Prompt:**
> "In Python with psycopg2, I have a function that inserts a booking row and then a payment row. If the payment insert fails, the booking row still ends up in the database. How do I make both inserts atomic so that if either fails, neither is committed?"

**Outcome:** The AI correctly identified that the issue was `conn.autocommit = True` (used by the `_connect()` helper for read-only queries). It explained that autocommit commits each statement immediately, so there is no rollback possible for the booking insert after the payment fails. The fix was to open a new connection with `conn.autocommit = False`, wrap both inserts in a `try/except`, call `conn.commit()` after both succeed, and `conn.rollback()` in the except block. This is exactly the pattern now in `execute_booking()`:

```python
conn = psycopg2.connect(PG_DSN)
conn.autocommit = False
try:
    ...
    cur.execute("INSERT INTO national_rail_bookings ...")
    cur.execute("INSERT INTO payments ...")
    conn.commit()
except Exception as e:
    conn.rollback()
    return False, f"Booking failed: {str(e)}"
finally:
    conn.close()
```

The AI's explanation was accurate and directly resolved the atomicity gap.

---

### Example 5 — AI output that was wrong: cosine similarity threshold

**Context:** Implementing `query_policy_vector_search()`, a threshold was needed below which results should be excluded to avoid returning irrelevant policies.

**Prompt:**
> "In pgvector cosine similarity search for a RAG application, what threshold should I use to filter out low-relevance results? Should I use 0.5, 0.7, or something else?"

**Outcome:** The AI recommended 0.7 as "generally good practice for semantic search". This was **incorrect** for this implementation. When tested with `nomic-embed-text` (the Ollama embedding model), a threshold of 0.7 excluded correct matches — queries like "can I bring my bicycle on the train?" returned empty results even though `travel_policies.json` contained a bicycle policy section. The model produces lower raw similarity scores than the OpenAI models the AI appeared calibrated toward. After empirical testing across 15 sample queries, the threshold was set to 0.5 (now stored as `VECTOR_SIMILARITY_THRESHOLD` in `skeleton/config.py`). This example demonstrates that numerical thresholds recommended by AI tools are model-dependent and must be validated empirically — there is no universal constant.

---

## 6. Reflection & Trade-offs

### 6.1 Two Specific Design Decisions

**Decision 1: UUID as primary key for bookings and users (not SERIAL)**

All primary keys in `users`, `national_rail_bookings`, `metro_trips`, and `payments` use `UUID DEFAULT gen_random_uuid()` rather than integer `SERIAL`. The comments in `schema.sql` document the rationale:

> *"UUID chosen over SERIAL: user_id appears in auth tokens and API responses. Sequential integers would allow enumeration attacks (IDOR); UUID prevents this."*
> *"UUID chosen: booking_id is customer-facing. Sequential integers would expose total booking volume and allow ID guessing."*

The security argument is the primary motivation: sequential integers allow an attacker to iterate over valid IDs by incrementing. A booking cancellation endpoint that accepts `booking_id` would be trivially exploitable with SERIAL PKs. UUIDs generated by `gen_random_uuid()` are cryptographically random and cannot be guessed.

The trade-off is that UUIDs are 128 bits (vs 32 bits for INTEGER), making index entries larger and JOIN operations slightly slower. `legacy_user_id` and `legacy_booking_id` columns (e.g., `RU01`, `BK001`) are retained as `VARCHAR(10) UNIQUE` columns for seeding compatibility, but the production PK is always UUID.

**Decision 2: Separate `national_rail_fare_classes` table (not fare columns on the schedule)**

National rail fare information is stored in a separate `national_rail_fare_classes` table with a composite PK of `(schedule_id, fare_class)`, rather than adding `standard_base_fare`, `standard_per_stop`, `first_base_fare`, `first_per_stop` columns directly to `national_rail_schedules`.

The functional dependency argument: `base_fare_usd` is functionally dependent on `(schedule_id, fare_class)`, not on `schedule_id` alone. Storing fare data as columns on the schedule table would be a partial dependency violation (2NF). It would also make adding a new fare class (e.g., `business`) require a schema change (ALTER TABLE ADD COLUMN), whereas the junction table approach requires only a new row.

Metro schedules do not use this pattern — fare data (`base_fare_usd`, `per_stop_rate_usd`) is stored directly on `metro_schedules` — because metro has a single undifferentiated fare structure with no fare classes. This asymmetry is documented in the `schema.sql` comments.

### 6.2 One Aspect That Would Be Different in a Production System

**Connection pooling instead of per-request connections**

Every query function in `databases/relational/queries.py` opens a new psycopg2 connection via `_connect()` and closes it at the end of the function. This is workable for a single-user development environment but would fail under production load.

Opening a TCP connection to PostgreSQL is expensive: it involves a network handshake, authentication, and process forking on the PostgreSQL side. At 100 concurrent users, the application would attempt to open 100 simultaneous connections — PostgreSQL's default `max_connections` limit is 100, so the 101st request would receive `FATAL: sorry, too many clients already`.

In production, a **connection pool** such as **PgBouncer** (an external pool proxy) or **psycopg2's built-in pool** maintains a fixed number of long-lived connections that are reused across requests:

```python
# Production pattern: initialise once at startup
from psycopg2 import pool
connection_pool = pool.ThreadedConnectionPool(
    minconn=5, maxconn=20, dsn=PG_DSN
)

def _connect():
    return connection_pool.getconn()  # borrows from pool, doesn't open a new connection
```
