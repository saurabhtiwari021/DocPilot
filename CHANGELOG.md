# Changelog - Deployability & Security Pass

Changes made against the pre-deployment audit, in the audit's own order.
Item numbers match the audit document.

## Fixed

**1. Broken Gemini embedding model**
`GEMINI_EMBEDDING_MODEL` default changed from the shut-down
`models/text-embedding-004` to `gemini-embedding-001` (`.env.example` and
`app/config/settings.py`). Note included: any existing FAISS/pgvector
index was built in the old embedding space and must be rebuilt, not reused.

**2. Filename path traversal**
New `app/services/filenames.py::safe_filename()` strips directory
components and unsafe characters from every uploaded filename before it's
used to build a filesystem path or S3 key. Applied in `upload.py` (first
use) and again defensively inside `storage_service.save_file()`.

**3. Unlimited upload size**
`upload.py` now reads the request body in bounded chunks and aborts with
`413` as soon as it exceeds `MAX_UPLOAD_SIZE_MB` (default 20), instead of
buffering the entire file into memory with a bare `await file.read()`.

**4. Duplicate filename / stale-vector re-upload bug**
New `app/services/document_registry.py` (`DocumentRecord` table) tracks,
per user + filename, the content hash and vector-store chunk ids currently
indexed. On re-upload: identical content is skipped (no re-embedding);
changed content has its old chunks deleted from the vector store *before*
the new ones are added. `vectorstore_service.add_documents()` now returns
the ids it created; a new `delete_documents()` removes ids by id.

**5. FAISS not multi-instance safe**
No code change (this is inherent to a local file-based index) - documented
in the README's new "Production Deployment" section: use
`VECTOR_STORE_BACKEND=pgvector` for anything with more than one instance.

**6. Production architecture**
Documented in the README ("Production Deployment" section): Postgres +
pgvector, S3, `ENVIRONMENT=production`.

**7. Blocking calls inside async routes**
`rag_service.get_answer()` now runs `chain.invoke(...)` via
`asyncio.to_thread`. `upload.py` runs file save, document parsing, and
vector store add/delete the same way, so a large upload or a slow LLM
call no longer blocks other requests on the same worker.

**8. Overly permissive CORS**
`app/main.py` now builds `allow_origins` from `FRONTEND_URL` (comma
separated), and narrows `allow_methods`/`allow_headers` from `["*"]` to
what the API actually uses. `FRONTEND_URL=*` still works for local dev.

**9. JWT secret fallback**
`jwt_secret_key` no longer defaults to `secrets.token_urlsafe(32)`. A new
`ensure_production_safety()` check (called at startup in `app/main.py`)
raises and refuses to start if `ENVIRONMENT=production` and the secret is
blank; in development it logs a warning and uses a per-process secret so
local runs still work without any setup. `.env.example`'s JWT secret
placeholder replaced with `CHANGE_ME_TO_A_LONG_RANDOM_SECRET`.

**10. Internal errors leaked to clients**
Every `raise HTTPException(..., detail=str(exc))` / f-string-with-exception
pattern (`chat.py`, `upload.py`, `documents.py`, `history.py`) replaced with
a fixed, generic detail message. The real exception is still logged
server-side with `exc_info=True`.

**11. No rate limiting**
Added `slowapi`. `/auth/login`, `/auth/register`, `/upload`, `/chat` are
now rate-limited per client IP (`RATE_LIMIT_AUTH`, `RATE_LIMIT_UPLOAD`,
`RATE_LIMIT_CHAT` in `.env`).

**13. S3 listing not paginated**
`storage_service.list_documents()` and `sync_cache_from_s3()` now use
boto3's `list_objects_v2` paginator instead of a single unpaginated call,
so a user with 1000+ stored files is listed/synced completely.

**17. Unpinned Postgres image**
`docker-compose.yml`: `ankane/pgvector:latest` -> `ankane/pgvector:v0.5.1`.

## Documented, not code-changed

**12. SQLite/no migrations** - noted in the README; introducing Alembic is
listed under "Production Deployment" and "Future Improvements" rather than
done here, since it's a schema-management decision best made once the
production schema is stable.

**14. `allow_dangerous_deserialization=True`** - kept, since in this
architecture the index files are only ever written by this application;
noted explicitly in the README as a trust boundary to preserve (don't let
`FAISS_INDEX_BASE_DIR` become externally writable).

**16. No frontend included** - unchanged; this audit/pass was scoped to
the FastAPI backend in the provided archive.

## Added

- `tests/` - a new offline test suite (`pytest`, embedding/LLM calls
  mocked out): filename sanitization, auth flows, upload validation
  (bad extension, oversized file, dedup, stale-chunk cleanup on
  re-upload), and cross-user data isolation. 22 tests, all passing.
- `app/rate_limit.py` - shared `slowapi` limiter instance.
- `app/services/filenames.py`, `app/services/document_registry.py` - see
  items 2 and 4 above.
- README: "Production Deployment" and "Run Tests" sections; expanded
  "Configuration" section documenting the new env vars.

## Verified in this environment

- `python -m compileall` passes over the full `app/` and `tests/` tree.
- `pip install -r requirements.txt` succeeds (PyPI was reachable here).
- `pytest` - 22/22 passing.
- Manually exercised `ensure_production_safety()`: confirmed it raises in
  `ENVIRONMENT=production` with a blank JWT secret or `FRONTEND_URL=*`,
  and only warns (without raising) in development.

Not verified here (no Docker CLI and no outbound package-index
connectivity for a full container build in this sandbox, same limitation
noted in the original audit): a full `docker compose build && up` boot
end-to-end. The Dockerfile and compose file are unchanged apart from the
version pin, so this should build the same way it did before.
