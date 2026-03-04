# TRP1 Week 3 Interim Report

Date: March 4, 2026  
Project: Document Intelligence Refinery  
Repository: `document-intelligence-refinery`

## 1. Domain Notes

### 1.1 Extraction Strategy Decision Tree

The implemented decision flow is:

1. Run `Triage Agent` to produce `DocumentProfile`.
2. Route by `estimated_extraction_cost`:
   - `fast_text_sufficient` -> `FastTextExtractor`
   - `needs_layout_model` -> `LayoutExtractor`
   - `needs_vision_model` -> `VisionExtractor`
3. Apply escalation guard:
   - Fast text -> layout when confidence is below threshold.
   - Layout -> vision when confidence is below threshold.

Current threshold configuration (`rubric/extraction_rules.yaml`):

- `fast_text_min_avg_chars_per_page`: `150`
- `fast_text_min_char_density`: `0.0015`
- `fast_text_max_image_area_ratio`: `0.4`
- `escalation.confidence_threshold`: `0.7`

### 1.2 Failure Modes Observed and Mitigations

1. Structure collapse in multi-column layouts  
   Mitigation: route to layout-aware extraction.
2. Table header/cell separation during chunking  
   Mitigation: preserve table rows as single LDUs.
3. Scanned PDF with near-zero character stream  
   Mitigation: direct routing to vision strategy.
4. Context fragmentation from naive chunking  
   Mitigation: chunk by logical document units (text blocks and tables).
5. Provenance blindness during QA  
   Mitigation: attach `ProvenanceChain` and `content_hash` to LDUs.

## 2. Architecture Diagram (5-Stage Pipeline)

```mermaid
flowchart LR
    A[Document Input: PDF] --> B[Triage Agent<br/>DocumentProfile]
    B --> C{ExtractionRouter}
    C -->|Fast Text| D[FastTextExtractor]
    C -->|Layout-Aware| E[LayoutExtractor]
    C -->|Vision| F[VisionExtractor]
    D -->|low confidence| E
    E -->|low confidence| F
    D --> G[ExtractedDocument]
    E --> G
    F --> G
    G --> H[Semantic Chunking Engine<br/>List[LDU]]
    H --> I[PageIndex Builder<br/>PageIndex JSON]
    H --> J[Vector Ingestion Manifest]
    G --> K[FactTable Extractor<br/>SQLite]
    I --> L[Query Interface Agent]
    J --> L
    K --> L
    L --> M[Answer + Provenance / Audit Verdict]
```

## 3. Cost Analysis (Strategy A/B/C)

### 3.1 Cost Model

- Strategy A (`FastTextExtractor`): local parsing, no API spend.
- Strategy B (`LayoutExtractor`): local Docling execution, no API spend.
- Strategy C (`VisionExtractor`): API-based; estimated in code as:
  - `tokens_estimate = len(extracted_text) / 4`
  - `cost_estimate_usd = tokens_estimate / 1000 * 0.15`
  - per-document budget cap: `0.50 USD`

### 3.2 Estimated Cost per Strategy Tier

| Strategy | Tooling | Cost Tier | Estimated API Cost / Doc | Budget Guard |
|---|---|---|---:|---|
| A | pdfplumber | Low | 0.00 USD | N/A |
| B | Docling | Medium | 0.00 USD | N/A |
| C | OpenRouter VLM | High | 0.10 to 0.50 USD | 0.50 USD cap |

### 3.3 Interim Artifact Snapshot

From repository artifacts as of March 4, 2026:

- Profiles: 5 (`.refinery/profiles`)
  - `fast_text_sufficient`: 2
  - `needs_layout_model`: 2
  - `needs_vision_model`: 1
- Ledger rows: 2 (`.refinery/extraction_ledger.jsonl`)
  - strategy usage: `fast_text` (1), `vision` (1)
  - observed average confidence: `0.86`
  - observed average cost: `0.21 USD`
  - observed scanned-doc vision example: `0.42 USD`

Interpretation:

- The cost profile is dominated by scanned/image-first documents routed to Strategy C.
- For native digital reports, Strategy A/B keeps API spend near zero.
- The router plus confidence threshold controls when high-cost escalation occurs.

## 4. Interim Repository Evidence Mapping

### 4.1 Core Models

- `src/models/document_profile.py`
- `src/models/extracted_document.py`
- `src/models/ldu.py`
- `src/models/pageindex.py`
- `src/models/provenance.py`

### 4.2 Agents and Strategies (Phases 1-2)

- `src/agents/triage.py`
- `src/strategies/fast_text_extractor.py`
- `src/strategies/layout_extractor.py`
- `src/strategies/vision_extractor.py`
- `src/agents/extractor.py`

### 4.3 Configuration and Artifacts

- `rubric/extraction_rules.yaml`
- `.refinery/profiles/*.json`
- `.refinery/extraction_ledger.jsonl`

### 4.4 Setup and Tests

- `pyproject.toml`
- `README.md`
- `tests/test_triage.py`
- `tests/test_data_layer_and_audit.py`

## 5. Interim Summary

The repository now contains the required multi-stage typed architecture, strategy router with escalation guard, externalized thresholds, and persisted profiling/ledger artifacts. The interim submission is aligned with the challenge structure and includes a cost-quality routing strategy suitable for heterogeneous enterprise documents.

