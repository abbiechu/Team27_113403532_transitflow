"""
TransitFlow — Neo4j Graph Database Layer

"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]
        
# Station IDs encode their network ("MS" = metro, "NR" = national rail), so the
# label/relationship type can be derived from the ID instead of an extra lookup
# or a "network" argument that callers would have to get right.
def _infer_label(station_id: str) -> str:
    """MS01 → MetroStation，NR01 → NationalRailStation"""
    if station_id.upper().startswith("MS"):
        return "MetroStation"
    return "NationalRailStation"


def _infer_link(station_id: str) -> str:
    """MS01 → METRO_LINK，NR01 → RAIL_LINK"""
    if station_id.upper().startswith("MS"):
        return "METRO_LINK"
    return "RAIL_LINK"

# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.
    Uses apoc.algo.dijkstra (APOC required; enabled in docker-compose.yml).

    Args:
        origin_id:       e.g. "MS01" or "NR01"
        destination_id:  e.g. "MS09" or "NR05"
        network:         "metro", "rail", or "auto" (inferred from IDs)

    Returns:
        dict with keys: found, origin_id, destination_id,
                        total_time_min, path (list of station dicts), legs
    """
    label = _infer_label(origin_id)
    link  = _infer_link(origin_id)

    # Cypher cannot bind parameters to node labels or relationship types, so the
    # inferred label/link names are interpolated into the query string. Both come
    # from a closed set of trusted constants (_infer_label/_infer_link), not user input.
    cypher = f"""
        MATCH (start:{label} {{station_id: $origin_id}})
        MATCH (end:{label}   {{station_id: $destination_id}})
        CALL apoc.algo.dijkstra(start, end, '{link}', 'travel_time_min')
        YIELD path, weight
        RETURN
            [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
            [rel  IN relationships(path) | {{
                line: rel.line,
                travel_time_min: rel.travel_time_min
            }}] AS legs,
            weight AS total_time_min
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            if not record:
                return {"found": False, "origin_id": origin_id, "destination_id": destination_id}
            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "stations": record["stations"],
                "legs": record["legs"],
            }
    
# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising total estimated fare.

    Args:
        origin_id:       e.g. "NR01"
        destination_id:  e.g. "NR05"
        network:         "metro", "rail", or "auto"
        fare_class:      "standard" or "first" (national rail only)

    Returns:
        dict with found, total_fare_usd (approximate), stations, legs
    """
    label     = _infer_label(origin_id)
    link      = _infer_link(origin_id)
    # Metro fares are a flat per-stop rate, while national rail fares vary by
    # class (standard/first), so the Dijkstra weight property differs by network.
    fare_prop = "first_fare_usd" if fare_class == "first" else "standard_fare_usd"
    if label == "MetroStation":
        fare_prop = "per_stop_rate_usd"

    cypher = f"""
        MATCH (start:{label} {{station_id: $origin_id}})
        MATCH (end:{label}   {{station_id: $destination_id}})
        CALL apoc.algo.dijkstra(start, end, '{link}', '{fare_prop}')
        YIELD path, weight
        RETURN
            [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
            [rel  IN relationships(path) | {{
                line: rel.line,
                travel_time_min: rel.travel_time_min
            }}] AS legs,
            weight AS total_fare_usd
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            if not record:
                return {"found": False}
            return {
                "found": True,
                "fare_class": fare_class,
                "total_fare_usd": record["total_fare_usd"],
                "stations": record["stations"],
                "legs": record["legs"],
            }

# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id: str,
    destination_id: str,
    avoid_station_id: str,
    network: str = "auto",
    max_routes: int = 3,
) -> list[list[dict]]:
    """
    Find paths that avoid a specific station.

    Args:
        origin_id:         e.g. "NR01"
        destination_id:    e.g. "NR05"
        avoid_station_id:  e.g. "NR03"
        network:           "metro", "rail", or "auto"
        max_routes:        max number of alternatives

    Returns:
        List of routes, each route is a list of leg dicts
    """
    label = _infer_label(origin_id)
    link  = _infer_link(origin_id)

    # *..15 caps the search depth so shortestPath doesn't traverse the whole
    # graph looking for a path on a disconnected/avoid-blocked network.
    # The avoid filter is applied to the path itself (not post-filtered in
    # Python) so the alternative is guaranteed not to pass through that station.
    cypher = f"""
        MATCH (start:{label} {{station_id: $origin_id}})
        MATCH (end:{label}   {{station_id: $destination_id}})
        MATCH path = shortestPath((start)-[:{link}*..15]->(end))
        WHERE NONE(n IN nodes(path) WHERE n.station_id = $avoid_id)
        WITH path,
             reduce(t = 0, r IN relationships(path) | t + r.travel_time_min) AS total_time
        RETURN
            [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
            [rel  IN relationships(path) | {{
                line: rel.line,
                travel_time_min: rel.travel_time_min
            }}] AS legs,
            total_time
        ORDER BY total_time
        LIMIT $max_routes
    """
    with _driver() as driver:
        with driver.session() as session:
            results = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_id=avoid_station_id,
                max_routes=max_routes,
            )
            return [record["legs"] for record in results]



# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path crossing between metro and national rail networks.

    Args:
        origin_id:       e.g. "MS03" (metro) or "NR05" (rail)
        destination_id:  e.g. "NR05" (rail) or "MS09" (metro)

    Returns:
        dict with found, stations, total_time_min
    """
    origin_label = _infer_label(origin_id)
    dest_label   = _infer_label(destination_id)
    origin_link  = _infer_link(origin_id)
    dest_link    = _infer_link(destination_id)

    # The relationship-type union (origin_link|INTERCHANGE_TO|dest_link) lets
    # shortestPath cross from one network to the other via an interchange edge.
    cypher = f"""
        MATCH (start:{origin_label} {{station_id: $origin_id}})
        MATCH (end:{dest_label}     {{station_id: $destination_id}})
        MATCH path = shortestPath(
            (start)-[:{origin_link}|INTERCHANGE_TO|{dest_link}*..20]->(end)
        )
        WITH path,
             reduce(t = 0, r IN relationships(path) |
                 t + coalesce(r.travel_time_min, r.transfer_time_min, 0)
             ) AS total_time
        RETURN
            [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
            [rel  IN relationships(path) | {{
                type: type(rel),
                line: rel.line,
                travel_time_min: coalesce(rel.travel_time_min, rel.transfer_time_min, 0)
            }}] AS legs,
            total_time AS total_time_min
        ORDER BY total_time
        LIMIT 1
    """
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, origin_id=origin_id, destination_id=destination_id)
            record = result.single()
            if not record:
                return {"found": False, "origin_id": origin_id, "destination_id": destination_id}
            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "stations": record["stations"],
                "legs": record["legs"],
            }

# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed station.

    Args:
        delayed_station_id: e.g. "NR03" or "MS01"
        hops:               how many connections out to search

    Returns:
        List of dicts: {station_id, name, network, hops_away}
    """
    # Neo4j does not allow a parameter to set a variable-length relationship
    # bound, so the validated hop count is interpolated directly into the Cypher.
    cypher = f"""
        MATCH (start {{station_id: $station_id}})
        MATCH p = (start)-[*1..{int(hops)}]->(affected)
        WHERE affected.station_id <> $station_id
        WITH affected, min(length(p)) AS hops_away
        RETURN
            affected.station_id AS station_id,
            affected.name       AS name,
            labels(affected)[0] AS network,
            hops_away
        ORDER BY hops_away, station_id
    """
    with _driver() as driver:
        with driver.session() as session:
            results = session.run(cypher, station_id=delayed_station_id)
            return [
                {
                    "station_id": r["station_id"],
                    "name":       r["name"],
                    "network":    r["network"],
                    "hops_away":  r["hops_away"],
                }
                for r in results
            ]

# ── STATION CONNECTIONS ───────────────────────────────────────────────────────

def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    cypher = """
        MATCH (s {station_id: $station_id})-[r]->(neighbor)
        RETURN
            neighbor.station_id AS station_id,
            neighbor.name       AS name,
            type(r)             AS relationship_type,
            r.line              AS line,
            coalesce(r.travel_time_min, r.transfer_time_min) AS travel_time_min
        ORDER BY neighbor.station_id
    """
    with _driver() as driver:
        with driver.session() as session:
            results = session.run(cypher, station_id=station_id)
            return [dict(r) for r in results]