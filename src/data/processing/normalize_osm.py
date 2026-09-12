import csv
import json
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

INPUT_DATA = json.loads(INPUT.read_text(encoding="utf-8"))

rows = []

for element in INPUT_DATA.get("elements", []):
    tags = element.get("tags", {})
    center = element.get("center")

    if not center:
        continue

    highway = tags.get("highway")
    if highway not in ALLOWED_HIGHWAYS:
        continue

    rows.append({
        "segment_id": f"OSM-{element['id']}",
        "osm_id": element["id"],
        "latitude": center["lat"],
        "longitude": center["lon"],
        "road_type": highway,
        "name": tags.get("name", ""),
        "surface": tags.get("surface", ""),
        "maxspeed": tags.get("maxspeed", ""),
        "lanes": tags.get("lanes", ""),
    })

OUTPUT.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "segment_id",
            "osm_id",
            "latitude",
            "longitude",
            "road_type",
            "name",
            "surface",
            "maxspeed",
            "lanes",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"Input OSM ways: {len(INPUT_DATA.get('elements', []))}")
print(f"Normalized road segments: {len(rows)}")
print(f"Saved: {OUTPUT}")
