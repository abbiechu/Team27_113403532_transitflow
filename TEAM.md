# Team Assignments & Project Status — TransitFlow

**Last updated:** 2026-06-04  
**Project deadline:** 2026-06-15

---

## Team Roster

| Name | Role | Primary Responsibility | Branch | Status | Start Date |
|------|------|------------------------|--------|--------|-----------|
| **朱家締** | PostgreSQL schema + seed_postgres.py |  PostgreSQL schema 、seed_postgres.py | `feature/postgresql` | In Progress | 2026-05-21|
| **劉千** | Neo4j Developer | Neo4j graph design, seeding, Cypher queries | `feature/neo4j` |  In Progress | ? |
| **祝善煦** | PostgreSQL擴充 + Integration | databases/relational/queries.py 擴充、pgvector RAG 整合、design document | `feature/design-document` | In Progress | 2026-05-28 |


---

## Current Sprint Status

### 📌 PostgreSQL & Vector DB (irischue1218-code)

**Status:** ✅ ACTIVE

#### Completed
- [x] Mock data analysis (`train-mock-data/` JSON files)
- [x] ER Diagram design (design_document.md Section 1)
- [x] PostgreSQL schema v1 (all 11 tables defined)
- [x] AI_SESSION_CONTEXT.md with full schema, function signatures, and coding conventions
- [x] TEAM.md (this file)

#### In Progress
- [ ] `databases/relational/schema.sql` - CREATE TABLE statements
- [ ] `databases/relational/seed_postgres.py` - load from JSON files
- [ ] `databases/relational/queries.py` - implement all 22 query functions
  - [ ] 11 read-only queries (availability, fare, bookings, user profile, seats, policy search)
  - [ ] 2 write queries (execute_booking, execute_cancellation)
  - [ ] 5 auth queries (register, login, secret question, password reset)
  - [ ] 1 helper (query_policy_vector_search using pgvector)
- [ ] pgvector integration: seed `policy_documents` table with embeddings
- [ ] Agent.py integration: verify all PostgreSQL tools work with `skeleton/agent.py`

#### Blocked by
- ⏳ Neo4j schema not finalized (can test PostgreSQL independently)

#### Next Actions
1. **This week (by 2026-06-06):**
   - Create `databases/relational/schema.sql`
   - Run seed_postgres.py to populate test database
   - Implement first 5 read-only query functions
   
2. **Next week (by 2026-06-13):**
   - Complete all 22 query functions
   - Test booking/cancellation flow
   - Integrate with agent.py

---

### 📌 Neo4j Graph DB ([Neo4j Member])

**Status:** ⏳ NOT STARTED — **CRITICAL PATH ITEM**

#### Design Phase (BLOCKING implementation)
- [ ] Review `AI_SESSION_CONTEXT.md` Section "Neo4j Graph Schema"
- [ ] Finalize node labels: MetroStation, NationalRailStation
- [ ] Finalize relationship types: METRO_LINK, RAIL_LINK, INTERCHANGE_TO
- [ ] Decide on relationship properties (travel_time_min, frequency_min, fare_classes, etc.)
- [ ] Attend design review meeting with irischue1218-code
- [ ] Update design_document.md Section 3 with Neo4j rationale & design decisions

#### Implementation (starts after design approval)
- [ ] Create Neo4j driver helper: `_driver()` function in `databases/graph/__init__.py`
- [ ] Implement `databases/graph/seed_neo4j.py`:
  - Load station data from PostgreSQL
  - Create MetroStation and NationalRailStation nodes
  - Create METRO_LINK, RAIL_LINK, INTERCHANGE_TO relationships
  - Create uniqueness constraints
- [ ] Implement `databases/graph/queries.py` (6 Cypher functions):
  - `query_shortest_route()` - Dijkstra by travel_time_min
  - `query_cheapest_route()` - Dijkstra by fare
  - `query_alternative_routes()` - avoid specific station
  - `query_interchange_path()` - cross-network routing
  - `query_delay_ripple()` - impact analysis (BFS)
  - `query_station_connections()` - direct neighbors (debug)
- [ ] Test all 6 functions in Neo4j Browser

#### Expected Timeline
- **Design review:** 2026-06-05 (1 day)
- **Implementation:** 2026-06-06 to 2026-06-10 (5 days)
- **Testing:** 2026-06-11 (1 day)
- **Integration:** 2026-06-12 (1 day)

#### Unblocked Dependency
- Can start as soon as irischue1218-code completes PostgreSQL schema (2026-06-06 planned)
- Does NOT need PostgreSQL query functions to be complete

---

### 📌 System Integration & Testing ([QA Member])

**Status:** ⏳ BLOCKED — waiting for PostgreSQL + Neo4j

#### Prerequisites (before starting)
- [ ] PostgreSQL seeded and tested
- [ ] Neo4j seeded and tested
- [ ] All query functions implemented

#### Tasks
- [ ] Verify end-to-end data flow: mock data → postgres → neo4j
- [ ] Test all 12 tools in `skeleton/agent.py`:
  - 6 rail/metro queries
  - 4 route/policy queries
  - 2 booking/cancellation operations
- [ ] Run 20 sample user queries (FAQ document in repo)
- [ ] Verify Gradio UI displays results correctly
- [ ] Check error handling (missing stations, no routes found, etc.)
- [ ] Load test with 100+ concurrent users
- [ ] Document any bugs/issues in ISSUES.md

#### Expected Timeline
- **Integration setup:** 2026-06-12 (1 day)
- **Testing:** 2026-06-13 to 2026-06-15 (3 days)

---

## Decision Log

**2026-06-04**
- ✅ **Decision:** PostgreSQL + Neo4j dual architecture approved
- ✅ **Decision:** Use pgvector 768-dim Ollama embeddings for policy search (not OpenAI)
- ✅ **Decision:** Neo4j Cypher for shortest_route will use apoc.algo.dijkstra
- ✅ **Decision:** AI_SESSION_CONTEXT.md is source of truth for team; updated in every commit that changes schema/functions

**Pending decisions (2026-06-05)**
- ⏳ Neo4j relationship cardinality: should INTERCHANGE_TO be 1:1 or N:M?
- ⏳ Should we add a `delays` table for tracking actual service disruptions?

---

## Blockers & Risks

| Blocker | Impact | Owner | ETA Fix | Workaround |
|---------|--------|-------|---------|-----------|
| Neo4j not started | Blocks route queries, integration testing | [Neo4j Member] | 2026-06-11 | Test PostgreSQL alone first |
| Unknown station IDs in mock data | Seeds may fail | irischue1218-code | 2026-06-05 | Validate JSON schema first |
| pgvector extension not installed | Policy search fails | DevOps | 2026-06-04 | Use Docker Postgres image |

---

## Communication Channels

- **Sync meeting:** Every Wed 10am (30 min)
- **Slack channel:** #transitflow-dev
- **Issue tracker:** GitHub Issues (use labels: `postgres`, `neo4j`, `integration`)
- **Schema questions:** Post in `#schema-discussion` thread

---

## How to Use This File

1. **Team members:** Check your section weekly. Update status, blockers, dates.
2. **irischue1218-code:** Update every time you complete a task or encounter a blocker.
3. **Sync meetings:** Start with this file to discuss progress and risks.
4. **New teammates:** Read this to understand project phase and dependencies.

---

## Quick Status Check (TL;DR)

```
✅ PostgreSQL: On track. Will be ready 2026-06-06.
⏳ Neo4j: Not started. Waiting for design review (2026-06-05).
⏳ Integration: Blocked. Can start 2026-06-12.

🟢 Overall: On schedule for 2026-06-15 deadline.
```

---

## Links

- **Design Document:** [`design_document.md`](design_document.md)
- **AI Context:** [`AI_SESSION_CONTEXT.md`](AI_SESSION_CONTEXT.md)
- **README (User Guide):** [`README.md`](README.md)
- **Issues Tracker:** [GitHub Issues](https://github.com/abbiechu/transitflow/issues)
