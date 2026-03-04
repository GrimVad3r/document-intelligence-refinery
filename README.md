## Document Intelligence Refinery

A production-grade, multi-stage pipeline that ingests heterogeneous documents
and emits structured, queryable, spatially-indexed knowledge. The design
follows the five-stage architecture from the Document Intelligence Refinery
brief:

- **Triage Agent**
- **Structure Extraction Layer**
- **Semantic Chunking Engine**
- **PageIndex Builder**
- **Query Interface Agent**

### Project Layout

- `src/models`: Pydantic v2 models representing document state
- `src/agents`: Agents for triage, extraction routing, chunking, indexing, querying
- `src/strategies`: Extraction strategies (fast text, layout-aware, vision-augmented)
- `.refinery/`: Runtime artifacts (`profiles`, `extraction_ledger.jsonl`, etc.)
- `rubric/extraction_rules.yaml`: Externalized thresholds and chunking rules
- `tests/`: Pytest-based tests

### Installation

```bash
cd Document-Inetelligence-refinery
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e .
pip install .[dev]
```

Or, using `pip` directly:

```bash
pip install -e ".[dev]"
```

### Running the End-to-End Pipeline

From the project root:

```bash
python -m src.main path\to\document.pdf --doc-id my_doc_id
```

This will:

1. Run the **Triage Agent** (`src/agents/triage.py`) to produce a
   `DocumentProfile` and persist it under `.refinery/profiles/{doc_id}.json`.
2. Use the **ExtractionRouter** (`src/agents/extractor.py`) to select the
   appropriate strategy:
   - `FastTextExtractor` (`src/strategies/fast_text_extractor.py`)
   - `LayoutExtractor` (`src/strategies/layout_extractor.py`)
   - `VisionExtractor` (`src/strategies/vision_extractor.py`)
3. Log the extraction decision, confidence, and cost estimate to
   `.refinery/extraction_ledger.jsonl`.
4. Normalize results into an `ExtractedDocument` model
   (`src/models/extracted_document.py`).
5. Pass the document to the **ChunkingEngine**
   (`src/agents/chunker.py`) to produce a list of LDUs.
6. Build a **PageIndex** using `PageIndexBuilder`
   (`src/agents/indexer.py`) for navigation.

All stages emit structured logs via the centralized logger in
`src/utils/logging.py`.

### Query Interface

Once LDUs and a PageIndex are available, you can use the `QueryAgent`
(`src/agents/query_agent.py`) in your own scripts:

```python
from src.agents.query_agent import QueryAgent

agent = QueryAgent()
top_sections = agent.pageindex_navigate(topic="capital expenditure", index=page_index)
top_ldus = agent.semantic_search(query="capital expenditure for Q3", ldus=ldus)
```

For numerical fact querying, point `structured_query` at a SQLite database
that you populate from extracted tables.

### Logging and Error Handling

- **Logging**: Use `src/utils/logging.py` (`get_logger`) for all logs. The
  default format is JSON, with optional plain text via `REFINERY_LOG_FORMAT`.
- **Errors**: All domain-specific errors derive from `RefineryError` in
  `src/utils/errors.py`. Stages raise specific exceptions such as
  `TriageError`, `ExtractionError`, `ChunkingError`, `IndexingError`,
  and `QueryError`.

### Implementation Guide (How to Extend or Adapt)

- **Onboard a New Document Type**
  - Adjust or extend thresholds in `rubric/extraction_rules.yaml` rather than
    modifying code.
  - Run `python -m src.main` on representative PDFs and inspect:
    - `.refinery/profiles/{doc_id}.json` for triage signals
    - `.refinery/extraction_ledger.jsonl` for strategy selection and confidence
  - If fast-text extraction underperforms, bias
    `estimated_extraction_cost` toward layout or vision tiers.

- **Swap or Enhance Extraction Backends**
  - `FastTextExtractor` uses `pdfplumber` and can be tuned to capture more
    granular text blocks or additional table heuristics.
  - `LayoutExtractor` currently uses Docling; you can extend it to capture
    full structural metadata instead of markdown-only output.
  - `VisionExtractor` talks to an OpenRouter-compatible API. Update
    `DEFAULT_VISION_MODEL` or the request body to use a different provider.

- **Improve Chunking and RAG Quality**
  - Extend `ChunkingEngine` to implement more sophisticated grouping
    (e.g., paragraph merging, heading-aware segmentation) while preserving the
    invariants enforced by `ChunkValidator`.
  - Add a vector-store ingestion layer (e.g., Chroma or FAISS) that indexes
    `LDU.content` alongside `ProvenanceChain` for high-recall retrieval.

- **Enhance Query Interface**
  - Wrap `QueryAgent` in a LangGraph workflow that orchestrates
    `pageindex_navigate`, `semantic_search`, and `structured_query` as tools.
  - Make every answer carry a `ProvenanceChain` and expose document/page/bbox
    to calling applications for audit.

### Running Tests

```bash
pytest
```

The included tests (`tests/test_triage.py`) validate the basic behavior of
the triage agent and confirm that profiles are persisted to `.refinery`.

