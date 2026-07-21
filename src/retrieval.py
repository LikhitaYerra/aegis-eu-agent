"""Parent-child retrieval with hybrid RRF and cross-encoder reranking."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TOKEN_PATTERN = re.compile(r"\b[\w'-]+\b", re.UNICODE)


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str
    source: str
    jurisdiction: str = "EU"


@dataclass(frozen=True)
class ChildChunk:
    id: str
    parent_id: str
    text: str


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: float
    matched_chunk: str


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _chunks(text: str, size: int = 90, overlap: int = 20) -> Iterable[str]:
    words = text.split()
    step = max(1, size - overlap)
    for start in range(0, len(words), step):
        chunk = words[start : start + size]
        if chunk:
            yield " ".join(chunk)
        if start + size >= len(words):
            break


class HybridRetriever:
    """Fuse BM25 and dense child-chunk rankings, then rerank parent documents."""

    def __init__(
        self,
        documents: Sequence[Document],
        *,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        if not documents:
            raise ValueError("At least one document is required.")
        self.documents = {document.id: document for document in documents}
        self.children = [
            ChildChunk(
                id=f"{document.id}:{index}",
                parent_id=document.id,
                text=chunk,
            )
            for document in documents
            for index, chunk in enumerate(_chunks(document.text))
        ]
        self.embedding_model_name = embedding_model
        self.reranker_model_name = reranker_model
        lightweight = os.getenv("LIGHTWEIGHT_RETRIEVAL", "").lower() in {"1", "true", "yes"}
        lightweight = lightweight or os.getenv("RENDER", "").lower() == "true"
        self._embedding_model = False if lightweight else None
        self._reranker = False if lightweight else None
        self._dense_embeddings = None
        self._build_bm25_index()

    def _build_bm25_index(self) -> None:
        self._term_frequencies = [Counter(_tokens(chunk.text)) for chunk in self.children]
        self._lengths = [sum(frequencies.values()) for frequencies in self._term_frequencies]
        self._average_length = sum(self._lengths) / max(1, len(self._lengths))
        document_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequencies.update(frequencies.keys())
        total = len(self.children)
        self._idf = {
            term: math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequencies.items()
        }

    def _bm25_rank(self, query: str) -> list[int]:
        query_tokens = _tokens(query)
        scores: list[tuple[int, float]] = []
        for index, frequencies in enumerate(self._term_frequencies):
            score = 0.0
            length = self._lengths[index]
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                numerator = frequency * 2.2
                denominator = frequency + 1.2 * (
                    0.25 + 0.75 * length / max(1, self._average_length)
                )
                score += self._idf.get(token, 0.0) * numerator / denominator
            scores.append((index, score))
        return [index for index, _ in sorted(scores, key=lambda item: item[1], reverse=True)]

    def _load_dense_model(self) -> bool:
        if self._embedding_model is False:
            return False
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedding_model = SentenceTransformer(self.embedding_model_name)
                self._dense_embeddings = self._embedding_model.encode(
                    [chunk.text for chunk in self.children],
                    normalize_embeddings=True,
                )
            except (ImportError, OSError, RuntimeError):
                self._embedding_model = False
                self._dense_embeddings = None
        return self._embedding_model is not False

    @staticmethod
    def _hashed_vector(text: str, dimensions: int = 384) -> list[float]:
        vector = [0.0] * dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _dense_rank(self, query: str) -> list[int]:
        if self._load_dense_model():
            query_vector = self._embedding_model.encode([query], normalize_embeddings=True)[0]
            scores = self._dense_embeddings @ query_vector
            return sorted(range(len(scores)), key=lambda index: float(scores[index]), reverse=True)
        query_vector = self._hashed_vector(query)
        vectors = [self._hashed_vector(chunk.text) for chunk in self.children]
        scores = [
            sum(left * right for left, right in zip(query_vector, vector))
            for vector in vectors
        ]
        return sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)

    @staticmethod
    def _rrf(rankings: Sequence[Sequence[int]], constant: int = 60) -> dict[int, float]:
        scores: dict[int, float] = {}
        for ranking in rankings:
            for position, item in enumerate(ranking, start=1):
                scores[item] = scores.get(item, 0.0) + 1.0 / (constant + position)
        return scores

    def _cross_encoder_scores(self, query: str, candidates: list[ChildChunk]) -> list[float]:
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder

                self._reranker = CrossEncoder(self.reranker_model_name)
            except (ImportError, OSError, RuntimeError):
                self._reranker = False
        if self._reranker is not False:
            return [
                float(score)
                for score in self._reranker.predict([(query, chunk.text) for chunk in candidates])
            ]
        query_terms = set(_tokens(query))
        return [
            len(query_terms.intersection(_tokens(chunk.text))) / max(1, len(query_terms))
            for chunk in candidates
        ]

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search child chunks and return their full parents for context assembly."""
        if not query.strip():
            raise ValueError("Query cannot be empty.")
        top_k = max(1, min(top_k, 20))
        fused = self._rrf((self._bm25_rank(query), self._dense_rank(query)))
        candidate_indices = sorted(fused, key=fused.get, reverse=True)[: max(20, top_k * 4)]
        candidates = [self.children[index] for index in candidate_indices]
        reranker_scores = self._cross_encoder_scores(query, candidates)

        best_by_parent: dict[str, tuple[float, ChildChunk]] = {}
        for index, chunk, rerank_score in zip(candidate_indices, candidates, reranker_scores):
            combined = rerank_score + fused[index]
            current = best_by_parent.get(chunk.parent_id)
            if current is None or combined > current[0]:
                best_by_parent[chunk.parent_id] = (combined, chunk)

        ranked = sorted(best_by_parent.items(), key=lambda item: item[1][0], reverse=True)
        return [
            SearchResult(
                document=self.documents[parent_id],
                score=score,
                matched_chunk=chunk.text,
            )
            for parent_id, (score, chunk) in ranked[:top_k]
        ]


def _document_from_path(path: Path) -> Document:
    content = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    if content.startswith("---\n"):
        closing = content.find("\n---", 4)
        if closing != -1:
            for line in content[4:closing].splitlines():
                key, separator, value = line.partition(":")
                if separator:
                    metadata[key.strip()] = value.strip()
    return Document(
        id=path.stem,
        title=metadata.get("title", path.stem.replace("_", " ").title()),
        text=content,
        source=metadata.get("source_url", str(path)),
        jurisdiction=metadata.get("jurisdiction", "EU"),
    )


def load_documents(data_directory: str | Path) -> list[Document]:
    """Load Markdown/text documents; fall back to a small bundled EU corpus."""
    directory = Path(data_directory)
    files = (
        sorted(path for path in directory.glob("*") if path.suffix.lower() in {".md", ".txt"})
        if directory.exists()
        else []
    )
    documents = [
        _document_from_path(path)
        for path in files
        if path.name.lower() != "readme.md"
    ]
    if documents:
        return documents
    return [
        Document(
            id="eu-ai-act-risk",
            title="EU AI Act risk classification",
            source="Regulation (EU) 2024/1689, Articles 5-7 and Annex III",
            text=(
                "The EU AI Act uses a risk-based framework. Article 5 prohibits specified "
                "practices including manipulative techniques, social scoring, and certain "
                "biometric categorisation. Article 6 and Annex III classify high-risk systems, "
                "including systems used in employment, education, essential services, law "
                "enforcement, migration, justice, and critical infrastructure. Providers of "
                "high-risk systems must implement risk management, data governance, technical "
                "documentation, logging, human oversight, accuracy, robustness, and cybersecurity."
            ),
        ),
        Document(
            id="eu-ai-act-transparency",
            title="EU AI Act transparency duties",
            source="Regulation (EU) 2024/1689, Article 50",
            text=(
                "Article 50 establishes transparency obligations for certain AI systems. People "
                "must be informed when interacting directly with an AI system unless this is "
                "obvious. Providers of systems generating synthetic content must make outputs "
                "machine-readable and detectable. Deployers using emotion recognition or "
                "biometric categorisation must inform exposed persons, subject to exceptions."
            ),
        ),
        Document(
            id="eu-ai-act-gpai",
            title="General-purpose AI obligations",
            source="Regulation (EU) 2024/1689, Articles 53-55",
            text=(
                "Providers of general-purpose AI models must maintain technical documentation, "
                "provide information to downstream providers, maintain a copyright compliance "
                "policy, and publish a sufficiently detailed training-content summary. Models "
                "with systemic risk have additional duties for evaluation, adversarial testing, "
                "incident reporting, cybersecurity, and systemic risk assessment and mitigation."
            ),
        ),
        Document(
            id="gdpr-automated-decisions",
            title="GDPR automated decision-making",
            source="Regulation (EU) 2016/679, Articles 13-15 and 22",
            text=(
                "GDPR Article 22 gives a data subject the right not to be subject to a decision "
                "based solely on automated processing that produces legal or similarly significant "
                "effects, subject to exceptions and safeguards. Transparency information includes "
                "meaningful information about the logic involved and the significance and envisaged "
                "consequences. Safeguards include human intervention and the ability to contest."
            ),
        ),
    ]
