import os
from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", 
        "postgresql+asyncpg://neondb_owner:npg_f5eoYQgrZ1jy@ep-holy-scene-b3d5pgxv-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?ssl=require"
    )
    
    SYNC_DATABASE_URL: str = os.environ.get(
        "SYNC_DATABASE_URL",
        "postgresql://neondb_owner:npg_f5eoYQgrZ1jy@ep-holy-scene-b3d5pgxv-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def clean_asyncpg_database_url(cls, v: str) -> str:
        if "asyncpg" in v:
            # Replace libpq sslmode=require with asyncpg ssl=require
            v = v.replace("sslmode=require", "ssl=require")
            # Remove libpq channel_binding not recognized by asyncpg
            v = v.replace("channel_binding=require", "")
            # Cleanup leftover delimiters
            v = v.replace("?&", "?").replace("&&", "&").rstrip("&").rstrip("?")
        return v

    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    
    # Embedding config (Dimension is matching the output of all-MiniLM-L6-v2, which is 384)
    EMBEDDING_DIMENSION: int = 384

    STORAGE_PATH: str = os.environ.get("STORAGE_PATH", "./uploads")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

os.makedirs(settings.STORAGE_PATH, exist_ok=True)
