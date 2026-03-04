from pathlib import Path

from src.agents.chunker import ChunkingEngine
from src.agents.extractor import ExtractionRouter
from src.agents.query_agent import QueryAgent
from src.agents.triage import triage_document


doc = r"C:\Users\henokt\Downloads\Company_Profile_2024_25.pdf"
doc_id = "company_profile"
query = "Summarize key financial points."


def _safe_console(text: str) -> str:
    """Return text that is safe to print in legacy Windows terminals."""

    return text.encode("cp1252", errors="replace").decode("cp1252")


print("Document exists:", Path(doc).exists())
print("Working directory:", Path().resolve())

# 1) Triage
print("\n--- TRIAGE ---")
profile = triage_document(doc_id=doc_id, document_path=doc)
print("Profile:", profile)

# 2) Extraction
print("\n--- EXTRACTION ---")
extracted = ExtractionRouter().extract(doc, profile)
print("Extraction complete")

# 3) Chunking
print("\n--- CHUNKING ---")
ldus = ChunkingEngine().chunk(extracted)
print("LDUs generated:", len(ldus))

# 4) Query
print("\n--- QUERY ---")
agent = QueryAgent()
result = agent.answer_with_provenance(query, ldus, top_k=2)
hits = agent.semantic_search(query=query, ldus=ldus, top_k=2)

print("\n--- RETRIEVED CHUNKS ---")
for i, hit in enumerate(hits, start=1):
    page = hit.page_refs[0] if hit.page_refs else "n/a"
    print(f"\nChunk {i}:")
    print("Page:", page)
    print("Text preview:", _safe_console(hit.content[:500]))

print("\nANSWER:\n", _safe_console(result.answer[:800]))

if result.provenance.records:
    r = result.provenance.records[0]
    print("\nPROVENANCE:")
    print("document_id:", r.document_id)
    print("page_number:", r.page_number)
    print("bbox:", r.bbox)
    print("content_hash:", r.content_hash)
else:
    print("\nNo provenance records returned.")
