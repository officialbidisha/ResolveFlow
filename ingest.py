"""Phase 1: ingestion. Run once (or whenever the corpus should refresh) —
not part of the LangGraph pipeline. Fetches closed issues from a real repo,
chunks them, embeds them, and stores them in Pinecone for tools/retrieval.py
to query at runtime.
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec

from tools.github_client import list_closed_issues

load_dotenv()

REPOS = [
    "facebook/react",
    "langchain-ai/langchain",
    "microsoft/terminal",
    "vercel/next.js",
]
ISSUE_COUNT_PER_REPO = 150
INDEX_NAME = "resolveflow-issues"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 512


def _build_documents() -> list[Document]:
    """Fetch closed issues from every repo in REPOS and turn each into one
    Document (pre-split).

    source is repo-prefixed (f"{repo}#{number}", slashes turned to dashes)
    rather than just f"issue-{number}" — plain issue numbers collide across
    repos (facebook/react#10 and langchain-ai/langchain#10 would otherwise
    both become "issue-10", corrupting the id scheme retrieval.py depends
    on for citations).
    """
    documents = []
    for repo in REPOS:
        issues = list_closed_issues(repo, count=ISSUE_COUNT_PER_REPO)
        for issue in issues:
            page_content = f"Issue #{issue['number']}: {issue['title']} \n\n {issue['body'] if issue['body'] is not None else ''}"
            source = f"{repo.replace('/', '-')}-issue-{issue['number']}"
            doc = Document(page_content=page_content, metadata={"source": source, "repo": repo})
            documents.append(doc)
    return documents


def main() -> None:
    print("Ingesting...")
    docs = _build_documents()

    #Step A : Split documents
    splitter = RecursiveCharacterTextSplitter(chunk_size = 800, chunk_overlap= 40)
    chunks = splitter.split_documents(docs)

    #Step B : assign a per chunk id
    counts = {}
    for chunk in chunks:
        source = chunk.metadata["source"]
        index = counts.get(source,0)
        chunk.metadata["id"] = f"{source}#{index}"
        counts[source] = index+1

    ## Step C: embedding the chunks and writing them into the vectorstore
    embedding = OpenAIEmbeddings(model = EMBEDDING_MODEL, dimensions= EMBEDDING_DIMENSION)
    pc = Pinecone(api_key = os.environ["PINECONE_API_KEY"])

    if not pc.has_index(INDEX_NAME):
        print(f"Index {INDEX_NAME!r} not found, creating it...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)

    index = pc.Index(host=pc.describe_index(INDEX_NAME).host)

    # Old runs used a plain "issue-{number}" id scheme (single-repo, no repo
    # prefix) — those ids don't collide with the new repo-prefixed scheme,
    # so they'd just sit there as stale duplicates rather than get
    # overwritten. Clear the index first so re-running this script is
    # actually idempotent, not additive.
    if index.describe_index_stats()["total_vector_count"] > 0:
        print("Clearing existing vectors before re-ingesting...")
        index.delete(delete_all=True)

    vector_store = PineconeVectorStore(index=index, embedding = embedding)

    ids = [chunk.metadata["id"] for chunk in chunks]
    vector_store.add_documents(documents=chunks,ids=ids)

if __name__ == "__main__":
    main()
