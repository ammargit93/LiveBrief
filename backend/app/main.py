from fastapi import FastAPI, UploadFile
import uuid
from pathlib import Path
import os

UPLOAD_DIR = Path("uploads/")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello, FastAPI!"}

@app.post("/documents")
async def upload_files(file: UploadFile):
    document_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / document_id
    with dest.open("wb") as out:
        while chunk := file.file.read(1024*1024):
            out.write(chunk)
    return {"filename":file.filename}
    