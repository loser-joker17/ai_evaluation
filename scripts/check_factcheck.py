
import json

with open("data/cache/factcheck.json", encoding="utf-8") as f:
    c = json.load(f)

for v in c.values():
    print(
        v.get("notes_used"),
        v["label"],
        v["claim"][:60]
    )
