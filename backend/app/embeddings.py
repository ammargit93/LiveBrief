import re
import math
from collections import Counter
from typing import List

class SimpleEmbedder:
    def __init__(self):
        # 50 key terms for software engineering artifacts to capture semantics
        self.vocab = [
            "auth", "authentication", "jwt", "oauth", "token", "session", "login", "security",
            "database", "postgres", "sql", "db", "vector", "cache", "redis",
            "feature", "requirement", "prd", "sprint", "timeline", "deadline", "milestone",
            "frontend", "backend", "api", "rest", "graphql", "grpc", "http",
            "docker", "kubernetes", "aws", "s3", "cloud", "serverless",
            "risk", "mitigation", "threat", "failure", "error", "bug", "issue",
            "decision", "adr", "architecture", "design", "pattern", "component",
            "owner", "lead", "assignee", "developer", "manager"
        ]
        self.vocab_map = {word: i for i, word in enumerate(self.vocab)}
        self.dim = len(self.vocab)

    def embed(self, text: str) -> List[float]:
        # Simple bag-of-words keyword frequency vector
        text = text.lower()
        words = re.findall(r'[a-z0-9]+', text)
        counts = Counter(words)
        
        vector = [0.0] * self.dim
        for word, count in counts.items():
            if word in self.vocab_map:
                vector[self.vocab_map[word]] = float(count)
                
        # Normalize the vector using L2 norm
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        else:
            # Hash-based fallback to ensure non-zero vector for overlapping terms
            vector = [0.0] * self.dim
            for word in words:
                h = hash(word) % self.dim
                vector[h] += 1.0
            norm = math.sqrt(sum(v * v for v in vector))
            if norm > 0:
                vector = [v / norm for v in vector]
                
        return vector

embedder = SimpleEmbedder()

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
