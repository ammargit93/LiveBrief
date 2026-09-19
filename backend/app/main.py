from contextlib import asynccontextmanager
import os
import uuid

from fastapi import FastAPI, UploadFile, Depends, Request, HTTPException, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.middleware.cors import CORSMiddleware
from .settings import settings
from .utils import embed_document
from .database import get_db, create_tables
from .models import User, Document
from pathlib import Path

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/user/create")
async def create_user( request: Request, db: AsyncSession = Depends(get_db) ):
    data = await request.json()

    username = data.get("username")
    password = data.get("password")

    user = User( username=username, password=password, )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"id": str(user.id), "username": user.username}


@app.post("/user/login")
async def login( request: Request, db: AsyncSession = Depends(get_db), ):
    data = await request.json()

    username = data.get("username")
    password = data.get("password")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return {"error": "Invalid username or password"}

    if user.password != password:
        return {"error": "Invalid username or password"}
    return { "message": "Login successful", "user_id": str(user.id), "username": user.username, }


@app.post("/documents")
async def upload_files( file: UploadFile = File(...), user_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException( status_code=404, detail="User not found", )
    document = Document( document_name=file.filename, user_id=user.id, )
    db.add(document)
    await db.flush()
    user_dir = settings.STORAGE_PATH / Path(str(user.id))
    os.makedirs(user_dir, exist_ok=True)
    extension = file.filename.split(".")[-1]
    dest = user_dir / f"{document.id}.{extension}"
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    chunk_count = await embed_document( dest, document.id, db, )
    await db.commit()
    return { "document_id": str(document.id), "document_name": document.document_name, "chunks": chunk_count, }


@app.get("/documents")
async def get_documents(db: AsyncSession = Depends(get_db) ):
    result = await db.execute(select(Document))
    documents = result.scalars().all()
    return [ { "id": str(document.id), "name": document.document_name, "user_id": str(document.user_id), } for document in documents ]
