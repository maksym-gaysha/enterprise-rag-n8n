# Enterprise RAG Microservice & Telegram Orchestration

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-HNSW_Cosine-blue?style=for-the-badge)](https://github.com/pgvector/pgvector)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-Embeddings_%26_LLM-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![n8n](https://img.shields.io/badge/n8n-Workflow_Automation-EA4B71?style=for-the-badge&logo=n8n&logoColor=white)](https://n8n.io/)
[![Docker](https://img.shields.io/badge/Docker_Compose-Multi--Container-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

A modular, production-grade **Retrieval-Augmented Generation (RAG)** microservice architected for high-concurrency enterprise document question answering. Built with asynchronous **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL 16 with pgvector**, **Google Gemini models**, and low-latency **n8n Telegram Bot webhook orchestration**.

---

## Table of Contents

- [Key Architectural Features](#-key-architectural-features)
- [Technology Stack](#-technology-stack)
- [Quickstart Guide](#-quickstart-guide)
- [n8n Telegram Bot Setup](#-n8n-telegram-bot-setup)
- [API Documentation & Reference](#-api-documentation--reference)
- [Project Directory Structure](#-project-directory-structure)

---

## Key Architectural Features

- **Asynchronous Core**: Built entirely on async FastAPI and `asyncpg` with SQLAlchemy 2.0 session isolation, backed by `greenlet` C-extensions for maximum concurrency.
- **pgvector with HNSW Indexing**: Document chunks are mapped to 768-dimensional dense vectors indexed with Hierarchical Navigable Small World (HNSW) graphs (`vector_cosine_ops`) for sub-millisecond similarity search (`<=>`).
- **Boundary-Aware Recursive Chunking**: Custom recursive text chunking (~700 characters, ~100 character sliding overlap) designed to preserve semantic sentences, paragraphs, and financial tabular data integrity.
- **Non-Blocking Background Ingestion**: Document parsing (`.pdf` via `pypdf` and `.txt`) and embedding generation execute asynchronously in background tasks, decoupling file upload latency from processing time.
- **Grounded Anti-Hallucination RAG**: Strict prompt constraints require the LLM to refuse ungrounded questions. Includes cosine similarity threshold guards (`< 0.35`) and automated confidence scoring (`high`, `medium`, `low`).
- **Verifiable Source Citations**: Every generated answer provides exact document names, page numbers, similarity match percentages, and original text excerpts.
- **n8n Webhook Orchestration**: Instantaneous, zero-polling Telegram Bot integration powered by official self-hosted n8n and HTTPS webhooks.

---

## Technology Stack

| Layer | Component | Version / Identifier | Rationale |
| :--- | :--- | :--- | :--- |
| **API Framework** | FastAPI | `^0.115.0` | High-throughput asynchronous Python framework with native OpenAPI schema validation. |
| **ASGI Server** | Uvicorn (standard) | `^0.32.0` | Production lightning-fast ASGI implementation with uvloop and httptools. |
| **Database Engine** | PostgreSQL | `16.x` | Industry-standard relational DBMS with ACID compliance. |
| **Vector Extension**| pgvector | `pg16 (0.8+)` | Open-source vector similarity search inside PostgreSQL with HNSW and IVFFlat indexing. |
| **ORM / Driver** | SQLAlchemy + asyncpg | `2.0+` / `^0.30.0` | Fully asynchronous non-blocking database queries with strict schema mapping. |
| **Embedding Model** | Google Gemini | `gemini-embedding-001` | 768-dimensional dense vector embeddings optimized for retrieval precision. |
| **Generative LLM** | Google Gemini | `gemini-2.5-flash` / `3.5-lite`| Fast, highly capable generative model for strict context-grounded synthesis. |
| **Document Parser** | pypdf | `^5.1.0` | High-performance pure-Python PDF extraction preserving physical page numbers. |
| **Workflow Engine** | n8n | `latest (2.x)` | Self-hosted low-code workflow automation orchestrating Webhook ingestion and formatting. |
| **Containerization**| Docker & Docker Compose | `v2.x` | Standardized multi-container orchestration across development and production environments. |

---

## Quickstart Guide

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/install/) (v2.20+ recommended)
- A **Google Gemini API Key** (obtainable from [Google AI Studio](https://aistudio.google.com/))
- A **Telegram Bot Token** (obtainable from [@BotFather](https://t.me/BotFather))

### 2. Environment Configuration
Clone the repository and initialize your `.env` configuration:

```bash
git clone https://github.com/your-username/enterprise-rag-n8n.git
cd enterprise-rag-n8n
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```dotenv
# Core Settings
ENVIRONMENT=development
DEBUG=true

# PostgreSQL & pgvector Credentials
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=enterprise_rag
POSTGRES_PORT=5432

# Google Gemini API
GEMINI_API_KEY=your_actual_gemini_api_key_here

# Telegram & Automation
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
GENERIC_TIMEZONE=Europe/Berlin
TZ=Europe/Berlin

# Set to your public HTTPS tunnel (e.g. from Cloudflare Tunnel, ngrok, or domain)
WEBHOOK_URL=https://your-tunnel-subdomain.trycloudflare.com
```

### 3. Launch with Docker Compose

Build and launch all services in detached mode:

```bash
docker compose up --build -d
```

Verify that all three containers are healthy and running:

```bash
docker compose ps
```

| Service | Container Name | Port Mapping | Health |
| :--- | :--- | :--- | :--- |
| `postgres-db` | `enterprise-rag-db` | `5432:5432` | `healthy` |
| `api` | `enterprise-rag-api` | `8000:8000` | `running` |
| `n8n` | `enterprise-rag-n8n` | `5678:5678` | `running` |

### 4. Verify System Health

Run a cURL request against the system healthcheck probe:

```bash
curl http://localhost:8000/health
```

Expected Response (`200 OK`):
```json
{
  "status": "healthy",
  "database": "connected",
  "pgvector": true
}
```

The database schema and the `vector` extension are automatically verified and created during API startup.

---

## n8n Telegram Bot Setup

The repository includes a ready-to-import, production-grade workflow located in [`workflows/telegram_rag_workflow.json`].

### Step-by-Step Activation

1. **Access n8n Web UI**:
   Navigate to [http://localhost:5678](http://localhost:5678) in your browser and complete the initial local owner setup.

2. **Import Workflow**:
   - Go to **Workflows** > **Add Workflow** > Click the three dots `...` (top right) > **Import from File**.
   - Select [`workflows/telegram_rag_workflow.json`].

3. **Configure Telegram Credentials**:
   - In n8n, navigate to **Credentials** > **New Credential** > Select **Telegram API**.
   - Paste your `TELEGRAM_BOT_TOKEN`.
   - In the imported workflow canvas, verify that both the `Telegram Trigger` and `Send Telegram Reply` nodes have this credential selected.

4. **Connect Public Webhook URL**:
   Telegram webhooks strictly require a public HTTPS address. Expose your n8n container using a tool like Cloudflare Tunnel or ngrok:
   ```bash
   # Example using Cloudflare Quick Tunnels:
   docker run --rm --network enterprise-rag-n8n_rag-network cloudflare/cloudflared:latest tunnel --url http://n8n:5678
   ```
   - Copy the assigned HTTPS URL (e.g. `https://example-subdomain.trycloudflare.com`).
   - Set `WEBHOOK_URL` in your `.env` file to this URL.
   - Restart the n8n container: `docker compose up -d n8n`.

5. **Activate the Workflow**:
   - Switch the workflow toggle in the top-right corner from **Inactive** to **Active**.
   - n8n will automatically register the webhook URL with Telegram.

6. **Test the Bot**:
   Open Telegram, search for your bot, and send:
   > *"What is the service revenue according to the income statement?"*

   The bot will immediately reply with the grounded answer, confidence level badge (🟢 HIGH / 🟡 MEDIUM / 🔴 LOW), document name, page number, similarity score, and excerpt quotes.

---

## API Documentation & Reference

The FastAPI microservice provides interactive Swagger UI documentation at:
**[http://localhost:8000/docs](http://localhost:8000/docs)** (or ReDoc at [http://localhost:8000/redoc](http://localhost:8000/redoc)).

### Core Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Validates database connectivity and pgvector extension readiness. |
| `POST` | `/api/v1/documents/upload` | Uploads a `.pdf` or `.txt` file for asynchronous chunking and embedding. |
| `GET` | `/api/v1/documents/{document_id}/status` | Checks background ingestion status and chunk count. |
| `GET` | `/api/v1/documents` | Lists all documents with processing metadata. |
| `POST` | `/api/v1/chat/query` | Executes grounded vector search and hallucination-free generation. |

---

### Endpoint Specifications & Examples

#### 1. System Healthcheck
`GET /health`

**Response (`200 OK`):**
```json
{
  "status": "healthy",
  "database": "connected",
  "pgvector": true
}
```

---

#### 2. Asynchronous Document Upload
`POST /api/v1/documents/upload`  
*Content-Type: `multipart/form-data`*

**cURL Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "accept: application/json" \
  -F "file=@Sample-Financial-Statements.pdf"
```

**Response (`202 Accepted`):**
```json
{
  "document_id": "a5e8e3d2-4b1f-4c9e-9f3a-1d7589f2b0a1",
  "filename": "Sample-Financial-Statements.pdf",
  "file_size": 245760,
  "status": "PROCESSING",
  "message": "Document accepted for background processing"
}
```

---

#### 3. Document Ingestion Status
`GET /api/v1/documents/{document_id}/status`

**cURL Request:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents/a5e8e3d2-4b1f-4c9e-9f3a-1d7589f2b0a1/status"
```

**Response (`200 OK`):**
```json
{
  "document_id": "a5e8e3d2-4b1f-4c9e-9f3a-1d7589f2b0a1",
  "filename": "Sample-Financial-Statements.pdf",
  "file_size": 245760,
  "status": "READY",
  "chunks_count": 8,
  "error_message": null,
  "created_at": "2026-10-15T19:30:00Z",
  "updated_at": "2026-10-15T19:30:03Z"
}
```

---

#### 4. Grounded RAG Query
`POST /api/v1/chat/query`  
*Content-Type: `application/json`*

**cURL Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/chat/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the total service revenue for the year ended September 30, 2021?",
    "top_k": 4
  }'
```

**Response (`200 OK`):**
```json
{
  "answer": "According to the Sample Company Income Statement (Service), the Service revenue for the year ended September 30, 2021 was $2,750.",
  "confidence": "high",
  "sources": [
    {
      "document_name": "Sample-Financial-Statements.pdf",
      "page_number": 1,
      "excerpt": "Sample Company Income Statement (Service) For the Year Ended September 30, 2021 Service revenue $2,750 Operating Expenses: Depreciation expense 100 Wages expenses 1,200",
      "similarity_score": 0.842
    },
    {
      "document_name": "Sample-Financial-Statements.pdf",
      "page_number": 2,
      "excerpt": "Sample Company Income Statement (Product) For the Year Ended September 30, 2021 Sales revenue $6,875 Cost of Goods Sold ( 4,125) Gross Profit $2,750",
      "similarity_score": 0.691
    }
  ]
}
```

---

## 📂 Project Directory Structure

```text
enterprise-rag-n8n/
├── .env.example                          # Canonical environment configuration template
├── .gitignore                            # Standard Python, Docker & IDE gitignore rules
├── Dockerfile                            # Production multi-stage FastAPI container definition
├── README.md                             # Comprehensive enterprise repository documentation
├── docker-compose.yml                    # Multi-service stack (PostgreSQL + API + n8n)
├── requirements.txt                      # Pinned Python dependencies
├── app/
│   ├── main.py                           # FastAPI application entrypoint & lifespan lifecycle
│   ├── api/
│   │   └── v1/
│   │       ├── router.py                 # Central v1 endpoint router mounting
│   │       └── endpoints/
│   │           ├── chat.py               # RAG retrieval and query endpoints
│   │           ├── documents.py          # Document upload, listing & status endpoints
│   │           └── health.py             # System & pgvector connectivity probe
│   ├── core/
│   │   ├── config.py                     # Pydantic Settings & dynamic async database URI
│   │   └── database.py                   # Async SQLAlchemy engine, sessionmaker & init_db
│   ├── models/
│   │   └── document.py                   # Document & DocumentChunk with Vector(768) + HNSW
│   ├── schemas/
│   │   ├── chat.py                       # Pydantic models for chat requests and responses
│   │   └── document.py                   # Pydantic models for document ingestion and status
│   └── services/
│       ├── gemini_service.py             # Google GenAI SDK client for 768-dim embeddings
│       ├── indexer_service.py            # PDF/TXT extraction, recursive chunker & background worker
│       └── rag_service.py                # Cosine distance retrieval & grounded synthesis
└── workflows/
    └── telegram_rag_workflow.json        # Production Telegram Bot webhook orchestration workflow
```
