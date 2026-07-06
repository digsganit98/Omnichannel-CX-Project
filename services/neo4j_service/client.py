import os
import logging

logger = logging.getLogger(__name__)


def _driver():
    try:
        from neo4j import GraphDatabase
        return GraphDatabase
    except ImportError:
        return None


class Neo4jClient:
    def __init__(self) -> None:
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "bfsi-password")
        self.enabled = os.getenv("NEO4J_ENABLED", "true").lower() == "true"
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            GraphDatabase = _driver()
            if GraphDatabase is None:
                raise RuntimeError("neo4j package not installed")
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        if not self.enabled:
            return []
        with self._get_driver().session() as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def write(self, cypher: str, params: dict | None = None) -> None:
        if not self.enabled:
            return
        with self._get_driver().session() as session:
            session.run(cypher, params or {})

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def status(self) -> dict:
        base = {"uri": self.uri, "user": self.user, "enabled": self.enabled}
        if not self.enabled:
            return {**base, "reachable": None}
        try:
            self.query("RETURN 1 AS ping")
            return {**base, "reachable": True}
        except Exception as exc:
            return {**base, "reachable": False, "error": str(exc)}
