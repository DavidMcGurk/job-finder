"""Local sentence-transformer embeddings and cosine similarity."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when the embedding model cannot be loaded or used."""


class Embedder:
    """Wraps a sentence-transformers model for batched local embedding."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> Any:
        """Lazily load the sentence-transformers model."""
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError("sentence-transformers is required for embeddings.") from exc
        logger.info("Loading embedding model: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Embed a list of texts in batches, returning a 2-D array."""
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        model = self._ensure_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text, returning a 1-D array."""
        return self.embed([text])[0]


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between a single vector ``a`` and each row of ``b``.

    Assumes vectors are already L2-normalised (as produced by ``embed`` with
    ``normalize_embeddings=True``). Returns a 1-D array of similarities.
    """
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if b.ndim == 1:
        b = b.reshape(1, -1)
    # Already normalised, so cosine similarity is just dot product
    return (a @ b.T).ravel()


def normalise_cosine(sim: float) -> float:
    """Map cosine similarity from [-1, 1] to [0, 1].

    Cosine similarity for sentence embeddings is typically in [0, 1] already,
    but we normalise defensively to guarantee the [0, 1] range.
    """
    return (sim + 1.0) / 2.0
