# AWS vector store option for retrieval (design only)

Status: **design; not implemented or benchmarked.** Pinecone remains the default. The S3 Vectors and
Bedrock APIs were confirmed reachable in the test AWS account (`ap-southeast-2`); nothing was built.
Verify current service limits and pricing before relying on any number.

## Options
| Option | Gives | Trade-off |
|---|---|---|
| S3 Vectors | Cost-optimized vector storage in S3, native query API, metadata filtering, no cluster | Dense similarity only (no lexical); typically higher latency than a dedicated engine |
| Bedrock Knowledge Bases | Managed ingest/chunk/embed/store + Retrieve API with citations | Less control over chunking and scoring |
| OpenSearch | Hybrid BM25 + vector, filters | Heaviest and most expensive to operate |
| Postgres + pgvector | Already run Postgres; SQL filters; `tsvector` full-text search | Shares resources with the app DB |

## Proposed integration
- Provider-neutral `retrieve(query, k, filters) -> [{id, text, source, score}]`; implementations
  `PineconeRetriever` (existing) and `S3VectorsRetriever` / `BedrockKBRetriever`; chosen by a feature flag.
  Pinecone stays the default until evaluation says otherwise.
- Keep the **same OpenAI embeddings** (text-embedding-3-small, 512 dims) when storing in S3 Vectors, so
  no re-embedding is required and quality is comparable.
- **Score calibration:** `graph/nodes/independent_review.py` gates on `MIN_RELEVANCE_SCORE = 0.35`,
  calibrated on Pinecone cosine similarity. A different store reports a different scale (e.g. distance);
  convert and **re-calibrate on a labeled set** or the groundedness gate changes behavior silently.
- Preserve metadata (id, source, repo, issue number) so citations and filters keep working.
- On provider error: fall back or escalate to a human; never post an ungrounded diagnosis.

## Is OpenSearch / hybrid retrieval needed?
Embeddings match exact tokens (stack-trace lines, exception names, `#4521`) poorly. Try cheaper steps
first: (1) regex-extract issue IDs and use a metadata filter or direct lookup; (2) Postgres full-text
search for stack traces, fused with vector hits via Reciprocal Rank Fusion; (3) adopt OpenSearch hybrid
only if recall@k on exact-match cases still fails.

## Evaluation plan
Labeled set (start from `eval/real_test_cases.py`); measure recall@k, citation relevance, p50/p95
retrieval latency, monthly cost, and a dedicated exact-match slice. Choose the default from the numbers.
