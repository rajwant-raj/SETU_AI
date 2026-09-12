import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

SOUTH = 24.50
WEST = 90.90
NORTH = 27.90
EAST = 94.50

QUERY = f"""
[out:json][timeout:180];
(
  way["highway"]["highway"~"motorway|trunk|primary|secondary|tertiary"](
    {SOUTH},{WEST},{NORTH},{EAST}
  );
);
out tags geom;
"""

output_path = Path("datasets/raw/osm/guwahati_imphal_roads.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

request = Request(
    OVERPASS_URL,
    data=urlencode({"data": QUERY}).encode("utf-8"),
    headers={"User-Agent": "SETU-AI/0.1 dataset prototype"},
    method="POST",
)

with urlopen(request, timeout=240) as response:
    data = json.loads(response.read().decode("utf-8"))

output_path.write_text(
    json.dumps(data),
    encoding="utf-8",
)

print(f"Downloaded OSM ways: {len(data.get('elements', []))}")
print(f"Saved: {output_path}")
