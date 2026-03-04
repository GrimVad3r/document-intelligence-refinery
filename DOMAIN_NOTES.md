# Document Intelligence Refinery – Domain Notes

This document captures the domain understanding, design decisions, and failure
mode analysis used to build the Document Intelligence Refinery.

## Extraction Strategy Decision Tree

High-level decision logic:

```text
PDF input
 ├─► Triage Agent → DocumentProfile
 │      ├─ origin_type: native_digital / scanned_image / mixed / form_fillable
 │      ├─ layout_complexity: single_column / multi_column / table_heavy / mixed
 │      ├─ heuristic_signals: avg_chars_per_page, char_density, image_area_ratio
 │      └─ estimated_extraction_cost: fast_text_sufficient / needs_layout_model / needs_vision_model
 │
 ├─► If estimated_extraction_cost == fast_text_sufficient
 │       └─► FastTextExtractor (pdfplumber)
 │             └─► If confidence < escalation.confidence_threshold → LayoutExtractor
 │
 ├─► If estimated_extraction_cost == needs_layout_model
 │       └─► LayoutExtractor (Docling)
 │             └─► If confidence < escalation.confidence_threshold → VisionExtractor
 │
 └─► If estimated_extraction_cost == needs_vision_model
         └─► VisionExtractor (multimodal VLM via HTTP API)
```

Key thresholds are externalized in `rubric/extraction_rules.yaml` so that new
document domains can be onboarded without code changes.

## Observed Failure Modes (Conceptual)

The following failure modes are drawn from typical financial and government
reports:

- **Structure collapse on multi-column layouts**
  - Naive text extraction concatenates left and right columns.
  - Mitigation: use `LayoutExtractor` (Docling) for documents with high
    `multi_column_confidence` or `table_like_region_ratio`.

- **Table misalignment and header loss**
  - OCR or text extraction loses header rows, breaking downstream analytics.
  - Mitigation: represent tables using structured `Table` and `TableCell`
    models; chunking keeps each table as a single LDU so headers are never
    separated from cells.

- **Scanned PDFs with no character stream**
  - `pdfplumber` returns empty text while pages are full images.
  - Mitigation: triage detects low `avg_chars_per_page` and high
    `avg_image_area_ratio` and routes directly to `VisionExtractor`.

- **Context poverty from naive chunking**
  - Fixed-size token windows split tables or list items.
  - Mitigation: `ChunkingEngine` keeps table LDUs intact and generates
    paragraph LDUs aligned with text blocks, avoiding arbitrary mid-sentence
    splits.

- **Provenance blindness**
  - Facts cannot be traced back to page and region.
  - Mitigation: every LDU carries a `ProvenanceChain` with page number,
    optional bounding box, and `content_hash`.

## Pipeline Diagram (Mermaid)

```mermaid
flowchart LR
    A[PDF / Document Input] --> B[Triage Agent<br/>DocumentProfile]
    B --> C{ExtractionRouter}
    C -->|Fast Text| D[FastTextExtractor<br/>pdfplumber]
    C -->|Layout| E[LayoutExtractor<br/>Docling]
    C -->|Vision| F[VisionExtractor<br/>VLM API]
    D -->|low confidence| E
    E -->|low confidence| F
    D --> G[ExtractedDocument]
    E --> G
    F --> G
    G --> H[ChunkingEngine<br/>LDUs]
    H --> I[PageIndexBuilder<br/>PageIndex]
    H --> J[Vector / Fact Store]
    I --> K[QueryAgent<br/>(pageindex_navigate)]
    J --> K
```

## Heuristic Thresholds (Summary)

From `rubric/extraction_rules.yaml`:

- `fast_text_min_avg_chars_per_page`: **150**
- `fast_text_min_char_density`: **0.0015**
- `fast_text_max_image_area_ratio`: **0.4**
- `escalation.confidence_threshold`: **0.7**

Interpretation:

- Documents with low character density and high image area ratio are treated as
  scanned or mixed and escalated away from fast text extraction.
- Extraction strategies must meet a minimum confidence threshold before their
  outputs are accepted; otherwise the router escalates to a more powerful,
  more expensive strategy.

