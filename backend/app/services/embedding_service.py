import math
from typing import List
from sentence_transformers import SentenceTransformer

class HuggingFaceEmbedder:
    def __init__(self):
        # Load the light, open source sentence transformer model
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def embed(self, text: str) -> List[float]:
        # Generate the embedding vector
        emb = self.model.encode(text)
        # Convert numpy array elements to Python floats for database/JSON compatibility
        return [float(x) for x in emb]

embedder = HuggingFaceEmbedder()

def get_embedding(text: str) -> List[float]:
    return embedder.embed(text)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    # Small math function to compute cosine similarity of two float vectors
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)
