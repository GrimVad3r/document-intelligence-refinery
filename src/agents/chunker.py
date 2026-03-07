"""Semantic chunking engine producing Logical Document Units (LDUs)."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

import yaml  # type: ignore[import-untyped]

from ..models.extracted_document import ExtractedDocument, Figure, Table, TextBlock
from ..models.ldu import LDU, LDUType
from ..models.provenance import BoundingBox, ProvenanceChain, ProvenanceRecord
from ..utils.errors import ChunkingError, ConfigError
from ..utils.logging import get_logger


logger = get_logger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUBRIC_PATH = os.path.join(PROJECT_ROOT, "rubric", "extraction_rules.yaml")

_NUMBERED_ITEM_RE = re.compile(r"^\s*(?:\d+[\.\)]|[A-Za-z][\.\)])\s+")
_HEADER_NUMBERED_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+\S+")
_CROSS_REF_RE = re.compile(r"\b(Table|Figure)\s+(\d+)\b", re.IGNORECASE)


def _hash_content(content: str) -> str:
    """Return a stable hash for content, used in provenance."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _token_count(text: str) -> int:
    return len(text.split())


@dataclass(frozen=True)
class ChunkingRules:
    """Chunking constitution loaded from rubric config."""

    max_tokens_per_ldu: int = 512
    table_preserve_header: bool = True
    keep_numbered_lists_together: bool = True
    attach_captions_to_figures: bool = True


def _load_chunking_rules() -> ChunkingRules:
    if not os.path.exists(RUBRIC_PATH):
        raise ConfigError(f"Missing extraction rules at {RUBRIC_PATH}")
    with open(RUBRIC_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    section = cfg.get("chunking", {}) or {}
    return ChunkingRules(
        max_tokens_per_ldu=int(section.get("max_tokens_per_ldu", 512)),
        table_preserve_header=bool(section.get("table_preserve_header", True)),
        keep_numbered_lists_together=bool(section.get("keep_numbered_lists_together", True)),
        attach_captions_to_figures=bool(section.get("attach_captions_to_figures", True)),
    )


def _is_numbered_list_item(text: str) -> bool:
    return bool(_NUMBERED_ITEM_RE.match(text.strip()))


def _is_section_header(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    words = stripped.split()
    if _HEADER_NUMBERED_RE.match(stripped):
        return True
    if stripped.endswith(":") and len(words) <= 12:
        return True
    if len(words) <= 10 and stripped.upper() == stripped and any(ch.isalpha() for ch in stripped):
        return True
    return False


def _split_list_items_by_token_budget(items: Sequence[str], max_tokens: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0

    for item in items:
        item_tokens = _token_count(item)
        if current and current_tokens + item_tokens > max_tokens:
            chunks.append("\n".join(current))
            current = [item]
            current_tokens = item_tokens
        else:
            current.append(item)
            current_tokens += item_tokens

    if current:
        chunks.append("\n".join(current))
    return chunks


def _extract_explicit_label(caption: str | None, kind: str) -> str | None:
    if not caption:
        return None
    m = re.search(rf"\b{kind}\s+(\d+)\b", caption, flags=re.IGNORECASE)
    if not m:
        return None
    return f"{kind.lower()} {m.group(1)}"


class ChunkValidator:
    """Validator enforcing chunking constitution and core invariants."""

    @staticmethod
    def validate(ldus: List[LDU], rules: ChunkingRules) -> None:
        if not ldus:
            raise ChunkingError("No LDUs produced by chunker.")

        has_header_ldu = any(ldu.ldu_type == LDUType.HEADER for ldu in ldus)

        for ldu in ldus:
            if not ldu.content.strip():
                raise ChunkingError(f"Empty content detected in LDU {ldu.id}")

            if has_header_ldu and ldu.ldu_type != LDUType.HEADER and not ldu.parent_section_id:
                raise ChunkingError(f"Missing parent_section_id for child LDU {ldu.id}")

            if rules.table_preserve_header and ldu.ldu_type == LDUType.TABLE:
                has_header = ldu.metadata.get("has_header", "false").lower() == "true"
                if has_header:
                    first_line = ldu.content.splitlines()[0] if ldu.content.splitlines() else ""
                    if not first_line.strip():
                        raise ChunkingError(f"Table header missing or malformed in {ldu.id}")

            if rules.keep_numbered_lists_together and ldu.ldu_type == LDUType.LIST:
                lines = [ln.strip() for ln in ldu.content.splitlines() if ln.strip()]
                if not lines:
                    raise ChunkingError(f"List LDU has no items in {ldu.id}")
                if any(not _is_numbered_list_item(ln) for ln in lines):
                    raise ChunkingError(f"Non-numbered item found in list LDU {ldu.id}")

            if rules.attach_captions_to_figures and ldu.ldu_type == LDUType.FIGURE:
                if not ldu.metadata.get("caption", "").strip():
                    raise ChunkingError(f"Figure caption missing in {ldu.id}")

            if ldu.id in ldu.related_ldu_ids:
                raise ChunkingError(f"Self-referential relationship detected in {ldu.id}")


class ChunkingEngine:
    """Convert an `ExtractedDocument` into a list of LDUs with semantic invariants."""

    def chunk(self, document: ExtractedDocument) -> List[LDU]:
        rules = _load_chunking_rules()
        ldus: List[LDU] = []
        ldu_id = 0

        current_section_id: str | None = "section-root"
        current_section_title: str | None = "Document"
        section_id_counter = 1
        page_to_section: Dict[int, str] = {}

        table_label_to_ldu: Dict[str, str] = {}
        figure_label_to_ldu: Dict[str, str] = {}

        def _new_ldu(
            *,
            content: str,
            ldu_type: LDUType,
            page_refs: List[int],
            bbox: BoundingBox | None,
            description: str,
            parent_section_id: str | None,
            metadata: Dict[str, str] | None = None,
        ) -> LDU:
            nonlocal ldu_id
            content_hash = _hash_content(content)
            provenance = ProvenanceChain(
                records=[
                    ProvenanceRecord(
                        document_id=document.document_id,
                        page_number=page_refs[0],
                        bbox=bbox,
                        content_hash=content_hash,
                        description=description,
                    )
                ]
            )
            ldu = LDU(
                id=f"ldu-{ldu_id}",
                content=content,
                ldu_type=ldu_type,
                page_refs=page_refs,
                parent_section_id=parent_section_id,
                token_count=_token_count(content),
                content_hash=content_hash,
                provenance=provenance,
                related_ldu_ids=[],
                metadata=metadata or {},
            )
            ldu_id += 1
            return ldu

        text_blocks = sorted(document.text_blocks, key=lambda b: (b.page_number, b.reading_order))
        i = 0
        while i < len(text_blocks):
            block: TextBlock = text_blocks[i]
            content = block.text.strip()
            if not content:
                i += 1
                continue

            if _is_section_header(content):
                section_id = f"section-{section_id_counter}"
                section_id_counter += 1
                current_section_id = section_id
                current_section_title = content
                page_to_section[block.page_number] = section_id
                ldus.append(
                    _new_ldu(
                        content=content,
                        ldu_type=LDUType.HEADER,
                        page_refs=[block.page_number],
                        bbox=block.bbox,
                        description="Section header",
                        parent_section_id=None,
                        metadata={"section_title": content},
                    )
                )
                i += 1
                continue

            if rules.keep_numbered_lists_together and _is_numbered_list_item(content):
                items = [content]
                page_number = block.page_number
                bbox = block.bbox
                j = i + 1
                while j < len(text_blocks):
                    nxt = text_blocks[j]
                    nxt_text = nxt.text.strip()
                    if nxt.page_number != page_number or not _is_numbered_list_item(nxt_text):
                        break
                    items.append(nxt_text)
                    j += 1

                for list_content in _split_list_items_by_token_budget(items, rules.max_tokens_per_ldu):
                    ldus.append(
                        _new_ldu(
                            content=list_content,
                            ldu_type=LDUType.LIST,
                            page_refs=[page_number],
                            bbox=bbox,
                            description="Numbered list",
                            parent_section_id=current_section_id,
                            metadata={
                                "section_title": current_section_title or "",
                                "list_items": str(len([ln for ln in list_content.splitlines() if ln.strip()])),
                            },
                        )
                    )
                i = j
                continue

            page_to_section.setdefault(block.page_number, current_section_id or "section-root")
            ldus.append(
                _new_ldu(
                    content=content,
                    ldu_type=LDUType.PARAGRAPH,
                    page_refs=[block.page_number],
                    bbox=block.bbox,
                    description="Text block",
                    parent_section_id=current_section_id,
                    metadata={"section_title": current_section_title or ""},
                )
            )
            i += 1

        # Rule 1: table cells stay with headers in a single table LDU.
        for table_idx, table in enumerate(document.tables, start=1):
            content = _table_content(table)
            if not content:
                continue

            explicit = _extract_explicit_label(table.caption, "table")
            table_label = explicit or f"table {table_idx}"
            parent_section = page_to_section.get(table.page_number) or None
            metadata = {
                "has_header": "true" if any(h.strip() for h in table.headers if h) else "false",
                "table_label": table_label,
                "section_title": current_section_title or "",
            }
            if table.caption:
                metadata["caption"] = table.caption

            ldu = _new_ldu(
                content=content,
                ldu_type=LDUType.TABLE,
                page_refs=[table.page_number],
                bbox=None,
                description="Table",
                parent_section_id=parent_section,
                metadata=metadata,
            )
            ldus.append(ldu)
            table_label_to_ldu[table_label.lower()] = ldu.id

        # Rule 2: figure caption must be attached to figure LDU metadata.
        for fig_idx, figure in enumerate(document.figures, start=1):
            caption = (figure.caption or "").strip()
            explicit = _extract_explicit_label(caption, "figure")
            figure_label = explicit or f"figure {fig_idx}"
            parent_section = page_to_section.get(figure.page_number) or None
            content = caption or figure_label.title()

            ldu = _new_ldu(
                content=content,
                ldu_type=LDUType.FIGURE,
                page_refs=[figure.page_number],
                bbox=figure.bbox,
                description="Figure",
                parent_section_id=parent_section,
                metadata={
                    "caption": caption,
                    "figure_label": figure_label,
                    "section_title": current_section_title or "",
                },
            )
            ldus.append(ldu)
            figure_label_to_ldu[figure_label.lower()] = ldu.id

        # Rule 5: resolve cross-references and store relationships.
        label_to_id = {**table_label_to_ldu, **figure_label_to_ldu}
        for ldu in ldus:
            refs = _CROSS_REF_RE.findall(ldu.content)
            if not refs:
                continue
            resolved_ids: List[str] = []
            unresolved: List[str] = []
            for kind, num in refs:
                label = f"{kind.lower()} {num}"
                target_id = label_to_id.get(label)
                if target_id and target_id != ldu.id:
                    resolved_ids.append(target_id)
                elif not target_id:
                    unresolved.append(label)

            if resolved_ids:
                ldu.related_ldu_ids = sorted(set(ldu.related_ldu_ids + resolved_ids))
            if unresolved:
                ldu.metadata["unresolved_refs"] = ",".join(sorted(set(unresolved)))

        ChunkValidator.validate(ldus, rules)

        logger.info(
            "Chunking completed",
            extra={
                "document_id": document.document_id,
                "ldu_count": len(ldus),
                "rules": {
                    "max_tokens_per_ldu": rules.max_tokens_per_ldu,
                    "table_preserve_header": rules.table_preserve_header,
                    "keep_numbered_lists_together": rules.keep_numbered_lists_together,
                    "attach_captions_to_figures": rules.attach_captions_to_figures,
                },
            },
        )

        return ldus


def _table_content(table: Table) -> str:
    rows: List[str] = []
    if table.headers:
        rows.append(" | ".join(table.headers))
    by_row: Dict[int, Dict[int, str]] = {}
    for cell in table.cells:
        row = by_row.setdefault(cell.row_index, {})
        row[cell.col_index] = cell.text
    for r_idx in sorted(by_row):
        max_col = max(by_row[r_idx].keys(), default=-1)
        cols = [by_row[r_idx].get(c_idx, "") for c_idx in range(max_col + 1)]
        rows.append(" | ".join(cols))
    return "\n".join(rows).strip()
