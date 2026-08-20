"""Queries the resolveflow-issues Pinecone index populated by ingest.py.

EMBEDDING_MODEL/EMBEDDING_DIMENSION must match ingest.py's exactly — the
query embedding and the stored document embeddings have to live in the
same vector space, or Pinecone's similarity search is meaningless.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore


load_dotenv()

INDEX_NAME = "resolveflow-issues"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 512
pc = Pinecone(api_key = os.environ["PINECONE_API_KEY"])

embeddings = OpenAIEmbeddings(model = EMBEDDING_MODEL, dimensions= EMBEDDING_DIMENSION)
index = pc.Index(host=pc.describe_index(INDEX_NAME).host)
vector_store = PineconeVectorStore(index= index, embedding= embeddings)


def retrieve_evidence(query: str, k: int = 3) -> list[dict]:
    results = vector_store.similarity_search(query, k)

    return [
        {
            "id": doc.metadata["id"],
            "text": doc.page_content,
            "source": doc.metadata["source"],
        }
        for doc in results
    ]
