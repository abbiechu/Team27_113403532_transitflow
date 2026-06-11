"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        # Wipe the graph before reseeding: combined with MERGE below, this makes
        # re-running the script idempotent (clean rebuild, never duplicates).
        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # ── 建立 Metro 車站節點 ──────────────────────────────────────
        for s in metro_stations:
            session.run(
                """
                MERGE (n:MetroStation {station_id: $station_id})
                SET n.name = $name,
                    n.lines = $lines,
                    n.is_interchange_metro = $is_interchange_metro,
                    n.is_interchange_national_rail = $is_interchange_national_rail
                """,
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"],
                is_interchange_metro=s["is_interchange_metro"],
                is_interchange_national_rail=s["is_interchange_national_rail"],
            )
        print(f"  Created {len(metro_stations)} MetroStation nodes")

        # ── 建立 National Rail 車站節點 ──────────────────────────────
        for s in rail_stations:
            session.run(
                """
                MERGE (n:NationalRailStation {station_id: $station_id})
                SET n.name = $name,
                    n.lines = $lines,
                    n.is_interchange_metro = $is_interchange_metro,
                    n.is_interchange_national_rail = $is_interchange_national_rail
                """,
                station_id=s["station_id"],
                name=s["name"],
                lines=s["lines"],
                is_interchange_metro=s["is_interchange_metro"],
                is_interchange_national_rail=s["is_interchange_national_rail"],
            )
        print(f"  Created {len(rail_stations)} NationalRailStation nodes")

        # ── 建立 Metro 路線連結 (METRO_LINK) ─────────────────────────
        # Fare fields are fixed per relationship (rather than per schedule) so
        # apoc.algo.dijkstra has a single numeric weight to optimise on; the
        # schedule-level fare classes used by PostgreSQL are not graph concerns.
        metro_link_count = 0
        for s in metro_stations:
            for adj in s.get("adjacent_stations", []):
                session.run(
                    """
                    MATCH (a:MetroStation {station_id: $from_id})
                    MATCH (b:MetroStation {station_id: $to_id})
                    MERGE (a)-[r:METRO_LINK {line: $line}]->(b)
                    SET r.travel_time_min = $time,
                        r.base_fare_usd = 0.80,
                        r.per_stop_rate_usd = 0.30
                    """,
                    from_id=s["station_id"],
                    to_id=adj["station_id"],
                    line=adj["line"],
                    time=adj["travel_time_min"],
                )
                metro_link_count += 1
        print(f"  Created {metro_link_count} METRO_LINK relationships")
        # ── 建立 National Rail 路線連結 (RAIL_LINK) ──────────────────
        rail_link_count = 0
        for s in rail_stations:
            for adj in s.get("adjacent_stations", []):
                session.run(
                    """
                    MATCH (a:NationalRailStation {station_id: $from_id})
                    MATCH (b:NationalRailStation {station_id: $to_id})
                    MERGE (a)-[r:RAIL_LINK {line: $line}]->(b)
                    SET r.travel_time_min = $time,
                        r.standard_fare_usd = 1.50,
                        r.first_fare_usd = 2.50
                    """,
                    from_id=s["station_id"],
                    to_id=adj["station_id"],
                    line=adj["line"],
                    time=adj["travel_time_min"],
                )
                rail_link_count += 1
        print(f"  Created {rail_link_count} RAIL_LINK relationships")

        # ── 建立 Metro ↔ Rail 轉乘連結 (INTERCHANGE_TO) ──────────────
        # Created in both directions: route queries follow directed
        # relationships, and a journey may start on either network, so
        # shortestPath needs an INTERCHANGE_TO edge usable from either side.
        interchange_count = 0
        for s in metro_stations:
            if s["is_interchange_national_rail"] and s.get("interchange_national_rail_station_id"):
                nr_id = s["interchange_national_rail_station_id"]
                session.run(
                    """
                    MATCH (m:MetroStation {station_id: $metro_id})
                    MATCH (r:NationalRailStation {station_id: $rail_id})
                    MERGE (m)-[x:INTERCHANGE_TO]->(r)
                    SET x.transfer_time_min = 5
                    """,
                    metro_id=s["station_id"],
                    rail_id=nr_id,
                )
                session.run(
                    """
                    MATCH (r:NationalRailStation {station_id: $rail_id})
                    MATCH (m:MetroStation {station_id: $metro_id})
                    MERGE (r)-[x:INTERCHANGE_TO]->(m)
                    SET x.transfer_time_min = 5
                    """,
                    rail_id=nr_id,
                    metro_id=s["station_id"],
                )
                interchange_count += 2
        print(f"  Created {interchange_count} INTERCHANGE_TO relationships")

    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()