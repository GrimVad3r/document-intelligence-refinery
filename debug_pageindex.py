import json
from pathlib import Path
from src.models.pageindex import PageIndex
from src.agents.query_agent import QueryAgent

JSON_PATH = Path(".refinery/pageindex/company_profile.json")

print("JSON exists:", JSON_PATH.exists())
print("JSON path:", JSON_PATH.resolve())

data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

print("Loaded JSON keys:", list(data.keys())[:5])

index = PageIndex.model_validate(data)

hits = QueryAgent().pageindex_navigate(
    "capital expenditure",
    index,
    top_k=3
)

print("Hits found:", len(hits))

for h in hits:
    print(h.title, h.page_start, h.page_end)