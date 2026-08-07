import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from backend.app.core.database import Base
from backend.app.core.config import settings

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)
    type = Column(String(50), nullable=True)
    classification_confidence = Column(Float, nullable=True)
    status = Column(String(50), nullable=False, default="processing")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    version = Column(Integer, default=1)

    embeddings = relationship("Embedding", back_populates="document", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")
    graph_runs = relationship("GraphRun", back_populates="document", cascade="all, delete-orphan")

class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)

    document = relationship("Document", back_populates="embeddings")

class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)
    value = Column(JSONB, nullable=False)
    source_excerpt = Column(Text, nullable=True)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSION), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="entities")

class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False)
    existing_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    new_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    existing_entity = relationship("Entity", foreign_keys=[existing_entity_id])
    new_entity = relationship("Entity", foreign_keys=[new_entity_id])

class ProjectSummary(Base):
    __tablename__ = "project_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True)

class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    proposed_change = Column(JSONB, nullable=False)
    conflict_id = Column(UUID(as_uuid=True), ForeignKey("conflicts.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

class Timeline(Base):
    __tablename__ = "timeline"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    event = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    actor = Column(String(100), nullable=False)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL"), nullable=True)
    section = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class GraphRun(Base):
    __tablename__ = "graph_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    current_node = Column(String(100), nullable=False, default="upload")
    status = Column(String(50), nullable=False, default="running")
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="graph_runs")
