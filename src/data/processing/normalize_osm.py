import csv
import json
import math
from pathlib import Path

INPUT = Path("datasets/raw/osm/guwahati_imphal_roads.json")
OUTPUT = Path("datasets/processed/road_segments.csv")

ALLOWED_HIGHWAYS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
}


def haversine_km(lat1, lon1, lat2, lon2):
    """Return great-circle distance between two WGS84 coordinates in km."""
    radius_km = 6371.0088
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


INPUT_DATA = json.loads(INPUT.read_text(encoding="utf-8"))

rows = []

for element in INPUT_DATA.get("elements", []):
    tags = element.get("tags", {})
    geometry = element.get("geometry", [])
    highway = tags.get("highway")

    if highway not in ALLOWED_HIGHWAYS or len(geometry) < 2:
        continue

    for index, (start, end) in enumerate(
        zip(geometry, geometry[1:]),
        start=1,
    ):
        start_lat = float(start["lat"])
        start_lon = float(start["lon"])
        end_lat = float(end["lat"])
        end_lon = float(end["lon"])
        length_km = haversine_km(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
        )

        rows.append({
            "segment_id": f"OSM-{element['id']}-{index:04d}",
            "osm_id": element["id"],
            "latitude": (start_lat + end_lat) / 2.0,
            "longitude": (start_lon + end_lon) / 2.0,
            "start_latitude": start_lat,
            "start_longitude": start_lon,
            "end_latitude": end_lat,
            "end_longitude": end_lon,
            "segment_length_km": round(length_km, 6),
            "road_type": highway,
            "name": tags.get("name", ""),
            "surface": tags.get("surface", ""),
            "maxspeed": tags.get("maxspeed", ""),
            "lanes": tags.get("lanes", ""),
        })

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    fieldnames = [
        "segment_id",
        "osm_id",
        "latitude",
        "longitude",
        "start_latitude",
        "start_longitude",
        "end_latitude",
        "end_longitude",
        "segment_length_km",
        "road_type",
        "name",
        "surface",
        "maxspeed",
        "lanes",
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Input OSM ways: {len(INPUT_DATA.get('elements', []))}")
print(f"Normalized road segments: {len(rows)}")
print(f"Saved: {OUTPUT}")
