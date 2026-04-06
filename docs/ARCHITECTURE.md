# Levy - Architecture & RAG Strategy Documentation
> Zambian Legal AI System | RAG Engine Development Guide
> Last Updated: 2026-03-19

---

## Table of Contents
1. [What is Levy?](#1-what-is-levy)
2. [Core Concepts You Need to Understand](#2-core-concepts)
3. [Where Levy Sits on the RAG Evolution Timeline](#3-rag-evolution)
4. [Current Architecture (What We've Built)](#4-current-architecture)
5. [RAG Strategies - Which Ones Apply to Levy](#5-rag-strategies)
6. [Chunking Strategy Analysis](#6-chunking-strategies)
7. [Evaluation & Testing Strategy](#7-evaluation-testing)
8. [Development Roadmap & Milestones](#8-roadmap)
9. [Glossary of Terms](#9-glossary)

---

## 1. What is Levy?

Levy is a **Retrieval-Augmented Generation (RAG)** system specialized for
**Zambian legislation**. Users ask legal questions in natural language, and
Levy retrieves the most relevant sections from ingested Zambian Acts, then
uses an LLM (Claude) to generate accurate answers with proper legal
citations traceable to specific sections and page numbers.

### Why RAG Instead of Just Using an LLM?

LLMs like Claude have been trained on vast amounts of text, but they have
two critical limitations for legal work:

1. **Knowledge cutoff** - They don't know about recent Zambian legislation
   or amendments
2. **Hallucination** - They can confidently state incorrect legal provisions

RAG solves both problems by *retrieving actual legal text* before generating
an answer. The LLM is constrained to only use what it finds in the retrieved
documents, dramatically reducing hallucination and ensuring answers reflect
the actual law.

### Fun Fact: The Origin of RAG
> The RAG architecture was formally introduced in a 2020 paper by
> Facebook AI Research (now Meta AI). The key insight was deceptively
> simple: instead of trying to store all knowledge inside a model's
> parameters (weights), let the model *look things up* at query time.
> This mirrors how humans work - we don't memorize every law; we look
> up the specific statute when we need it. The original paper combined
> a Dense Passage Retriever (DPR) with a BART sequence-to-sequence
> generator. Since then, RAG has evolved through 5 major stages
> (covered in Section 3).

---

## 2. Core Concepts You Need to Understand

### 2.1 Embeddings - The Foundation of Semantic Search

**What they are:** An embedding is a list of numbers (a vector) that
represents the *meaning* of a piece of text. Similar meanings produce
similar vectors.

**How it works in Levy:**
- We use OpenAI's `text-embedding-3-large` model, which produces vectors
  with **3,072 dimensions** (3,072 numbers per text chunk)
- When a user asks "What are the penalties for illegal mining?", that
  question gets converted to a 3,072-dimensional vector
- We compare this vector to all stored chunk vectors using **cosine
  similarity** (a math formula that measures how "aligned" two vectors are)
- The chunks with the highest similarity scores are the most relevant

**Why 3,072 dimensions?** More dimensions capture more nuance. Think of it
like describing a color: RGB has 3 dimensions (red, green, blue). With
3,072 dimensions, you can capture incredibly subtle differences in meaning.

### Fun Fact: The Curse of Dimensionality
> In lower dimensions, finding the nearest neighbor is trivial. But at
> 3,072 dimensions, exact nearest-neighbor search becomes
> computationally explosive. That's why we use approximate algorithms
> like IVFFlat (Inverted File with Flat compression) - our pgvector
> index trades a tiny bit of accuracy for massive speed gains. The
> IVFFlat algorithm partitions the vector space into 100 clusters
> (lists), so at query time it only searches the nearest clusters
> instead of every single vector.

### 2.2 Chunking - The Unit of Retrieval

**What it is:** Breaking large documents into smaller, meaningful pieces
that can be individually embedded and retrieved.

**Why it matters critically:** The Twig AI guide makes a powerful point:
*chunking quality is a stronger predictor of RAG accuracy than embedding
model choice.* If your chunks are poorly scoped, even the best embedding
model won't save you.

**Current Levy chunking:**
- Max chunk size: 3,000 characters (~800 tokens)
- Overlap: 200 characters between chunks
- Splits at paragraph boundaries, then sentence boundaries
- Preserves the legal hierarchy (Part → Section → Subsection) as metadata

### 2.3 Vector Database - Where Knowledge Lives

**What it is:** A database optimized for storing and searching vectors.

**Levy uses:** Supabase PostgreSQL with the **pgvector** extension.

**How search works:**
```
User Question → Embed → 3072-dim vector
                            ↓
                    pgvector similarity search
                    (cosine similarity)
                            ↓
                    Top-K most similar chunks
                    (K=5 by default)
```

### 2.4 The RAG Pipeline Formula

Formally, a RAG system computes:

```
P(answer | question) = Sum over documents d of:
    P(answer | question, d) * P(d | question)
```

In plain English:
- `P(d | question)` = How likely is document d to be relevant? (retriever)
- `P(answer | question, d)` = Given the question and document, what's the
  answer? (generator/LLM)
- We sum across all retrieved documents to get the final answer

### 2.5 Cosine Similarity - How We Measure "Relevance"

Two vectors are compared by measuring the angle between them:
- **1.0** = identical direction (perfect match)
- **0.0** = perpendicular (unrelated)
- **-1.0** = opposite direction

Our threshold: **0.7** (chunks scoring below this are considered irrelevant)

### Fun Fact: Why Cosine and Not Euclidean Distance?
> Cosine similarity measures the *angle* between vectors, ignoring
> their magnitude (length). This is crucial because two texts about
> the same topic might have embeddings of different lengths (due to
> text length differences), but they'll point in the same *direction*.
> Euclidean distance would penalize length differences; cosine
> similarity doesn't. For text similarity, direction matters more
> than magnitude.

---

## 3. Where Levy Sits on the RAG Evolution Timeline

The Twig AI guide identifies 5 stages of RAG evolution:

```
Stage 1: Information Retrieval (pre-2018)
    TF-IDF, BM25 - keyword matching
    ❌ Levy does NOT use this (yet - see Hybrid RAG)

Stage 2: Neural Retrieval (2018-2020)
    BERT, DPR - dense vector embeddings
    ✅ Levy's current embedding approach

Stage 3: Baseline RAG (2020)
    Retrieval + Generation combined
    ✅ Levy is building toward this NOW ← WE ARE HERE

Stage 4: Context-Aware / Dynamic RAG (2022-2024)
    Query rewriting, adaptive retrieval, confidence scoring
    🎯 Our NEXT target after baseline works

Stage 5: Agentic / Multi-Agent RAG (2024-2025)
    Autonomous agents, self-evaluation, tool use
    🔮 Future vision for Levy
```

**Key insight:** We are building Stage 3 right now. The ingestion pipeline
(parsing, chunking, embedding, storing) is complete. What's missing is
the *retrieval + generation* loop - the actual API endpoint where a user
asks a question and gets an answer with citations.

---

## 4. Current Architecture (What We've Built)

### 4.1 System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    INGESTION PIPELINE                    │
│                     (COMPLETED ✅)                       │
│                                                         │
│  PDF ──→ Parser ──→ Chunker ──→ Embedder ──→ Supabase   │
│   │        │          │           │             │       │
│   │    Extracts    Splits      OpenAI        Stores     │
│   │    hierarchy   with       3072-dim      chunks +    │
│   │    + metadata  metadata   vectors       embeddings  │
│   │                                                     │
│  Sample Acts:                                           │
│  • Environmental Management Act 2011                    │
│  • Employment Code Act 2019                             │
│  • Mines and Minerals Act 2015                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    QUERY PIPELINE                        │
│                   (TO BE BUILT 🔨)                       │
│                                                         │
│  User ──→ API ──→ Embed ──→ Search ──→ LLM ──→ Answer  │
│  Query    Route   Query    Supabase   Claude   + Cites  │
│                                                         │
│  Missing pieces:                                        │
│  • FastAPI routes                                       │
│  • LLM provider (Anthropic/Claude integration)          │
│  • Prompt templates for legal Q&A                       │
│  • Citation formatting                                  │
│  • Session/chat management                              │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Database Schema (7 Tables)

| Table | Purpose | Status |
|-------|---------|--------|
| `legal_documents` | Act metadata (title, year, hash) | ✅ Active |
| `legal_hierarchy` | Act → Part → Section tree | ✅ Active |
| `legal_chunks` | Text chunks + VECTOR(3072) | ✅ Active |
| `amendments` | Track legal amendments | 📋 Schema ready |
| `cross_references` | Links between acts/sections | 📋 Schema ready |
| `chat_sessions` | Chat session tracking | 📋 Schema ready |
| `chat_messages` | Messages with citations | 📋 Schema ready |

### 4.3 File Structure

```
levy/
├── backend/
│   ├── app/
│   │   ├── config.py          # Settings (API keys, thresholds)
│   │   ├── models/
│   │   │   └── schemas.py     # Pydantic data models
│   │   ├── db/
│   │   │   └── supabase.py    # Database operations
│   │   ├── services/
│   │   │   ├── parser.py      # PDF → structured sections
│   │   │   ├── chunker.py     # Sections → embeddable chunks
│   │   │   ├── embedder.py    # Text → 3072-dim vectors
│   │   │   └── ingester.py    # Full pipeline orchestration
│   │   ├── routes/            # 🔨 TO BUILD: API endpoints
│   │   ├── providers/         # 🔨 TO BUILD: LLM providers
│   │   └── prompts/           # 🔨 TO BUILD: Prompt templates
│   └── requirements.txt
├── scripts/
│   ├── ingest_pdf.py          # CLI ingestion tool
│   └── setup_db.sql           # Database schema
├── data/pdfs/                 # Sample Zambian Acts
├── docs/                      # 📋 This documentation
└── frontend/                  # 🔮 Future: Web UI
```

---

## 5. RAG Strategies - Which Ones Apply to Levy

Based on the Twig AI guide's 22 chapters, here's my analysis of which
strategies are relevant for Levy, ordered by implementation priority:

### Tier 1: MUST IMPLEMENT (Baseline + Critical for Legal)

| Strategy | Why for Levy | Priority |
|----------|-------------|----------|
| **Baseline RAG** (Ch.3) | Foundation - retrieve + generate | NOW |
| **Hierarchical RAG** (Ch.9) | Legal docs ARE hierarchical (Act→Part→Section) - we already parse this! | NOW |
| **Context-Aware RAG** (Ch.4) | Multi-turn legal conversations need context | NEXT |
| **Evaluation Metrics** (Ch.14) | Must measure accuracy before improving | NEXT |

### Tier 2: HIGH VALUE (Accuracy Improvements)

| Strategy | Why for Levy | Priority |
|----------|-------------|----------|
| **Hybrid RAG** (Ch.6) | Legal text has specific terms (BM25) AND semantic meaning (dense) | SOON |
| **Multi-Stage Retrieval** (Ch.7) | Broad recall first, then precise reranking - critical for legal precision | SOON |
| **Dynamic RAG** (Ch.5) | Simple questions need few chunks; complex cross-act questions need many | MEDIUM |
| **Synthetic Data Generation** (Ch.15) | Generate Zambian law Q&A pairs for testing | MEDIUM |

### Tier 3: ADVANCED (Production Hardening)

| Strategy | Why for Levy | Priority |
|----------|-------------|----------|
| **Human-in-the-Loop** (Ch.19) | Lawyers should verify and rate answers | LATER |
| **Graph-Based RAG** (Ch.8) | Cross-references between acts form a natural graph | LATER |
| **Domain-Specific Fine-Tuning** (Ch.16) | Tune embeddings for Zambian legal terminology | LATER |
| **Real-Time Monitoring** (Ch.18) | Track hallucination rate, retrieval quality | LATER |

### Tier 4: FUTURE VISION

| Strategy | Why for Levy | Priority |
|----------|-------------|----------|
| **Memory-Augmented RAG** (Ch.12) | Remember user's previous legal research sessions | FUTURE |
| **Agentic RAG** (Ch.10) | Auto-decompose complex legal questions | FUTURE |
| **Multi-Agent RAG** (Ch.20) | Separate agents for different legal domains | FUTURE |
| **Knowledge Graph Integration** (Ch.13) | Build a Zambian law knowledge graph | FUTURE |

### What We DON'T Need (Yet)

- **Streaming RAG** (Ch.11) - Our corpus is static legislation, not live data
- **Privacy & Compliance** (Ch.17) - Important later, but Zambian law is public

---

## 6. Chunking Strategy Analysis

### What Levy Currently Does

Our chunker (`chunker.py`) uses a combination of:
- **Heading-Boundary Chunking** (Strategy 3.4) - We split at Part/Section boundaries
- **Paragraph-Boundary Chunking** (Strategy 3.3) - Fallback for large sections

### What We Should Upgrade To

Based on the Twig guide's 13 chunking strategies, the best fit for
Zambian legislation is:

#### Recommended: Parent-Child Hierarchical Chunking (Strategy 3.7)
**Why:** Legal documents ARE hierarchical. We already parse this structure!
- **Child chunks** (300-500 tokens): Individual sections/subsections for
  precise retrieval
- **Parent chunks** (1,000-1,500 tokens): Full sections for grounding context
- Retrieve children for precision, supply parents to the LLM for context

#### Also Recommended: Contextual-Header Augmented Chunking (Strategy 3.8)
**Why:** When a subsection says "The Minister may...", without context
you don't know WHICH Act, WHICH Part, or WHAT the Minister may do.
- Prepend the full heading path to each chunk:
  `"Employment Code Act 2019 > Part IV: Termination > Section 36: Notice Period > (2)"`
- This makes each chunk self-contained and dramatically improves retrieval

#### Future: Question-Anchored Chunking (Strategy 3.11)
**Why:** Legal users ask specific questions. We can generate likely
questions per section and store them as metadata.
- Example: Section 36 of Employment Code → "What is the required notice
  period for termination?" + "How much notice must an employer give?"

### Critical Insight from Twig
> "If your RAG system hallucinates, your chunk boundaries are usually
> the root cause." This is why we must get chunking right before
> worrying about fancier retrieval strategies.

---

## 7. Evaluation & Testing Strategy

### 7.1 What to Measure (Three Layers)

Based on the Twig guide's Chapter 14:

```
Layer 1: RETRIEVER METRICS (Did we find the right chunks?)
├── Recall@K      - Of all relevant chunks, what % did we retrieve?
├── Precision@K   - Of retrieved chunks, what % were actually relevant?
└── MRR           - How high was the first relevant chunk ranked?

Layer 2: GENERATOR METRICS (Did the LLM answer correctly?)
├── Faithfulness  - Does the answer stick to retrieved evidence?
├── Groundedness  - Can every claim be traced to a source chunk?
└── Completeness  - Did the answer cover all relevant aspects?

Layer 3: HUMAN EVALUATION (Does a lawyer agree?)
├── Correctness   - Is the legal interpretation accurate?
├── Helpfulness   - Would this answer help a real user?
└── Citation Quality - Are the references correct and useful?
```

### 7.2 How to Build a Test Suite for Zambian Law

**Phase 1: Manual Gold Set (Start Here)**
Create 20-30 question-answer pairs manually from our 3 Acts:
```
Q: "What is the minimum notice period for terminating employment?"
A: "Under Section 36 of the Employment Code Act No. 3 of 2019..."
Expected chunks: [chunk_id_1, chunk_id_2]
```

**Phase 2: Synthetic Data Generation (Chapter 15)**
Use Claude to generate more Q&A pairs from our ingested chunks:
- Feed each chunk to Claude
- Ask: "Generate 3 realistic questions a Zambian lawyer might ask
  that this text answers"
- Filter for quality and accuracy

**Phase 3: Automated Evaluation (Chapter 18)**
Use RAGAS or a custom evaluator to score every response automatically.

### 7.3 Testing Philosophy

> **Teach moment:** Many developers test RAG systems by asking a few
> questions and seeing if the answers "look right." This is like testing
> software by running it once and checking if it crashes. You need:
>
> 1. **Regression tests** - A fixed set of Q&A pairs that must always pass
> 2. **Retrieval tests** - Verify the right chunks come back for known queries
> 3. **Edge case tests** - Cross-act questions, ambiguous queries, questions
>    about topics NOT in the corpus (the system should say "I don't know")
> 4. **Adversarial tests** - Try to make it hallucinate or cite wrong sections

---

## 8. Development Roadmap & Milestones

### Milestone 1: Baseline RAG (Current Sprint)
**Goal:** A user can ask a question and get an answer with citations.

Tasks:
- [ ] Build FastAPI routes (`/api/chat`, `/api/search`, `/api/documents`)
- [ ] Build LLM provider (Anthropic Claude integration)
- [ ] Build prompt templates for legal Q&A with citation instructions
- [ ] Build the RAG chain: query → embed → search → prompt → respond
- [ ] Test with manual questions against our 3 Acts

**Success criteria:** Ask "What are the penalties for illegal mining under
Zambian law?" and get a correct, cited answer from the Mines and Minerals
Act.

### Milestone 2: Evaluation Framework
**Goal:** Objectively measure how good our system is.

Tasks:
- [ ] Create 25+ gold Q&A pairs across all 3 Acts
- [ ] Build automated evaluation script (retrieval + generation metrics)
- [ ] Establish baseline scores (Recall@5, Faithfulness, Groundedness)
- [ ] Set up synthetic data generation pipeline

### Milestone 3: Chunking Upgrade
**Goal:** Improve retrieval accuracy through better chunking.

Tasks:
- [ ] Implement Parent-Child Hierarchical Chunking
- [ ] Implement Contextual-Header Augmented Chunking
- [ ] Re-ingest all PDFs with new chunking strategy
- [ ] Compare metrics before/after (A/B evaluation)

### Milestone 4: Hybrid Retrieval
**Goal:** Combine keyword search (BM25) with vector search.

Tasks:
- [ ] Add BM25/full-text search index to Supabase
- [ ] Implement fusion scoring (combine BM25 + vector scores)
- [ ] Add reranking step (cross-encoder or ColBERT)
- [ ] Measure improvement on legal terminology queries

### Milestone 5: Context-Aware Conversations
**Goal:** Multi-turn legal research conversations.

Tasks:
- [ ] Implement chat session management
- [ ] Build query rewriter (compress conversation history into search query)
- [ ] Implement context window management
- [ ] Test multi-turn scenarios

### Milestone 6: Production Hardening
**Goal:** Real-time monitoring, feedback loops, more Acts.

Tasks:
- [ ] Add observability (latency, token cost, retrieval quality per query)
- [ ] Implement human feedback collection (thumbs up/down, corrections)
- [ ] Ingest 20+ additional Zambian Acts
- [ ] Performance optimization (caching, batch retrieval)

---

## 9. Glossary of Terms

| Term | Definition |
|------|-----------|
| **RAG** | Retrieval-Augmented Generation - retrieve relevant docs before generating an answer |
| **Embedding** | A vector (list of numbers) representing the meaning of text |
| **Cosine Similarity** | Math formula measuring how similar two vectors are (0 to 1) |
| **Top-K** | The K most similar chunks retrieved for a query (default K=5) |
| **Chunk** | A piece of text small enough to embed and retrieve individually |
| **Hallucination** | When an LLM generates confident but incorrect information |
| **Faithfulness** | Whether an answer only contains claims supported by retrieved evidence |
| **Groundedness** | Whether every claim in an answer can be traced to a source |
| **BM25** | A keyword-matching search algorithm (Best Matching 25) |
| **Dense Retrieval** | Searching by comparing vector embeddings |
| **Sparse Retrieval** | Searching by keyword overlap (TF-IDF, BM25) |
| **Cross-Encoder** | A model that scores query-document pairs together for reranking |
| **IVFFlat** | An approximate nearest neighbor index that clusters vectors for faster search |
| **pgvector** | PostgreSQL extension for storing and searching vectors |
| **Reranker** | A second-stage model that re-scores retrieved results for better precision |
| **Context Window** | The maximum amount of text an LLM can process in one request |
| **Token** | A sub-word unit (~4 characters in English); LLMs count in tokens |
| **RAGAS** | An open-source framework for evaluating RAG systems |
| **MRR** | Mean Reciprocal Rank - measures where the first correct result appears |
| **Recall@K** | What fraction of relevant documents appear in the top K results |
| **DPR** | Dense Passage Retriever - Facebook's original neural retriever (2020) |

---

*This document is a living reference. It will be updated as we progress
through each milestone.*
