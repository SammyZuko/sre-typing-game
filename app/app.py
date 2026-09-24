import os
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from wonderwords import RandomSentence
import psycopg2
from psycopg2 import pool

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config (all overridable via environment variables for container deploys)
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "typinggame")
DB_USER = os.environ.get("DB_USER", "typinggame")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "typinggame")

sentence_generator = RandomSentence()

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["endpoint"]
)
GAME_SESSIONS_STARTED = Counter(
    "game_sessions_started_total", "Typing game sessions started"
)
GAME_SESSIONS_COMPLETED = Counter(
    "game_sessions_completed_total", "Typing game sessions completed"
)
GAME_WPM = Histogram(
    "game_wpm", "Distribution of words-per-minute scores",
    buckets=(10, 20, 30, 40, 50, 60, 80, 100, 150, 200),
)

# ---------------------------------------------------------------------------
# DB connection pool (lazy — app should still boot if DB is briefly down)
# ---------------------------------------------------------------------------
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            1, 5,
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
        )
    return _pool


def init_db():
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    player_name TEXT,
                    wpm NUMERIC NOT NULL,
                    accuracy NUMERIC NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
        conn.commit()
    finally:
        get_pool().putconn(conn)


# ---------------------------------------------------------------------------
# Middleware: measure every request
# ---------------------------------------------------------------------------
@app.before_request
def _start_timer():
    request._start_time = time.time()


@app.after_request
def _record_metrics(response):
    if request.path == "/metrics":
        return response
    duration = time.time() - getattr(request, "_start_time", time.time())
    endpoint = request.endpoint or "unknown"
    HTTP_REQUEST_DURATION.labels(endpoint=endpoint).observe(duration)
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method, endpoint=endpoint, status=response.status_code
    ).inc()
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/prompt")
def api_prompt():
    GAME_SESSIONS_STARTED.inc()
    # Generate 2-3 sentences strung together so prompts aren't too short
    prompt = " ".join(sentence_generator.sentence() for _ in range(2))
    return jsonify({"prompt": prompt})


@app.route("/api/score", methods=["POST"])
def api_score():
    data = request.get_json(force=True, silent=True) or {}
    wpm = data.get("wpm")
    accuracy = data.get("accuracy")
    player_name = (data.get("player_name") or "anonymous")[:64]

    if wpm is None or accuracy is None:
        return jsonify({"error": "wpm and accuracy are required"}), 400

    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (player_name, wpm, accuracy) VALUES (%s, %s, %s) RETURNING id, created_at;",
                (player_name, wpm, accuracy),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        get_pool().putconn(conn)

    GAME_SESSIONS_COMPLETED.inc()
    GAME_WPM.observe(float(wpm))

    return jsonify(
        {
            "id": row[0],
            "player_name": player_name,
            "wpm": wpm,
            "accuracy": accuracy,
            "created_at": row[1].astimezone(timezone.utc).isoformat(),
        }
    ), 201


@app.route("/api/leaderboard")
def api_leaderboard():
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT player_name, wpm, accuracy, created_at FROM sessions "
                "ORDER BY wpm DESC LIMIT 10;"
            )
            rows = cur.fetchall()
    finally:
        get_pool().putconn(conn)

    return jsonify(
        [
            {
                "player_name": r[0],
                "wpm": float(r[1]),
                "accuracy": float(r[2]),
                "created_at": r[3].astimezone(timezone.utc).isoformat(),
            }
            for r in rows
        ]
    )


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
else:
    # Also init when run under gunicorn
    try:
        init_db()
    except Exception as e:  # noqa: BLE001
        app.logger.warning("DB init deferred: %s", e)
