#!/usr/bin/env python3
"""
Code review agent: heuristic checks always; optional AI review when OPENAI_API_KEY is set.
Reads a PR diff, runs checks, writes a single Markdown review to --output.
"""
import argparse
import os
import re
import sys
from pathlib import Path


# Heuristic patterns: (pattern, label, severity)
HEURISTIC_PATTERNS = [
    (r"\bconsole\.(log|debug|info|warn|error)\s*\(", "console.* call", "warning"),
    (r"\bdebugger\s*;?", "debugger statement", "warning"),
    (r"\b(TODO|FIXME|XXX|HACK)\b", "TODO/FIXME", "info"),
    (r"\b(eval|exec)\s*\(", "eval/exec", "security"),
    (r"except\s*:\s*(?:pass|\s*\.\.\.)?\s*$", "empty except", "warning"),
    (r"except\s+Exception\s*:\s*(?:pass|\s*\.\.\.)?\s*$", "bare Exception pass", "warning"),
    (r"\.(innerHTML|outerHTML)\s*=", "innerHTML/outerHTML assignment", "security"),
    (r"(?i)(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+['\"]", "possible hardcoded secret", "security"),
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "possible hardcoded token", "security"),
]


def run_heuristic_review(diff_text: str) -> str:
    """Run heuristic checks on the diff and return Markdown report."""
    lines = diff_text.splitlines()
    findings = []
    for i, line in enumerate(lines, 1):
        # Only inspect added lines (start with + but not +++).
        if not line.startswith("+") or line.startswith("+++"):
            continue
        code = line[1:]
        for pattern, label, severity in HEURISTIC_PATTERNS:
            if re.search(pattern, code):
                findings.append((i, label, severity, code.strip()[:80]))

    if not findings:
        return "## Heuristic review\n\nNo issues found by heuristic checks.\n"

    by_severity = {"security": [], "warning": [], "info": []}
    for line_no, label, severity, snippet in findings:
        by_severity[severity].append((line_no, label, snippet))

    out = ["## Heuristic review", ""]
    for sev in ("security", "warning", "info"):
        items = by_severity.get(sev, [])
        if not items:
            continue
        out.append(f"### {sev.capitalize()}")
        out.append("")
        for line_no, label, snippet in items:
            out.append(f"- **Line {line_no}** ({label}): `{snippet}`")
        out.append("")
    return "\n".join(out)


def run_ai_review(diff_text: str, api_key: str) -> str:
    """Call OpenAI to generate a short review. Returns Markdown."""
    try:
        from openai import OpenAI
    except ImportError:
        return "## AI review\n\n`openai` package not installed; run `pip install openai` for AI review.\n"

    client = OpenAI(api_key=api_key)
    # Cap diff size to avoid token limits.
    max_chars = 12000
    if len(diff_text) > max_chars:
        diff_text = diff_text[:max_chars] + "\n\n... (diff truncated)\n"

    prompt = """Review this pull request diff. Write a short Markdown report (use headers) covering:
- Correctness: obvious bugs or logic errors
- Security: sensitive data, injection, unsafe patterns
- Performance: obvious inefficiencies
- Style: consistency and clarity

Keep the review concise and actionable. If there are no significant issues, say so briefly.

Diff:
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a code reviewer. Reply only with the review in Markdown."},
                {"role": "user", "content": prompt + diff_text},
            ],
            max_tokens=1500,
        )
        text = (resp.choices[0].message.content or "").strip()
        return "## AI review\n\n" + text if text else "## AI review\n\nNo review generated.\n"
    except Exception as e:
        return f"## AI review\n\nError calling OpenAI: {e}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run code review on a PR diff.")
    parser.add_argument("--diff", required=True, help="Path to file containing the PR diff.")
    parser.add_argument("--output", required=True, help="Path to write the Markdown review.")
    args = parser.parse_args()

    diff_path = Path(args.diff)
    if not diff_path.exists():
        print(f"Diff file not found: {diff_path}", file=sys.stderr)
        sys.exit(1)

    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    if not diff_text.strip():
        review = "## Code review\n\nNo diff to review (empty or no changes).\n"
    else:
        heuristic = run_heuristic_review(diff_text)
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if api_key:
            ai = run_ai_review(diff_text, api_key)
            review = heuristic + "\n---\n\n" + ai
        else:
            review = heuristic + "\n\n*Set `OPENAI_API_KEY` in repo Secrets for AI review.*\n"

    Path(args.output).write_text(review, encoding="utf-8")
    print("Review written to", args.output)


if __name__ == "__main__":
    main()
