"""Queries the resolveflow-issues Pinecone index populated by ingest.py.

EMBEDDING_MODEL/EMBEDDING_DIMENSION must match ingest.py's exactly — the
query embedding and the stored document embeddings have to live in the
same vector space, or Pinecone's similarity search is meaningless.

The Pinecone client and index handle are created on first use, not at
import time. Importing this module (and therefore graph/build.py) used to
require PINECONE_API_KEY plus a network round trip to describe the index,
which made the graph impossible to import in offline tests and PR CI.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

INDEX_NAME = "resolveflow-issues"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 512


@lru_cache(maxsize=1)
def _vector_store():
    from langchain_openai import OpenAIEmbeddings
    from langchain_pinecone import PineconeVectorStore
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSION)
    index = pc.Index(host=pc.describe_index(INDEX_NAME).host)
    return PineconeVectorStore(index=index, embedding=embeddings)


def retrieve_evidence(query: str, k: int = 3) -> list[dict]:
    """`score` is cosine similarity (this index's metric) in roughly [0, 1]
    for real text embeddings. Empirically: a query closely matching real
    corpus content scored ~0.53-0.63; a query unrelated to anything in any
    of the 4 ingested repos scored ~0.21-0.22 — see independent_review.py's
    MIN_RELEVANCE_SCORE, which sits between those two clusters. Callers
    that don't need the score (nothing did, until independent_review.py's
    groundedness check started using it) can just ignore the key.
    """
    results = _vector_store().similarity_search_with_score(query, k)

    return [
        {
            "id": doc.metadata["id"],
            "text": doc.page_content,
            "source": doc.metadata["source"],
            "score": score,
        }
        for doc, score in results
    ]
