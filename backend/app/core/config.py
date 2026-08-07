import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database Settings
    # Standard connection URL: postgresql+asyncpg://ammar:1234@localhost:5432/livebrief
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", 
        "postgresql+asyncpg://ammar:1234@localhost:5432/livebrief"
    )
    
    # Sync DB URL for migrations / test setups
    SYNC_DATABASE_URL: str = os.environ.get(
        "SYNC_DATABASE_URL",
        "postgresql://ammar:1234@localhost:5432/livebrief"
    )

    # Groq API Settings
    GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
    GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
    GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
    
    # Embedding config (Dimension is matching the output of all-MiniLM-L6-v2, which is 384)
    EMBEDDING_DIMENSION: int = 384

    # Local Storage Settings
    STORAGE_PATH: str = os.environ.get("STORAGE_PATH", "./uploads")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure storage path exists
os.makedirs(settings.STORAGE_PATH, exist_ok=True)
