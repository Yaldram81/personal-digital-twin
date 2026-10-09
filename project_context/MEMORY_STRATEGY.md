# Memory Strategy

## Memory Types

### 1. Episodic Memory
- User events and interactions
- Time-stamped logs

### 2. Semantic Memory
- Facts about user preferences
- Stable knowledge (likes/dislikes)

### 3. Behavioral Memory
- Decision patterns
- Writing style patterns

---

## Storage Approach

- Vector embeddings for semantic search
- Relational DB for structured facts
- Hybrid retrieval system

---

## Retrieval Strategy

1. Query embedding
2. Top-K semantic search
3. Temporal filtering
4. Re-ranking based on relevance + recency

---

## Critical Rule
Memory must NEVER overwrite truth.
Conflicting memories are stored, not replaced.