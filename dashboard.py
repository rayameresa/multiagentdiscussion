import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse


PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "almas.sqlite3"


app = FastAPI(title="ALMAS Dashboard", docs_url=None, redoc_url=None)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/", response_class=HTMLResponse)
def list_debates() -> str:
    """Simple HTML page listing recent debates."""
    if not DB_PATH.exists():
        return "<h1>ALMAS Dashboard</h1><p>No database found yet. Run <code>python main.py</code> to generate debates.</p>"

    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, topic
            FROM debates
            ORDER BY id DESC
            LIMIT 100
            """
        )
        rows = cur.fetchall()

    if not rows:
        return "<h1>ALMAS Dashboard</h1><p>No debates recorded yet.</p>"

    items = []
    for r in rows:
        created = r["created_at"]
        try:
            created_dt = datetime.fromisoformat(created)
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            created_str = created

        items.append(
            f"<li><a href='/debates/{r['id']}'><strong>{created_str}</strong> — {r['topic']}</a></li>"
        )

    items_html = "\n".join(items)
    html = (
        "<html>"
        "<head>"
        "<title>ALMAS Dashboard</title>"
        "<style>"
        "body { font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;"
        "       max-width: 800px; margin: 2rem auto; padding: 0 1rem; }"
        "h1 { margin-bottom: 0.5rem; }"
        ".subtitle { color: #555; margin-bottom: 1.5rem; }"
        "ul { list-style: none; padding-left: 0; }"
        "li { margin: 0.4rem 0; }"
        "a { text-decoration: none; color: #0366d6; }"
        "a:hover { text-decoration: underline; }"
        "code { background: #f4f4f4; padding: 0.1rem 0.25rem; border-radius: 3px; }"
        "</style>"
        "</head>"
        "<body>"
        "<h1>ALMAS Dashboard</h1>"
        '<div class="subtitle">Recent debates (newest first)</div>'
        "<ul>"
        f"{items_html}"
        "</ul>"
        '<p style="margin-top:2rem; font-size: 0.85rem; color:#777;">'
        "Data source: <code>data/almas.sqlite3</code>. "
        "Run <code>python main.py</code> in another terminal to keep generating debates."
        "</p>"
        "</body>"
        "</html>"
    )

    return html


# ---------------------------------------------------------------------------
# JSON API (new in this feature branch)
# ---------------------------------------------------------------------------

@app.get("/api/debates")
def api_list_debates(limit: int = Query(100, ge=1, le=500)) -> list:
    """
    Return recent debates as JSON: id, created_at, topic, transcript_length.
    Use ?limit=20 to cap the number of results.
    """
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Database not found. Run main.py first.")
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, topic,
                   LENGTH(transcript) AS transcript_length
            FROM debates
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "topic": r["topic"],
            "transcript_length": r["transcript_length"] or 0,
        }
        for r in rows
    ]


@app.get("/api/debates/{debate_id}")
def api_get_debate(debate_id: int) -> dict:
    """Return a single debate as JSON (id, created_at, topic, transcript)."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Database not found. Run main.py first.")
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, created_at, topic, transcript FROM debates WHERE id = ?",
            (debate_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Debate not found.")
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "topic": row["topic"],
        "transcript": row["transcript"] or "",
    }


@app.get("/api/stats")
def api_stats() -> dict:
    """
    Return aggregate stats: total_debates, latest_debate_at, avg_transcript_length.
    """
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="Database not found. Run main.py first.")
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_debates,
                MAX(created_at) AS latest_debate_at,
                AVG(LENGTH(transcript)) AS avg_transcript_length
            FROM debates
            """
        )
        row = cur.fetchone()
    return {
        "total_debates": row["total_debates"] or 0,
        "latest_debate_at": row["latest_debate_at"],
        "avg_transcript_length": round(row["avg_transcript_length"] or 0, 1),
    }


@app.get("/debates/{debate_id}", response_class=HTMLResponse)
def view_debate(debate_id: int) -> str:
    """Render a single debate transcript."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database not found.")

    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, topic, transcript
            FROM debates
            WHERE id = ?
            """,
            (debate_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Debate not found.")

    created = row["created_at"]
    try:
        created_dt = datetime.fromisoformat(created)
        created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        created_str = created

    # Transcripts are stored as plain text with speaker prefixes.
    transcript_html = "<br><br>".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in (row["transcript"] or "").split("\n")
        if line.strip()
    )

    html = f"""
    <html>
      <head>
        <title>Debate #{row['id']} - ALMAS</title>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
                 max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
          a {{ color: #0366d6; text-decoration: none; }}
          a:hover {{ text-decoration: underline; }}
          .meta {{ color: #555; margin-bottom: 1rem; }}
          .transcript {{ margin-top: 1.5rem; line-height: 1.6; }}
        </style>
      </head>
      <body>
        <p><a href="/">&larr; Back to list</a></p>
        <h1>{row['topic']}</h1>
        <div class="meta">Debate #{row['id']} • {created_str}</div>
        <div class="transcript">{transcript_html}</div>
      </body>
    </html>
    """
    return html

