# AI Session Context — TransitFlow

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits your codebase exactly.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like a team contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a fictional dual-network transit operator. It queries three databases — PostgreSQL (relational + vector), Neo4j (graph) — and uses an LLM (Gemini or Ollama) to answer natural language user questions about schedules, fares, bookings, routes, and policies.

**Key entry point:** `skeleton/agent.py` → `run_agent(user_message, history, current_user_email)` → LLM tool selection → database queries → normalized answer.

## Tech Stack

- **Language:** Python 3.11+
- **Relational DB:** PostgreSQL via `psycopg2` with `RealDictCursor`
- **Graph DB:** Neo4j via the `neo4j` Python driver
- **Vector search:** `pgvector` extension (768-dim Ollama embeddings)
- **Web UI:** Gradio
- **LLM:** Google Gemini or local Ollama (configured via `.env`)
- **Data seed:** JSON mock files in `train-mock-data/`

## Coding Conventions

- **Naming:** `snake_case` for all Python names and SQL identifiers
- **Docstrings:** All functions must have a docstring with `Args:` and `Returns:` sections
- **Return types:** Use type hints. Read-only functions return `list[dict]` or `Optional[dict]`
- **Empty results:** Return `[]` or `None` (as documented), never raise an exception for "not found"
- **SQL:** Use `%s` placeholders for all user inputs — never string-format into SQL
- **Relational pattern:** Use `_connect()` helper + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** Use `_driver()` helper + session with Cypher queries:
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH (n:MetroStation {station_id: $station_id}) ...", station_id=station_id)
          return [dict(record) for record in result]
  ```
- **JSON serialization:** All query results must be JSON-serializable (use `default=str` for datetime)

---

## PostgreSQL Schema (Final — Approved)

Implemented in `databases/relational/schema.sql` and seeded via `seed_postgres.py`.

### Core Tables

```sql
-- ============================================================
-- USERS & AUTHENTICATION
-- ============================================================

CREATE TABLE users (
    user_id VARCHAR(10) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    date_of_birth DATE,
    secret_question VARCHAR(255),
    secret_answer VARCHAR(255),
    registered_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true
);

-- ============================================================
-- INFRASTRUCTURE: STATIONS
-- ============================================================

CREATE TABLE national_rail_stations (
    station_id VARCHAR(4) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    lines TEXT[] NOT NULL,
    is_interchange_national_rail BOOLEAN DEFAULT false,
    interchange_national_rail_lines TEXT[],
    is_interchange_metro BOOLEAN DEFAULT false,
    interchange_metro_station_id VARCHAR(4),
    adjacent_stations JSONB
);

CREATE TABLE metro_stations (
    station_id VARCHAR(4) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    lines TEXT[] NOT NULL,
    is_interchange_metro BOOLEAN DEFAULT false,
    interchange_metro_lines TEXT[],
    is_interchange_national_rail BOOLEAN DEFAULT false,
    interchange_national_rail_station_id VARCHAR(4),
    adjacent_stations JSONB
);

-- ============================================================
-- SCHEDULES
-- ============================================================

CREATE TABLE national_rail_schedules (
    schedule_id VARCHAR(20) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    service_type VARCHAR(20),
    direction VARCHAR(20),
    origin_station_id VARCHAR(4) NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(4) NOT NULL REFERENCES national_rail_stations(station_id),
    stops_in_order TEXT[] NOT NULL,
    passed_through_stations TEXT[],
    first_train_time TIME,
    last_train_time TIME,
    travel_time_from_origin_min JSONB,
    fare_classes JSONB,
    frequency_min INT,
    operates_on TEXT[]
);

CREATE TABLE metro_schedules (
    schedule_id VARCHAR(20) PRIMARY KEY,
    line VARCHAR(10) NOT NULL,
    direction VARCHAR(20),
    origin_station_id VARCHAR(4) NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(4) NOT NULL REFERENCES metro_stations(station_id),
    stops_in_order TEXT[] NOT NULL,
    first_train_time TIME,
    last_train_time TIME,
    travel_time_from_origin_min JSONB,
    base_fare_usd DECIMAL(6, 2),
    per_stop_rate_usd DECIMAL(6, 2),
    frequency_min INT,
    operates_on TEXT[]
);

CREATE TABLE national_rail_seat_layouts (
    layout_id VARCHAR(20) PRIMARY KEY,
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
    coaches JSONB
);

-- ============================================================
-- TRANSACTIONS: BOOKINGS & TRAVEL
-- ============================================================

CREATE TABLE national_rail_bookings (
    booking_id VARCHAR(20) PRIMARY KEY,
    user_id VARCHAR(10) NOT NULL REFERENCES users(user_id),
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
    origin_station_id VARCHAR(4) NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(4) NOT NULL REFERENCES national_rail_stations(station_id),
    travel_date DATE NOT NULL,
    departure_time TIME,
    ticket_type VARCHAR(20),
    fare_class VARCHAR(20),
    coach VARCHAR(2),
    seat_id VARCHAR(10),
    stops_travelled INT,
    amount_usd DECIMAL(10, 2) NOT NULL CHECK (amount_usd >= 0),
    status VARCHAR(20) DEFAULT 'confirmed',
    booked_at TIMESTAMP DEFAULT NOW(),
    travelled_at TIMESTAMP
);

CREATE TABLE metro_travel_history (
    trip_id VARCHAR(20) PRIMARY KEY,
    user_id VARCHAR(10) NOT NULL REFERENCES users(user_id),
    schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id),
    origin_station_id VARCHAR(4) NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(4) NOT NULL REFERENCES metro_stations(station_id),
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(20),
    day_pass_ref VARCHAR(20),
    stops_travelled INT,
    amount_usd DECIMAL(10, 2) NOT NULL CHECK (amount_usd >= 0),
    status VARCHAR(20) DEFAULT 'completed',
    purchased_at TIMESTAMP,
    travelled_at TIMESTAMP
);

-- ============================================================
-- PAYMENTS & FEEDBACK
-- ============================================================

CREATE TABLE payments (
    payment_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20),
    trip_id VARCHAR(20),
    amount_usd DECIMAL(10, 2) NOT NULL CHECK (amount_usd >= 0),
    method VARCHAR(20),
    status VARCHAR(20),
    paid_at TIMESTAMP
);

CREATE TABLE feedback (
    feedback_id VARCHAR(20) PRIMARY KEY,
    booking_id VARCHAR(20),
    trip_id VARCHAR(20),
    user_id VARCHAR(10) NOT NULL REFERENCES users(user_id),
    rating INT CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    submitted_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- POLICIES & VECTOR SEARCH
-- ============================================================

CREATE TABLE policy_documents (
    doc_id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_embedding ON policy_documents USING ivfflat (embedding vector_cosine_ops);
```

---

## Neo4j Graph Schema (Blueprint)

**Status:** Design approved. Implementation starts after review.

### Node Labels

```cypher
-- Metro stations
CREATE CONSTRAINT metro_station_id IF NOT EXISTS 
FOR (n:MetroStation) REQUIRE n.station_id IS UNIQUE;

CREATE (n:MetroStation {
    station_id,           -- e.g., "MS01"
    name,                 -- e.g., "Central Square"
    lines,                -- e.g., ["M1", "M2"]
    is_interchange_metro,
    interchange_metro_lines,
    is_interchange_national_rail,
    interchange_national_rail_station_id
});

-- National rail stations
CREATE CONSTRAINT rail_station_id IF NOT EXISTS 
FOR (n:NationalRailStation) REQUIRE n.station_id IS UNIQUE;

CREATE (n:NationalRailStation {
    station_id,           -- e.g., "NR01"
    name,
    lines,
    is_interchange_national_rail,
    interchange_national_rail_lines,
    is_interchange_metro,
    interchange_metro_station_id
});
```

### Relationship Types

```cypher
-- Metro connections
(MetroStation)-[METRO_LINK {line, direction, travel_time_min, frequency_min}]->(MetroStation)

-- Rail connections
(NationalRailStation)-[RAIL_LINK {line, direction, service_type, travel_time_min, frequency_min, fare_classes}]->(NationalRailStation)

-- Cross-network
(MetroStation)-[INTERCHANGE_TO {transfer_time_min}]->(NationalRailStation)
(NationalRailStation)-[INTERCHANGE_TO {transfer_time_min}]->(MetroStation)
```

---

## Function Signatures (Fixed Contracts)

### PostgreSQL Queries (`databases/relational/queries.py`)

#### Read-only

```python
def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None
) -> list[dict]:
    """Find all national rail services between two stations."""

def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int
) -> Optional[dict]:
    """Calculate fare. Returns {amount_usd, base_fare_usd, per_stop_rate_usd}"""

def query_metro_schedules(
    origin_id: str,
    destination_id: str
) -> list[dict]:
    """Find all metro services between two stations."""

def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """Calculate metro fare. Returns {amount_usd, base_fare_usd, per_stop_rate_usd}"""

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str
) -> list[dict]:
    """List available seats. Returns [{seat_id, coach, row, column}, ...]"""

def auto_select_adjacent_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
    num_seats: int = 1
) -> list[str]:
    """Auto-select adjacent seats. Returns [seat_id, ...]"""

def query_user_profile(user_email: str) -> Optional[dict]:
    """Get user profile. Returns {user_id, email, full_name, phone, date_of_birth, is_active}"""

def query_user_bookings(user_email: str) -> dict:
    """Get user bookings. Returns {national_rail: [...], metro: [...]}"""

def query_payment_info(booking_id: str) -> Optional[dict]:
    """Get payment status. Returns {payment_id, amount_usd, method, status, paid_at}"""

def query_policy_vector_search(embedding: list[float], top_k: int = 3) -> list[dict]:
    """Search policies by embedding. Returns [{doc_id, title, category, content, similarity}, ...]"""
```

#### Write operations

```python
def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single"
) -> tuple[bool, dict | str]:
    """Create booking. Returns (True, booking_dict) or (False, error_msg)"""

def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """Cancel booking. Returns (True, cancellation_dict) or (False, error_msg)"""
```

#### Authentication

```python
def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str
) -> tuple[bool, str]:
    """Register user. Returns (True, user_id) or (False, error_msg)"""

def login_user(email: str, password: str) -> Optional[dict]:
    """Login. Returns user profile dict or None"""

def get_user_secret_question(email: str) -> Optional[str]:
    """Get secret question for password reset"""

def verify_secret_answer(email: str, answer: str) -> bool:
    """Verify secret answer"""

def update_password(email: str, new_password: str) -> bool:
    """Update password"""
```

### Neo4j Graph Queries (`databases/graph/queries.py`)

```python
def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto"
) -> dict:
    """Find fastest route. Returns {route: [...], total_time_min, legs: [...]}"""

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard"
) -> dict:
    """Find cheapest route. Returns {route: [...], total_cost_usd, legs: [...]}"""

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3
) -> list[list[dict]]:
    """Find alternatives avoiding a station. Returns [[...], [...], ...]"""

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """Find cross-network path. Returns {route: [...], total_time_min, interchange_station, legs: [...]}"""

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """Show impact of delay. Returns [{station_id, name, lines, distance_hops}, ...]"""

def query_station_connections(station_id: str) -> list[dict]:
    """List adjacent stations. Returns [{station_id, name, line, travel_time_min}, ...]"""
```

---

## Team Decisions Log

- ✅ **Decision:** PostgreSQL 11 tables + Neo4j dual architecture approved
- ✅ **Decision:** pgvector 768-dim Ollama embeddings (not OpenAI)
- ✅ **Decision:** Neo4j uses apoc.algo.dijkstra for shortest/cheapest routes
- ✅ **Decision:** AI_SESSION_CONTEXT.md is source of truth for all schema and function contracts
- ⏳ **Decision (pending):** Should delays table be added for tracking actual disruptions?

---

## Prompts That Worked

### PostgreSQL schema generation

```
Based on the mock data in train-mock-data/*.json, generate the complete PostgreSQL schema.sql file.

Requirements:
- 11 tables as listed in AI_SESSION_CONTEXT.md
- All foreign keys referencing correct tables
- JSONB for nested structures (fare_classes, coaches, adjacent_stations)
- Indexes on commonly queried columns (email, station_id, travel_date)
- CHECK constraints for data validation (amount_usd >= 0, rating 1-5)

Output only the complete CREATE TABLE statements with no explanation.
```

### Query function generation

```
Implement the function query_national_rail_availability() following the signature and using psycopg2 with RealDictCursor.

[paste function signature from AI_SESSION_CONTEXT.md]

The function should:
1. Connect using the _connect() helper
2. Query national_rail_schedules and related tables
3. Return empty list if no results (don't raise exception)
4. Use parameterized queries (%s placeholders)
```

---

## Quick Reference

**File locations:**
```
databases/relational/
  ├── schema.sql          (CREATE TABLE statements)
  ├── queries.py          (22 query functions)
  └── seed_postgres.py    (load from train-mock-data/)

databases/graph/
  ├── queries.py          (6 Neo4j query functions)
  └── seed_neo4j.py       (populate nodes/edges)

train-mock-data/         (10 JSON data files)

skeleton/
  ├── agent.py            (LLM tool routing — already done)
  └── ui.py               (Gradio interface — already done)
```

**Status:**
- ✅ PostgreSQL schema: Approved, ready to implement
- ✅ Neo4j schema: Approved, waiting for implementation
- ⏳ All query functions: Awaiting implementation
- ✅ Agent.py: Complete (tool routing already implemented)

---

**Last updated:** 2026-06-04  
**Maintained by:** irischue1218-code  
**Version:** 1.0 (Complete & Approved)
