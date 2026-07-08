# Snip — URL Shortener

A high-performance URL shortener built with **FastAPI** and **PostgreSQL**, engineered with a focus on query performance and deliberate schema design decisions.

**🔗 Live:** [web-production-03d95d.up.railway.app](https://web-production-03d95d.up.railway.app) &nbsp;·&nbsp; **API docs:** [/docs](https://web-production-03d95d.up.railway.app/docs)

> Deployed on Railway with a managed PostgreSQL instance.

---

## Features

- `POST /shorten` — accepts a long URL, returns a 6-character base62 slug
- `GET /:slug` — 301 redirect to original URL with atomic click count increment
- Click tracking — per-URL visit counter, incremented atomically on every redirect
- Auto-generated Swagger UI at `/docs` — no extra setup needed
- Clean web UI served directly from FastAPI via `StaticFiles`

---

## Tech Stack

| Layer | Choice |
|---|---|
| Framework | FastAPI + uvicorn |
| Database | PostgreSQL 16 |
| DB driver | psycopg2 |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Deployment | Railway |

---

## Schema Design

```sql
CREATE TABLE IF NOT EXISTS urls (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(6) UNIQUE,
    original_url TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    click_count  INTEGER DEFAULT 0
);
```

**Design decisions:**

**`slug VARCHAR(6) UNIQUE` — nullable (no NOT NULL)**
Slug is generated *after* insert (requires the auto-assigned `id` first), so the column must allow `NULL` during the brief window between `INSERT` and `UPDATE`. `UNIQUE` constraint allows multiple `NULL`s (Postgres treats NULLs as distinct), which avoids concurrent-insert collisions that would occur with a placeholder string approach.

**`UNIQUE` creates a free B-tree index**
No manual `CREATE INDEX` needed on `slug` — the `UNIQUE` constraint auto-creates a B-tree index (`urls_slug_key`), which is exactly what `GET /:slug` needs for sub-millisecond lookups.

**`TIMESTAMPTZ` over `TIMESTAMP`**
Stores timestamps in UTC internally and converts correctly on display regardless of server timezone — safer default for any production system.

---

## Base62 Encoding

Slugs are deterministically generated from the row's auto-incremented `id`:

```python
def encode_base62(num):
    num = (num * 3001) + 1_000_000_000
    base = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    slug = ""
    while num != 0:
        slug += base[num % 62]
        num //= 62
    return slug[::-1]
```

**Why `id * 3001 + 1,000,000,000` and not raw `id`?**

- **Offset (`1,000,000,000`)** — raw `id=1` encodes to a 1-character slug. Since `62^5 ≈ 916M`, an offset above that threshold guarantees every slug is **at least 6 characters**, keeping output length consistent.
- **Multiplier (`3001`, a prime)** — without it, consecutive IDs produce slugs differing only in the last character (`4c93 → 4c94 → 4c95`), making the sequence trivially guessable. The multiplier spreads changes across multiple character positions, making sequential enumeration non-obvious.

**Trade-off acknowledged:** This is *obfuscation*, not cryptographic security — a determined attacker with two known `(id, slug)` pairs can reverse-engineer the multiplier via modular arithmetic. True unpredictability requires a keyed hash (HMAC) or random generation with collision retry. For this use case, obfuscation is the right call (simpler, zero collision risk, no retry logic).

---

## `GET /:slug` — Atomic Redirect

The redirect endpoint does **one** DB round trip, not two:

```sql
UPDATE urls
SET click_count = click_count + 1
WHERE slug = %s
RETURNING original_url;
```

`UPDATE ... RETURNING` atomically increments the counter and fetches the URL in a single statement — no separate `SELECT` followed by `UPDATE`, which would introduce a race window under concurrent load.

---

## Performance Analysis

### Benchmark — `wrk` load test (50 concurrent connections, 15s)

```
wrk -t4 -c50 -d15s --latency http://127.0.0.1:8000/{slug}
```

| Metric | Value |
|---|---|
| Requests/sec | 191.04 |
| Avg latency | 288.74 ms |
| p50 | 213.30 ms |
| p75 | 403.98 ms |
| p90 | 659.40 ms |
| p99 | 1.18 s |

### EXPLAIN ANALYZE — slug lookup query

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE urls SET click_count = click_count + 1
WHERE slug = '15FVf4' RETURNING original_url;
```

```
Update on urls  (actual time=0.056..0.057 rows=1)
  Buffers: shared hit=4
  -> Bitmap Heap Scan  (actual time=0.030..0.031 rows=1)
       -> Bitmap Index Scan on urls_slug_key  (actual time=0.018..0.018)
            Index Cond: (slug = '15FVf4')

Execution Time: 0.086 ms
```

### Finding — bottleneck is connection overhead, not the query

| Layer | Time |
|---|---|
| DB query (EXPLAIN ANALYZE) | **0.086 ms** |
| HTTP avg latency (wrk) | **288.74 ms** |

The query completes in **0.086ms** via `Bitmap Index Scan` on the auto-created UNIQUE index.
The ~288ms HTTP latency is entirely from **per-request `psycopg2.connect()` calls** — each of the 50 concurrent requests opened a fresh TCP connection to Postgres (authentication + backend process handshake).

**Production fix:** Connection pooling (`psycopg2.pool.ThreadedConnectionPool` or `asyncpg`).
With pooling, expected latency: **< 10ms** — the 0.086ms query cost is what actually remains.

---

## Local Setup

**Prerequisites:** Python 3.10+, PostgreSQL 16

```bash
# 1. Clone
git clone https://github.com/singh-himanshu3/URL-Shortener.git
cd URL-Shortener

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the table (connect to your Postgres instance)
psql -U postgres -c "
CREATE TABLE IF NOT EXISTS urls (
    id           SERIAL PRIMARY KEY,
    slug         VARCHAR(6) UNIQUE,
    original_url TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    click_count  INTEGER DEFAULT 0
);"

# 5. Set environment variable (or update database.py directly for local dev)
export DATABASE_URL="dbname=postgres user=postgres password=yourpassword host=localhost"

# 6. Run
uvicorn main:app --workers 4
```

Open `http://localhost:8000` for the UI, `http://localhost:8000/docs` for Swagger.

---

## API Reference

### `POST /shorten`
```json
// Request
{ "url": "https://example.com/very/long/path" }

// Response 200
{ "slug": "15FUsF", "original_url": "https://example.com/very/long/path" }
```

### `GET /:slug`
Redirects to original URL with HTTP 301.
Increments `click_count` atomically.
Returns HTTP 404 if slug not found.

---

## Project Structure

```
.
├── main.py          # FastAPI app, routes, base62 encoder
├── models.py        # Pydantic request model (URLRequest)
├── database.py      # psycopg2 connection + get_db() dependency
├── requirements.txt
└── static/
    └── index.html   # Frontend UI (vanilla HTML/CSS/JS)
```
