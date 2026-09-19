from docx import Document as DocxDocument
from pypdf import PdfReader
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Embedding


embedder = SentenceTransformer("all-MiniLM-L6-v2")


def read_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".md":
        return path.read_text( encoding="utf-8", errors="ignore", )
    if ext == ".pdf":
        return "\n".join( page.extract_text() or "" for page in PdfReader(path).pages )
    if ext == ".docx":
        return "\n".join( p.text for p in DocxDocument(path).paragraphs )
    return ""


def chunk_text( text: str, size: int = 1000, overlap: int = 200, ) -> list[str]:
    step = size - overlap
    return [ chunk for i in range(0, len(text), step) if (chunk := text[i:i + size].strip()) ]


async def embed_document( path: Path, document_id, db: AsyncSession, ) -> int:
    text = read_text(path)
    if not text:
        return 0
    chunks = chunk_text(text)
    vectors = embedder.encode(chunks).tolist()
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        embedding = Embedding( document_id=document_id, chunk=chunk, chunk_index=i, embedding=vector, )
        db.add(embedding)

    await db.flush()
    return len(chunks)