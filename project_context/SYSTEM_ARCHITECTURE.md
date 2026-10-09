# System Architecture

## Overview
The system is composed of four layers:

1. Input Layer (User Data Ingestion)
2. Memory Layer (Storage + Retrieval)
3. Intelligence Layer (LLM Reasoning)
4. Output Layer (Personalized Responses)

---

## Components

### 1. Data Ingestion
- Chat logs
- Notes
- Documents
- Activity history

### 2. Memory System
- Vector database (semantic memory)
- Structured DB (facts, preferences)
- Temporal memory (time-based tracking)

### 3. Reasoning Engine
- LLM (primary reasoning)
- RAG pipeline
- Context prioritization logic

### 4. Response Generator
- Style conditioning
- Behavior alignment
- Personalization layer

---

## Key Design Choice
Memory is separated into:
- Short-term context
- Long-term knowledge
- Preference memory

This avoids context confusion and improves retrieval accuracy.