# Code Review Agent – Integration & Customization

This repo includes a **Code Review Agent** that runs on every pull request and posts (or updates) a single PR comment with the review.

## What you have

| Item | Description |
|------|-------------|
| **`.github/workflows/code-review.yml`** | Runs on every PR (opened, updated, reopened). Checks out the repo, builds the PR diff, runs the review script, then posts or updates one PR comment. |
| **`scripts/code-review-agent.py`** | Without `OPENAI_API_KEY`: runs heuristic checks (e.g. `console.log`, `debugger`, TODO/FIXME, possible hardcoded secrets, `eval`, empty `catch`/`except`, `innerHTML`). With `OPENAI_API_KEY`: sends the diff to OpenAI (e.g. gpt-4o-mini) and adds an AI-generated review (correctness, security, performance, style). |
| **`CODE_REVIEW_INTEGRATION.md`** | This step-by-step integration and customization guide. |

## How to integrate

### 1. Copy into your GitHub repo

Ensure your repo contains:

- `.github/workflows/code-review.yml`
- `scripts/code-review-agent.py`

Commit and push to the branch you use for PRs (e.g. `main`). The workflow will run on subsequent PRs.

### 2. Optional – AI reviews

- In the repo: **Settings → Secrets and variables → Actions**.
- Add a secret: **Name** `OPENAI_API_KEY`, **Value** = your OpenAI API key.
- No workflow change is needed; the script uses it when present.

### 3. Use it

Open or update a PR. The **Code Review Agent** workflow runs and posts (or updates) a comment with the review.

The workflow uses the default `GITHUB_TOKEN` and requests `contents: read` and `pull-requests: write`, so it can read the diff and post the comment. No extra app or bot setup is required.

---

## Customization

### Triggers

Edit `on` in `.github/workflows/code-review.yml`:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]   # add/remove as needed
```

To run on push to specific branches instead of (or in addition to) PRs, add:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened]
  push:
    branches: [main]
```

### Model and prompt (AI review)

In `scripts/code-review-agent.py`:

- **Model**: change `model="gpt-4o-mini"` in `run_ai_review()` to another model (e.g. `gpt-4o`) if desired.
- **Prompt**: edit the `prompt` string in `run_ai_review()` to ask for different aspects (e.g. docs, tests, accessibility).

### Heuristic checks

In `scripts/code-review-agent.py`, the `HEURISTIC_PATTERNS` list holds `(regex, label, severity)` tuples. Add or remove patterns, e.g.:

```python
(r"\byour_pattern\b", "Description", "warning"),  # severity: security | warning | info
```

### Diff size limit

The script truncates the diff sent to OpenAI to avoid token limits. In `run_ai_review()`, change `max_chars = 12000` to a different value if needed.

### Comment marker

The workflow finds the bot’s comment by a unique marker in the body. In the workflow, the marker is `<!-- code-review-agent -->`. If you change it, update both the workflow step that builds `body` and the script constant `COMMENT_MARKER` if you use it elsewhere.

---

## Troubleshooting

- **Workflow doesn’t run**  
  Ensure the workflow file is on the branch that is the **base** of the PR (usually `main`). PRs target that branch, so the workflow is taken from there.

- **No comment or “resource not accessible”**  
  Check that the job has `pull-requests: write` under `permissions` in the workflow.

- **AI section says “openai package not installed”**  
  The workflow step **Install review dependencies** runs `pip install openai`. If you run the script locally, install it yourself: `pip install openai`.

- **Heuristic only, no AI**  
  Add the `OPENAI_API_KEY` secret in the repo’s Actions secrets. The script uses AI only when that env var is set.
