"""
ingest_documents.py — Multi-format knowledge base indexer for MindWell RAG.

Supported formats:
  .pdf    — PDF documents (pypdf)
  .docx   — Microsoft Word documents (python-docx)
  .xlsx   — Microsoft Excel workbooks (openpyxl)
  .csv    — Comma-separated values (built-in csv)
  .txt    — Plain text files (built-in)
  .md     — Markdown files (built-in)

Default behavior:
  Scans the documents/ folder automatically and ingests everything it finds.
  Safe to re-run — duplicate chunks are silently skipped.

Usage:
  python ingest_documents.py                        # scans documents/ folder
  python ingest_documents.py documents/file.pdf     # single file
  python ingest_documents.py documents/             # specific folder

Requirements:
  pip install pypdf python-docx openpyxl
  ollama pull nomic-embed-text
"""

import csv
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Default folder to scan
DOCUMENTS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documents")

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md"}


# ================================================================
# TABLE SETUP
# ================================================================

def ensure_rag_table():
    """Creates rag_documents table if it doesn't exist (standalone run support)."""
    from database import get_pooled_connection
    with get_pooled_connection() as conn:
        if not conn:
            logger.error("Cannot connect to database. Check .streamlit/secrets.toml")
            sys.exit(1)
        cur = conn.cursor()
        try:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            except Exception:
                pass
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rag_documents (
                    doc_id         SERIAL PRIMARY KEY,
                    user_id        INTEGER,
                    content        TEXT NOT NULL,
                    content_hash   VARCHAR(32),
                    embedding      vector(768),
                    source         VARCHAR(200),
                    session_id     UUID,
                    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Add content_hash if table already exists without it
            try:
                cur.execute("ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32);")
            except Exception:
                pass
            # Unique index on 32-char hash — never hits btree size limit unlike raw content
            try:
                cur.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS rag_documents_hash_idx
                    ON rag_documents(content_hash)
                    WHERE content_hash IS NOT NULL;
                """)
            except Exception:
                pass
            cur.execute("""
                CREATE INDEX IF NOT EXISTS rag_documents_user_idx
                ON rag_documents(user_id);
            """)
            conn.commit()
            logger.info("rag_documents table ready.")
        except Exception as e:
            logger.error("Failed to create rag_documents table: %s", e)
            sys.exit(1)
        finally:
            cur.close()


# ================================================================
# FILE READERS — one function per format
# ================================================================

def read_pdf(path: str) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("pypdf not installed. Run: pip install pypdf")
        return ""
    try:
        reader = PdfReader(path)
        pages  = [page.extract_text() or "" for page in reader.pages]
        text   = "\n\n".join(p.strip() for p in pages if p.strip())
        logger.info("PDF: %s | pages=%d | chars=%d", os.path.basename(path), len(reader.pages), len(text))
        return text
    except Exception as e:
        logger.error("PDF read failed (%s): %s", path, e)
        return ""


def read_docx(path: str) -> str:
    """Extract text from Word .docx using python-docx."""
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        return ""
    try:
        doc   = Document(path)
        lines = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
        text  = "\n\n".join(lines)
        logger.info("DOCX: %s | paragraphs=%d | chars=%d", os.path.basename(path), len(lines), len(text))
        return text
    except Exception as e:
        logger.error("DOCX read failed (%s): %s", path, e)
        return ""


def read_excel(path: str) -> str:
    """
    Extract text from Excel .xlsx using openpyxl.
    Each sheet becomes a section. Each row becomes a line of text.
    Useful for structured data like mood logs, symptom checklists, Q&A tables.
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed. Run: pip install openpyxl")
        return ""
    try:
        wb      = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sections = []
        for sheet_name in wb.sheetnames:
            ws   = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                sections.append(f"Sheet: {sheet_name}\n" + "\n".join(rows))
        text = "\n\n".join(sections)
        logger.info("XLSX: %s | sheets=%d | chars=%d", os.path.basename(path), len(wb.sheetnames), len(text))
        return text
    except Exception as e:
        logger.error("XLSX read failed (%s): %s", path, e)
        return ""


def read_csv(path: str) -> str:
    """
    Extract text from CSV files.
    Each row is converted to a readable sentence using column headers.
    """
    try:
        lines = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                parts = [f"{k}: {v}" for k, v in row.items() if v and str(v).strip()]
                if parts:
                    lines.append(" | ".join(parts))
        text = "\n".join(lines)
        logger.info("CSV: %s | rows=%d | chars=%d", os.path.basename(path), len(lines), len(text))
        return text
    except Exception as e:
        logger.error("CSV read failed (%s): %s", path, e)
        return ""


def read_text(path: str) -> str:
    """Read plain .txt and .md files."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        logger.info("TEXT: %s | chars=%d", os.path.basename(path), len(text))
        return text
    except Exception as e:
        logger.error("Text read failed (%s): %s", path, e)
        return ""


def read_file(path: str) -> str:
    """Dispatch to correct reader based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    dispatch = {
        ".pdf":  read_pdf,
        ".docx": read_docx,
        ".xlsx": read_excel,
        ".csv":  read_csv,
        ".txt":  read_text,
        ".md":   read_text,
    }
    reader = dispatch.get(ext)
    if not reader:
        logger.warning("Unsupported format: %s — skipping.", path)
        return ""
    return reader(path)


# ================================================================
# CHUNKING
# ================================================================

def chunk_text(text: str, chunk_words: int = 400, overlap_words: int = 50) -> list:
    """
    Split text into overlapping word-based chunks.
    overlap_words ensures no sentence is cut mid-thought at a boundary.
    """
    words  = text.split()
    chunks = []
    start  = 0
    total  = len(words)

    if total == 0:
        return []

    while start < total:
        end   = min(start + chunk_words, total)
        chunk = " ".join(words[start:end]).strip()
        if len(chunk) >= 80:
            chunks.append(chunk)
        if end >= total:
            break
        start = end - overlap_words

    return chunks


# ================================================================
# INGESTION PIPELINE
# ================================================================

def ingest_file(file_path: str, source_label: str = None):
    """Full pipeline for one file: read → chunk → embed → store."""
    from rag import ingest_to_rag

    if not os.path.isfile(file_path):
        logger.error("File not found: %s", file_path)
        return

    ext    = os.path.splitext(file_path)[1].lower()
    source = source_label or os.path.basename(file_path)

    logger.info("=" * 60)
    logger.info("Processing: %s", file_path)

    # Step 1 — Read
    text = read_file(file_path)
    if not text or len(text) < 100:
        logger.warning("File empty or unreadable — skipping: %s", file_path)
        return

    # Step 2 — Chunk
    # Excel/CSV rows are already short — use smaller chunks to preserve row integrity
    chunk_size = 150 if ext in (".xlsx", ".csv") else 400
    chunks     = chunk_text(text, chunk_words=chunk_size, overlap_words=30)

    if not chunks:
        logger.warning("No chunks produced — skipping: %s", file_path)
        return

    logger.info("Chunks: %d (chunk_words=%d)", len(chunks), chunk_size)

    # Step 3 — Embed + Store
    success = 0
    skipped = 0

    for i, chunk in enumerate(chunks, 1):
        result = ingest_to_rag(
            user_id    = None,   # NULL = global knowledge for all users
            content    = chunk,
            source     = source,
            session_id = None,
        )
        if result:
            success += 1
        else:
            skipped += 1

        if i % 10 == 0 or i == len(chunks):
            logger.info("  Progress: %d/%d | success=%d skipped=%d", i, len(chunks), success, skipped)

        time.sleep(0.05)

    logger.info("Done: %s | total=%d success=%d skipped=%d", source, len(chunks), success, skipped)


def ingest_folder(folder_path: str):
    """Scan folder and ingest all supported files."""
    if not os.path.isdir(folder_path):
        logger.error("Folder not found: %s", folder_path)
        sys.exit(1)

    files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ])

    if not files:
        logger.warning(
            "No supported files found in: %s\n"
            "Supported: %s", folder_path, ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
        return

    logger.info("Found %d file(s) in %s", len(files), folder_path)
    for f in files:
        ingest_file(f)
    logger.info("=" * 60)
    logger.info("All files processed.")


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    import streamlit as st

    ensure_rag_table()

    args = sys.argv[1:]

    if not args:
        # Default: scan the documents/ folder
        logger.info("No path given — scanning: %s", DOCUMENTS_FOLDER)
        ingest_folder(DOCUMENTS_FOLDER)

    elif len(args) == 1:
        target = args[0]
        if os.path.isdir(target):
            ingest_folder(target)
        elif os.path.isfile(target):
            ingest_file(target)
        else:
            logger.error("Path not found: %s", target)
            sys.exit(1)

    else:
        for target in args:
            if os.path.isfile(target):
                ingest_file(target)
            else:
                logger.warning("Skipping (not found): %s", target)

    logger.info("Ingestion complete.")
