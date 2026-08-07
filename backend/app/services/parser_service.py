import os
import pypdf
import docx
from typing import List, Tuple

def parse_markdown(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def parse_pdf(file_path: str) -> str:
    reader = pypdf.PdfReader(file_path)
    text_parts = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            text_parts.append(f"[Page {idx + 1}]\n{text}")
    return "\n\n".join(text_parts)

def parse_docx(file_path: str) -> str:
    doc = docx.Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)

def extract_text_and_type(file_path: str, filename: str) -> Tuple[str, str]:
    ext = os.path.splitext(filename)[1].lower()
    
    if ext == ".md":
        return parse_markdown(file_path), "Markdown"
    elif ext == ".pdf":
        return parse_pdf(file_path), "PDF"
    elif ext in [".docx", ".doc"]:
        return parse_docx(file_path), "Word"
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    # Split text by double newlines into paragraphs to keep context together
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        # Fallback to single newline if double newlines are not present
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        
    chunks = []
    current_chunk = []
    current_length = 0
    
    for p in paragraphs:
        p_len = len(p)
        # If adding this paragraph exceeds chunk size, finalize current chunk
        if current_length + p_len > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
            # Carry over the last paragraph for overlap, if it's not too large
            last_p = current_chunk[-1]
            if len(last_p) < overlap:
                current_chunk = [last_p, p]
                current_length = len(last_p) + p_len + 2
            else:
                current_chunk = [p]
                current_length = p_len
        else:
            current_chunk.append(p)
            current_length += p_len + (2 if current_length > 0 else 0)
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks
