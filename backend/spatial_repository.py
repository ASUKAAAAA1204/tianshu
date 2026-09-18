from __future__ import annotations

from dataclasses import dataclass

from repository import PostgresStorage


INTERSECTION_SQL = """
SELECT id, name, layer_type, level, version
FROM layers
WHERE status = 'published'
  AND ST_Intersects(
        geometry,
        ST_SetSRID(ST_MakeLine(
          ST_MakePoint(%s, %s),
          ST_MakePoint(%s, %s)
        ), 4326)
      )
ORDER BY id
"""


@dataclass(frozen=True)
class SpatialHit:
    id: int
    name: str
    layer_type: str
    level: str
    version: int


class PostGISSpatialRepository:
    def __init__(self, storage: PostgresStorage):
        self.storage = storage

    def find_intersections(self, start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> list[SpatialHit]:
        with self.storage.session() as connection:
            with connection.cursor() as cursor:
                cursor.execute(INTERSECTION_SQL, (start_lng, start_lat, end_lng, end_lat))
                return [SpatialHit(*row) for row in cursor.fetchall()]
