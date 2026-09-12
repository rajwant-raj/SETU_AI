import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Broad prototype corridor:
# Guwahati -> Imphal
# We intentionally keep this bounded for the first dataset version.
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
out tags center;
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
    data = json.load(response)

with output_path.open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"Saved {len(data.get('elements', []))} road ways to {output_path}")
