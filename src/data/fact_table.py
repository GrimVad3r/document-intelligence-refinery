"""SQLite fact-table extraction for numerical and tabular documents."""

from __future__ import annotations

import os
import sqlite3
from typing import List

from ..models.extracted_document import ExtractedDocument
from ..utils.errors import QueryError
from ..utils.logging import get_logger


logger = get_logger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS extracted_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    table_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    row_index INTEGER NOT NULL,
    col_index INTEGER NOT NULL,
    column_header TEXT,
    value_text TEXT NOT NULL
);
"""


class FactTableExtractor:
    """Extract table cells into a simple SQL-queryable fact table."""

    def ingest(self, document: ExtractedDocument, db_path: str) -> int:
        """Ingest table cells from an extracted document into SQLite.

        Returns the number of rows inserted.
        """

        if not db_path:
            raise QueryError("db_path is required for fact-table ingestion.")

        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path)
        inserted = 0
        try:
            cur = conn.cursor()
            cur.execute(_SCHEMA_SQL)

            rows: List[tuple] = []
            for table in document.tables:
                for cell in table.cells:
                    header = (
                        table.headers[cell.col_index]
                        if 0 <= cell.col_index < len(table.headers)
                        else None
                    )
                    rows.append(
                        (
                            document.document_id,
                            table.id,
                            table.page_number,
                            cell.row_index,
                            cell.col_index,
                            header,
                            cell.text,
                        )
                    )

            if rows:
                cur.executemany(
                    """
                    INSERT INTO extracted_facts (
                        document_id, table_id, page_number,
                        row_index, col_index, column_header, value_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                inserted = len(rows)

            conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            logger.exception("FactTableExtractor ingestion failed", db_path=db_path)
            raise QueryError("Fact-table ingestion failed.") from exc
        finally:
            conn.close()

        logger.info(
            "Fact-table ingestion completed",
            extra={"document_id": document.document_id, "db_path": db_path, "rows": inserted},
        )
        return inserted

