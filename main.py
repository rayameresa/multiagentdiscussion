import json
import os
import sqlite3
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from ddgs import DDGS
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph


###############################################################################
# Configuration
###############################################################################

PROJECT_ROOT = Path(__file__).parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "almas.sqlite3"


def get_ollama_llm(model: str = "llama3") -> ChatOpenAI:
    """
    Create a ChatOpenAI client pointed at a local Ollama server.

    Ollama must be running with its OpenAI-compatible API enabled:
    - base_url: http://localhost:11434/v1
    - api_key: dummy value ("local-only") – never sent remotely.
    """
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    api_key = os.getenv("OLLAMA_API_KEY", "local-only")

    return ChatOpenAI(
        model=model,
        temperature=0.3,
        max_tokens=512,
        base_url=base_url,
        api_key=api_key,
    )


###############################################################################
# LangGraph state
###############################################################################


class GraphState(TypedDict, total=False):
    topics_raw: str
    topics: List[Dict[str, Any]]
    selected_topic: str
    debate_transcript: List[str]
    history_summaries: str


###############################################################################
# Phase 1: Signal Scouting (uses local DuckDuckGo search)
###############################################################################


def scout_trending_topics(state: GraphState) -> GraphState:
    """Use DuckDuckGo to gather a rough list of trending tech/science topics."""
    llm = get_ollama_llm()

    query = (
        "trending emerging technology or science breakthroughs 2025 2026, "
        "novel or controversial tech science topics"
    )
    results: List[Dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=8):
                results.append(
                    {
                        "title": r.get("title"),
                        "href": r.get("href"),
                        "body": r.get("body"),
                    }
                )
    except Exception:
        # Fallback if network/search fails so the cycle still completes.
        results = [
            {"title": "Frontier AI safety and alignment", "href": "", "body": "Safety practices for advancing AI models."},
            {"title": "Open-source foundation models", "href": "", "body": "Locally runnable, open-weight AI impact."},
            {"title": "Neurosymbolic AI", "href": "", "body": "Neural networks with symbolic reasoning."},
            {"title": "AI and climate resilience", "href": "", "body": "AI to model and adapt to climate change."},
            {"title": "Personal AI assistants", "href": "", "body": "Always-on local agents in daily life."},
        ]

    search_summary = json.dumps(results, ensure_ascii=False, indent=2)

    system_prompt = """You are a signal scout AI.
You are running in a long-lived autonomous system.
First, read the summary of recent debates to avoid repeating exactly the same focus.
Then, from the provided web search results, extract 5 candidate topics in technology or science.
For each topic assign:
- title (short)
- description (1–2 sentences)
- novelty_score (float 0–1, higher is more novel/uncertain)
Respond as pure JSON list (no extra text)."""

    msg = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                "Recent debate history (summaries):\n"
                f"{state.get('history_summaries', '(none yet)')}\n\n"
                f"New search results:\n{search_summary}"
            )
        ),
    ]
    resp = llm.invoke(msg)
    content = resp.content if isinstance(resp.content, str) else str(resp.content)

    topics: List[Dict[str, Any]] = []
    try:
        topics = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: wrap single topic
        topics = [{"title": "Fallback Topic", "description": content, "novelty_score": 0.5}]

    return {
        **state,
        "topics_raw": search_summary,
        "topics": topics,
    }


###############################################################################
# Phase 2: Topic Selection (Moderator)
###############################################################################


def moderator_select_topic(state: GraphState) -> GraphState:
    """Moderator chooses one topic based on novelty scores."""
    llm = get_ollama_llm()
    topics = state.get("topics") or []

    system_prompt = """You are a neutral moderator in a long-running research lab.
You are given a list of candidate topics, each with a novelty_score in [0, 1],
and a brief summary of recent debates this lab has already conducted.
Select exactly ONE topic for a debate, preferring higher novelty_score and clarity,
and either:
- explore a clearly new area the lab has not yet debated, or
- extend a prior debate in a non-repetitive way (different angle, implications, or applications).
Return JSON with:
- selected_title
- rationale (1–3 sentences)."""

    msg = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                "Recent debate history (summaries):\n"
                f"{state.get('history_summaries', '(none yet)')}\n\n"
                "Candidate topics:\n"
                f"{json.dumps(topics, ensure_ascii=False, indent=2)}"
            )
        ),
    ]
    resp = llm.invoke(msg)
    content = resp.content if isinstance(resp.content, str) else str(resp.content)

    try:
        parsed = json.loads(content)
        selected_title = parsed.get("selected_title") or topics[0]["title"]
    except Exception:
        selected_title = topics[0]["title"] if topics else "Underspecified Topic"

    return {
        **state,
        "selected_topic": selected_title,
    }


###############################################################################
# Phase 3: Multi-Agent Debate (3 turns each)
###############################################################################


def run_debate(state: GraphState) -> GraphState:
    """Run a 3-turn-per-side debate between two contrasting personas."""
    topic = state.get("selected_topic", "an unspecified topic")
    history = state.get("history_summaries", "")
    llm = get_ollama_llm()

    sys_optimist = textwrap.dedent(
        f"""
        You are The Techno-Optimist.
        You strongly believe that advances in technology are overwhelmingly positive.
        Debate about: "{topic}".
        You are working in a lab that has previously debated topics summarized below.
        Use that history to avoid repeating the exact same arguments; either build on them
        (by going deeper or applying them) or take a fresh angle.

        Recent debate history (summaries):
        {history}

        Argue enthusiastically for its benefits, scalability, and long‑term upside.
        Respond in 2–4 sentences, crisp and concrete.
        """
    ).strip()

    sys_skeptic = textwrap.dedent(
        f"""
        You are The Ethical Skeptic.
        You are cautious and focus on risks, equity, and unintended consequences.
        Debate about: "{topic}".
        You are working in a lab that has previously debated topics summarized below.
        Use that history to avoid repeating the exact same arguments; either build on them
        (by going deeper or applying them) or take a fresh angle.

        Recent debate history (summaries):
        {history}

        Respond in 2–4 sentences, highlighting trade‑offs, failure modes, and ethics.
        """
    ).strip()

    transcript: List[str] = []
    history: List[HumanMessage | SystemMessage] = []

    # Start with optimist opening
    history = [SystemMessage(content=sys_optimist)]
    resp = llm.invoke(history + [HumanMessage(content="Open the debate.")])
    optimist_utterance = resp.content if isinstance(resp.content, str) else str(resp.content)
    transcript.append(f"Techno-Optimist: {optimist_utterance}")

    # Alternating 3 turns each (optimist already spoke once)
    for turn in range(3):
        # Skeptic response
        skeptic_history = [
            SystemMessage(content=sys_skeptic),
            HumanMessage(
                content=f"The Techno-Optimist just said:\n{optimist_utterance}\n\nRespond briefly."
            ),
        ]
        resp_s = llm.invoke(skeptic_history)
        skeptic_utterance = resp_s.content if isinstance(resp_s.content, str) else str(resp_s.content)
        transcript.append(f"Ethical Skeptic: {skeptic_utterance}")

        if turn == 2:
            break

        # Optimist rebuttal
        optimist_history = [
            SystemMessage(content=sys_optimist),
            HumanMessage(
                content=f"The Ethical Skeptic just said:\n{skeptic_utterance}\n\nRespond briefly."
            ),
        ]
        resp_o = llm.invoke(optimist_history)
        optimist_utterance = resp_o.content if isinstance(resp_o.content, str) else str(resp_o.content)
        transcript.append(f"Techno-Optimist: {optimist_utterance}")

    return {
        **state,
        "debate_transcript": transcript,
    }


###############################################################################
# Phase 4: Archiving (Secretary -> SQLite)
###############################################################################


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS debates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                transcript TEXT NOT NULL,
                topics_json TEXT,
                topics_raw TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def archive_to_sqlite(state: GraphState) -> GraphState:
    """Secretary agent: persist the debate to a local SQLite database."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO debates (created_at, topic, transcript, topics_json, topics_raw)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(),
                state.get("selected_topic", "Unknown Topic"),
                "\n".join(state.get("debate_transcript") or []),
                json.dumps(state.get("topics") or [], ensure_ascii=False),
                state.get("topics_raw", ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return state


###############################################################################
# LangGraph workflow assembly
###############################################################################


def build_workflow():
    graph = StateGraph(GraphState)
    graph.add_node("scout", scout_trending_topics)
    graph.add_node("moderator", moderator_select_topic)
    graph.add_node("debate", run_debate)
    graph.add_node("archive", archive_to_sqlite)

    graph.set_entry_point("scout")
    graph.add_edge("scout", "moderator")
    graph.add_edge("moderator", "debate")
    graph.add_edge("debate", "archive")
    graph.add_edge("archive", END)

    return graph.compile()


###############################################################################
# Phase 5: Self-triggering loop
###############################################################################


def run_once() -> None:
    """Run a single end-to-end ALMAS cycle."""
    # Load a compact view of recent debates to provide long-term memory.
    history_summaries = ""
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                """
                SELECT created_at, topic, transcript
                FROM debates
                ORDER BY id DESC
                LIMIT 5
                """
            )
            rows = cur.fetchall()
            parts: List[str] = []
            for r in rows:
                created = r["created_at"]
                topic = r["topic"]
                # Take only the first couple of lines from the transcript for brevity.
                first_lines = (r["transcript"] or "").split("\n")[:2]
                snippet = " ".join(l.strip() for l in first_lines if l.strip())
                parts.append(f"- {created} — {topic}: {snippet}")
            history_summaries = "\n".join(parts)
        except Exception:
            history_summaries = ""
        finally:
            try:
                conn.close()
            except Exception:
                pass

    workflow = build_workflow()
    initial_state: GraphState = {"history_summaries": history_summaries}
    final_state = workflow.invoke(initial_state)

    # Also write a simple markdown snapshot alongside SQLite for human inspection.
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    topic = final_state.get("selected_topic", "Unknown Topic")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    md_path = DATA_DIR / f"debate_{ts}.md"
    transcript_lines = final_state.get("debate_transcript") or []
    md_content = f"# Debate on: {topic}\n\n" + "\n\n".join(transcript_lines) + "\n"
    md_path.write_text(md_content, encoding="utf-8")


def main() -> None:
    """Entry point: infinite autonomous loop with a sleep interval."""
    # Default to a shorter interval (5 minutes) for more interactive experimentation.
    # You can still override this via the ALMAS_INTERVAL_SECONDS environment variable.
    interval_seconds = int(os.getenv("ALMAS_INTERVAL_SECONDS", "300"))
    print(f"Starting ALMAS autonomous loop. Interval: {interval_seconds} seconds.")
    print(f"Database path: {DB_PATH}")

    while True:
        try:
            print(f"\n[{datetime.utcnow().isoformat()}] Starting new ALMAS cycle...")
            run_once()
            print(f"[{datetime.utcnow().isoformat()}] Cycle completed. Sleeping...")
        except Exception as e:
            print(f"Error during ALMAS cycle: {e}")

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()

