"""Tiny RAG retrieval over docs/*.md — TF-IDF vectors, FAISS index.

Deliberately not a real embedding model: this repo's corpus is two short
markdown files, a handful of paragraphs each. TfidfVectorizer produces real,
deterministic vectors with no extra API key and no heavy ML dependency —
the point of this module is the citation/groundedness architecture (see
graph/nodes/independent_review.py), not retrieval quality at scale.
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sklearn.feature_extraction.text import TfidfVectorizer

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


class TfidfEmbeddings(Embeddings):
    """Wraps a pre-fitted sklearn TfidfVectorizer to satisfy LangChain's Embeddings interface.

    The vectorizer is fit once, over the whole corpus, at index-build time —
    embed_query must reuse that same fitted vocabulary (never re-fit on a
    query), or query vectors and document vectors would live in different
    dimensions and similarity search would be meaningless.
    """

    def __init__(self, vectorizer: TfidfVectorizer) -> None:
        self._vectorizer = vectorizer

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._vectorizer.transform(texts).toarray().tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._vectorizer.transform([text]).toarray()[0].tolist()


def _load_chunks() -> list[tuple[str, str]]:
    """Returns [(chunk_id, chunk_text), ...] for every markdown file in docs/.

    chunk_id is "{filename-without-extension}#{chunk-index}" — e.g.
    "runbook#2" — a stable id independent_review can later check
    Diagnosis.citations against.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=40)
    chunks: list[tuple[str, str]] = []
    for doc_path in sorted(DOCS_DIR.glob("*.md")):
        for i, piece in enumerate(splitter.split_text(doc_path.read_text())):
            chunks.append((f"{doc_path.stem}#{i}", piece))
    return chunks


def build_index() -> FAISS:
    chunks = _load_chunks()
    ids = [chunk_id for chunk_id, _ in chunks]
    texts = [text for _, text in chunks]

    vectorizer = TfidfVectorizer().fit(texts)
    embeddings = TfidfEmbeddings(vectorizer)

    return FAISS.from_texts(texts, embeddings, metadatas=[{"id": chunk_id} for chunk_id in ids])


_index: FAISS | None = None


def _get_index() -> FAISS:
    global _index
    if _index is None:
        _index = build_index()
    return _index


def retrieve_evidence(query: str, k: int = 3) -> list[dict]:
    results = _get_index().similarity_search(query, k=k)
    return [
        {
            "id": doc.metadata["id"],
            "text": doc.page_content,
            "source": doc.metadata["id"].split("#")[0],
        }
        for doc in results
    ]
