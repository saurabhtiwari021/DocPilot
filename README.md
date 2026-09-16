# DocPilot

![DocPilot logo](app/static/logo.png)

A production-inspired **Retrieval-Augmented Generation (RAG)** platform built with **FastAPI**, **LangChain**, and **Google Gemini**. The application enables users to upload documents, perform semantic search using vector embeddings, and receive context-aware responses grounded in the uploaded content.

The project follows a modular architecture with support for authentication, persistent conversation history, configurable storage backends, and pluggable vector databases, making it easy to extend and deploy.

---

## Features

- JWT-based Authentication (Register/Login)
- Multi-user document isolation
- Upload PDF, DOCX and TXT documents
- Retrieval-Augmented Generation (RAG)
- Semantic Search using Vector Embeddings
- Persistent Chat History
- Source-aware Responses
- Prompt Engineering with reusable templates
- Structured logging (`logging.info` / `logging.error`) across every request path
- Configurable Storage Layer (Local / AWS S3)
- Configurable Vector Store (FAISS / pgvector)
- RESTful APIs built with FastAPI
- Docker support for containerized deployment
- Modular and scalable project architecture

---

# Tech Stack

### Backend

- Python
- FastAPI
- LangChain
- Google Gemini API
- SQLAlchemy
- JWT Authentication
- Pydantic

### AI

- Large Language Models (LLMs)
- Prompt Engineering
- Retrieval-Augmented Generation (RAG)
- Embeddings
- Semantic Search

### Storage

- Local Storage
- AWS S3 (Configurable)

### Vector Database

- FAISS
- PostgreSQL + pgvector (Configurable)

### Database

- SQLite (Development)
- PostgreSQL (Supported)

### DevOps

- Docker
- Docker Compose

---

# Architecture

```
                    +---------------------+
                    |      Frontend       |
                    +----------+----------+
                               |
                               |
                        REST API (FastAPI)
                               |
          +--------------------+--------------------+
          |                    |                    |
          |                    |                    |
 Authentication          Document Upload      Chat Endpoint
          |                    |                    |
          |                    |                    |
          +--------------------+--------------------+
                               |
                      Document Processing
                               |
               Text Extraction & Chunking
                               |
                         Embedding Model
                               |
                  Configurable Vector Store
                 (FAISS / PostgreSQL pgvector)
                               |
                           Retriever
                               |
                      Prompt Template Engine
                               |
                           Gemini LLM
                               |
                   Context-aware AI Response
                               |
                     Conversation History
```

---

# Project Structure

```
app
│
├── api/
│   └── routes/         # auth, upload, chat, history, documents
│
├── auth/                # models, schemas, security (bcrypt + JWT), service, dependencies
│
├── config/              # settings.py - all env-driven configuration
│
├── database/            # SQLAlchemy engine/session, table creation
│
├── models/               # Pydantic request/response schemas
│
├── prompts/              # ChatPromptTemplate definitions
│
├── static/               # logo.png (served at /static/logo.png, also used as favicon)
│
├── services/
│   ├── document_loader.py       # PDF / DOCX / TXT loading + splitting
│   ├── storage_service.py       # Configurable storage: local disk or AWS S3
│   ├── vectorstore_service.py   # Configurable vector store: FAISS or pgvector
│   ├── memory_service.py        # Per-user, per-session conversation history
│   └── rag_service.py           # History-aware RAG chain
│
└── main.py               # FastAPI app + startup lifecycle
```

---

# API Endpoints

## Authentication

| Method | Endpoint |
|----------|----------------|
| POST | /auth/register |
| POST | /auth/login |

---

## Documents

| Method | Endpoint |
|----------|----------------|
| POST | /upload |
| GET | /documents |

---

## Chat

| Method | Endpoint |
|----------|----------------|
| POST | /chat |
| GET | /history |
| DELETE | /history |

---

# RAG Pipeline

1. User uploads one or more documents.
2. Documents are parsed and split into chunks.
3. Embeddings are generated.
4. Embeddings are stored in the configured vector store.
5. User submits a query.
6. Semantic search retrieves the most relevant document chunks.
7. Retrieved context is combined with a prompt template.
8. The LLM generates a grounded response.
9. Response and conversation history are stored for future interactions.

---

# Configuration

The project supports interchangeable backends.

### Storage Backend

```
STORAGE_BACKEND=local
```

or

```
STORAGE_BACKEND=s3
```

When `STORAGE_BACKEND=s3`, also set:

```
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name
```

---

### Vector Store

```
VECTOR_STORE_BACKEND=faiss
```

or

```
VECTOR_STORE_BACKEND=pgvector
```

When `VECTOR_STORE_BACKEND=pgvector`, also set:

```
PGVECTOR_CONNECTION_STRING=postgresql+psycopg2://user:password@localhost:5432/ragdb
```

**Note:** FAISS is file-based and cached in memory per process, so it only
behaves correctly with a single instance backed by a single persistent
disk. If you deploy behind a load balancer with more than one instance,
use `pgvector` instead - otherwise each instance gets its own index and
concurrent writes can race. See "Production Deployment" below.

---

### Security & Limits

```
ENVIRONMENT=development        # "production" enables strict startup checks
JWT_SECRET_KEY=                # required in production - no random fallback
FRONTEND_URL=*                 # comma-separated allowed CORS origins; "*" only for dev
MAX_UPLOAD_SIZE_MB=20           # uploads over this are rejected (413) before being fully read
RATE_LIMIT_AUTH=10/minute       # applied to /auth/login and /auth/register
RATE_LIMIT_UPLOAD=20/minute
RATE_LIMIT_CHAT=30/minute
```

When `ENVIRONMENT=production`, the app refuses to start if `JWT_SECRET_KEY`
is blank or `FRONTEND_URL` is still `*` - this is intentional, since either
one running unnoticed in production is a real security gap, not just a
warning worth logging.

---

# Getting Started

## Clone Repository

```bash
git clone https://github.com/<your-username>/docpilot.git
cd docpilot
```

---

## Create Virtual Environment

```bash
python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Linux/macOS

```bash
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Environment

Create a `.env` file (or copy `.env.example`).

Example:

```env
GOOGLE_API_KEY=your_api_key

JWT_SECRET_KEY=your_secret

VECTOR_STORE_BACKEND=faiss

STORAGE_BACKEND=local
```

---

## Run Tests

```bash
pip install pytest
pytest
```

Tests run fully offline (embedding/LLM calls are mocked) and cover filename
sanitization, auth, upload validation, and cross-user data isolation.

---

## Run

```bash
uvicorn app.main:app --reload
```

Swagger UI

```
http://localhost:8000/docs
```

---

# Docker

Build

```bash
docker compose build
```

Run

```bash
docker compose up
```

---

# Production Deployment

For a real multi-user deployment (not a single-machine demo), the
recommended architecture is:

```
                   +---------------+
                   |   Frontend    |
                   +-------+-------+
                           |
                         HTTPS
                           |
                   +-------v-------+
                   |    FastAPI    |
                   +-------+-------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          PostgreSQL       S3          Gemini
          + pgvector    documents      API
             |
             v
        Chat history
        users
        document records
        embeddings
```

Recommended production settings:

```
ENVIRONMENT=production
STORAGE_BACKEND=s3
VECTOR_STORE_BACKEND=pgvector
APP_DB_URL=postgresql+psycopg2://...
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
JWT_SECRET_KEY=<a real, long, random secret - generate once and keep fixed>
FRONTEND_URL=https://your-frontend.example.com
```

Other things worth doing before a real launch, beyond what this codebase
enforces automatically:

- **Migrations**: the app currently calls `Base.metadata.create_all(...)`
  at startup, which is fine for a first deploy but not for evolving an
  existing production database. Introduce [Alembic](https://alembic.sqlalchemy.org/)
  once the schema needs to change under real data.
- **AWS credentials**: prefer an IAM role/service identity over long-lived
  `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` values where your hosting
  platform supports it, scoped to only the S3 bucket/actions this app needs.
- **FAISS trust boundary**: `FAISS.load_local(..., allow_dangerous_deserialization=True)`
  is safe as long as the index files were only ever written by this
  application - treat `FAISS_INDEX_BASE_DIR` as trusted application data,
  not something to accept from outside the app.

---

# Future Improvements

- Web-based React frontend
- Streaming AI responses
- Redis caching
- Role-based access control
- Hybrid search
- Support for additional LLM providers
- Background job queue (Celery/RQ) for upload processing at scale
- Alembic migrations

---

# Learning Outcomes

This project demonstrates practical implementation of:

- FastAPI
- REST APIs
- JWT Authentication
- LangChain
- Retrieval-Augmented Generation (RAG)
- Prompt Engineering
- Vector Databases
- Embedding Models
- Semantic Search
- Multi-user Architecture
- Structured Logging
- AWS S3 Integration
- Docker-based Deployment

---

# License

This project is intended for educational and portfolio purposes.
