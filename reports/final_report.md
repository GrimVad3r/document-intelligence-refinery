# TRP1 Challenge Week 3 - Final Report

Date: March 4, 2026  
Project: Document Intelligence Refinery  
Repository: `document-intelligence-refinery`

## 0. Executive Summary

This project implements a five-stage document intelligence pipeline with typed schemas, confidence-gated extraction routing, chunking, indexing, query utilities, and provenance-aware audit support.

Implemented outcomes:

1. Multi-strategy extraction (`fast_text`, `layout`, `vision`) with escalation guard.
2. Structured normalization (`ExtractedDocument`) and chunking to LDUs with `content_hash` + provenance.
3. PageIndex generation and persistence.
4. Query utilities (`pageindex_navigate`, `semantic_search`, `structured_query`) plus claim verification mode.
5. Data layer integration for vector-ingestion manifests and SQLite fact-table extraction.

Current measured artifact state (as of March 4, 2026):

- Profiles: 6 (`.refinery/profiles/*.json`)
- Ledger rows: 4 (`.refinery/extraction_ledger.jsonl`)
- PageIndex artifacts: 1 (`.refinery/pageindex/company_profile.json`)
- Vector manifests: 1 (`.refinery/vectorstore/company_profile.jsonl`)
- SQLite fact rows: 50 for `company_profile` (`.refinery/facts.db`)

## 1. Domain Notes (Refined)

### 1.1 Strategy Decision Tree

1. Triage each document into a `DocumentProfile`.
2. Route by expected cost tier:
   - `fast_text_sufficient` -> FastTextExtractor
   - `needs_layout_model` -> LayoutExtractor
   - `needs_vision_model` -> VisionExtractor
3. Escalate if extractor confidence < `escalation.confidence_threshold`.

### 1.2 Externalized Rules

From `rubric/extraction_rules.yaml`:

- `fast_text_min_avg_chars_per_page: 150`
- `fast_text_min_char_density: 0.0015`
- `fast_text_max_image_area_ratio: 0.4`
- `escalation.confidence_threshold: 0.7`
- Chunking constitution flags for table/list/caption handling.

### 1.3 Failure Modes and Mitigations

1. Multi-column structure collapse with naive OCR/text extraction.
   - Mitigation: route to layout-aware extraction.
2. Table-header and row separation harms QA integrity.
   - Mitigation: preserve tables as coherent LDU units.
3. Scanned PDFs have weak/empty character streams.
   - Mitigation: route to vision extraction based on triage signals.
4. Context fragmentation from fixed token chunking.
   - Mitigation: chunk by logical document units.
5. Unverifiable answers without source anchors.
   - Mitigation: include page-level provenance and content hashes.

## 2. Final Architecture and Implementation

### 2.1 Pipeline Stages

1. **Triage Agent**  
   `src/agents/triage.py` -> emits and persists `DocumentProfile`.
2. **Structure Extraction Layer**  
   `src/agents/extractor.py` + `src/strategies/*` -> strategy routing + escalation + ledger logging.
3. **Semantic Chunking Engine**  
   `src/agents/chunker.py` -> emits `List[LDU]` with provenance and content hashes.
4. **PageIndex Builder**  
   `src/agents/indexer.py` -> builds and persists PageIndex JSON.
5. **Query Interface Agent**  
   `src/agents/query_agent.py` -> navigation, semantic retrieval, SQL querying, and claim verification helper.

### 2.2 Data Layer

1. **FactTable extractor (SQLite)**: `src/data/fact_table.py`
2. **Vector ingestion manifest**: `src/data/vector_store.py`
3. **Audit mode verifier**: `src/agents/audit_agent.py`
4. **LangGraph-compatible wrapper**: `src/agents/langgraph_query_agent.py` (fallback orchestration path if LangGraph is absent)

## 3. Extraction Quality Analysis

### 3.1 Method

Quality was measured at three levels:

1. Routing quality via extraction ledger (strategy, confidence, cost).
2. Structured extraction quality proxies from ingested fact rows (header and non-empty value rates).
3. Unit-level correctness checks from automated tests (`pytest`).

### 3.2 Quantitative Results

#### A. Routing/Confidence (ledger, n=4 runs)

- Strategy mix: `fast_text=3`, `vision=1`
- Mean confidence score: `0.83`
- Mean estimated API cost: `0.105 USD`
- Mean extraction processing time: `3.806 sec`

#### B. Table Extraction Proxies (SQLite facts for `company_profile`)

- Extracted fact rows: `50`
- Non-empty value rate: `100%` (50/50)
- Column-header coverage: `98%` (49/50)

#### C. Test Results

- `python -m pytest -q` -> **4 passed** (March 4, 2026)
- Includes triage tests and data-layer/audit tests.

### 3.3 Precision/Recall Note

A strict corpus-level precision/recall benchmark for table extraction requires manually annotated ground truth for each evaluated PDF table. That annotation set is not yet present in the repository, so the current report uses operational quality proxies and unit tests.

Benchmark plan to close this gap:

1. Build gold annotations for at least 12 documents (minimum 3 per class).
2. Align extracted tables to gold by table id/page + normalized cell matching.
3. Report per-class and macro precision/recall/F1 in the final evaluation table.

## 4. Lessons Learned

### Lesson 1: High image ratio can coexist with usable text streams

Case: `company_profile` triaged as `origin_type=mixed` with high `image_area_ratio (~0.79)`, but fast-text extraction still produced high confidence (`0.8`) and usable outputs.

Fix/Insight:

1. Routing should consider combined signals, not a single image-area threshold.
2. Escalation guard is essential to avoid overpaying for vision when text extraction is adequate.

### Lesson 2: Single-root PageIndex is operational but weak for navigation quality

Case: Current PageIndex build produces one root section for long reports, which limits section-level navigation precision.

Fix/Insight:

1. Hierarchical section extraction is required for meaningful `pageindex_navigate` behavior.
2. Section-level entities/summaries should be populated per subtree, not only root scope.

### Lesson 3: Data products must be generated in the main pipeline, not ad hoc scripts

Case: Fact-table and vector outputs were initially optional/decoupled, reducing demo reproducibility.

Fix/Insight:

1. Integrated artifact generation directly in `src/main.py`.
2. Added deterministic outputs for PageIndex JSON, vector manifest, and optional SQLite ingestion.

## 5. Deliverables Mapping (Final)

### 5.1 Core Models

- `src/models/document_profile.py`
- `src/models/extracted_document.py`
- `src/models/ldu.py`
- `src/models/pageindex.py`
- `src/models/provenance.py`

### 5.2 Agents and Strategies

- `src/agents/triage.py`
- `src/agents/extractor.py`
- `src/strategies/fast_text_extractor.py`
- `src/strategies/layout_extractor.py`
- `src/strategies/vision_extractor.py`
- `src/agents/chunker.py`
- `src/agents/indexer.py`
- `src/agents/query_agent.py`
- `src/agents/audit_agent.py`
- `src/agents/langgraph_query_agent.py`

### 5.3 Data Layer

- `src/data/fact_table.py`
- `src/data/vector_store.py`

### 5.4 Configuration and Artifacts

- `rubric/extraction_rules.yaml`
- `.refinery/profiles/*.json`
- `.refinery/extraction_ledger.jsonl`
- `.refinery/pageindex/*.json`
- `.refinery/vectorstore/*.jsonl`
- `.refinery/facts.db`

### 5.5 Tests and Setup

- `tests/test_triage.py`
- `tests/test_data_layer_and_audit.py`
- `pyproject.toml`
- `README.md`
- `DOMAIN_NOTES.md`

## 6. Demo Evidence Checklist (Runbook)

1. Triage output shown with `DocumentProfile` JSON.
2. Extraction strategy and confidence shown in ledger.
3. PageIndex JSON shown and navigated.
4. Query answer shown with provenance.
5. Fact-table rows shown in SQLite for structured evidence.

## 7. Remaining Gaps to Full Rubric Completion

1. Build corpus-scale PageIndex artifacts (target: >=12 docs, >=3 per class).
2. Implement strict table precision/recall with annotated ground truth.
3. Enforce all five chunking constitution rules explicitly in `ChunkValidator`.
4. Expand PageIndex from single-root baseline to full hierarchy extraction.
5. Add 12 cross-class Q/A examples with complete provenance citations.

## 8. Conclusion

As of March 4, 2026, the repository contains a working end-to-end refinery pipeline with integrated extraction routing, chunking, indexing, retrieval artifacts, SQLite fact ingestion, and provenance-aware auditing primitives. The system is functional for demonstration and extension, with clearly identified next actions to satisfy the full rubric at corpus scale.

