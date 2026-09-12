import pandas as pd
from pathlib import Path

INPUT = Path("datasets/processed/road_segments.csv")
OUTPUT = Path("datasets/processed/core_road_segments.csv")

df = pd.read_csv(INPUT)

core_types = ["motorway", "trunk", "primary", "secondary"]

core = df[df["road_type"].isin(core_types)].copy()

core = core.drop_duplicates(subset=["segment_id"])

core.to_csv(OUTPUT, index=False)

print("Total normalized segments:", len(df))
print("Core segments:", len(core))
print()
print(core["road_type"].value_counts())
print()
print("Saved:", OUTPUT)
