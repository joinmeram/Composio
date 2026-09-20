# Composio 100-App Research Orchestrator

Agentic research pipeline for the Composio AI Product Ops Intern take-home. For each
of the 100 apps in the assignment, the agent researches: category and one-liner, auth
method(s), self-serve vs gated access, API surface (REST/GraphQL, breadth), existing
MCP support, a buildability verdict, the main blocker if any, and evidence URLs for
every claim.

**Live case study:** [](file:///C:/Users/rk336/AppData/Local/Temp/002dd683-5e7f-467c-8596-b368353aeb4d_composio-research-repo.zip.b4d/composio-research/case_study.html)

## Status: pipeline fixed and confirmed running, data still at n=5

5 of 100 apps researched, 1 independently verified. The pipeline itself is debugged
and working correctly — three real bugs (below) were caught, fixed, and confirmed
running before scaling up. Completing the 100-app run is now blocked on API credit,
not on further engineering. `case_study.html` states this plainly up front.

The **implementation described below (`src/`)** is a from-scratch Python version of
this pipeline, written to run on Composio's own SDK. The **actual data in
`case_study.html`** came from an n8n-based pipeline (workflow exports in
`workflows_composio_*.json`) built with Claude + Tavily search + Google Sheets as the
data store — that's what was actually run to produce the 5 researched / 1 verified
rows. The `src/` pipeline is the intended path forward once credits allow a full
100-app run: it does the same search → fetch → synthesize → validate → repair loop,
but through Composio's hosted toolkits instead of n8n + Tavily.

## Bugs found and fixed

Caught by manually diffing a small batch before trusting the pipeline at scale —
which is exactly why it was still at n=5 when these surfaced.

1. **Row mislabeling.** The write-back step originally used
   `{{ $('Loop Over Items').first(1, $runIndex).json.id }}` to look up which app a
   loop iteration belonged to — not valid n8n usage for indexing into a loop, so the
   label (app name / id) written back got misaligned with the researched content.
   **Fixed** with an `Edit Fields` node that snapshots `id`/`app`/`category`/`hint_url`
   before the AI Agent runs, and a `Merge (combine by position)` node that reattaches
   them afterward — the model never sees or echoes these values at all now, so it
   can't mislabel them.
2. **Verification accuracy silently reporting 0%.** The comparison code looked for
   sheet columns named `verification_<field>`; the actual headers were typo'd as
   `verifcation_<field>` (missing "i"), so every lookup returned `undefined` and every
   field counted as a mismatch regardless of whether the agent was actually right.
   **Fixed** — headers corrected, and the comparison now excludes free-text fields
   (description, blocker, credential acquisition) from the accuracy count entirely,
   since two independent model runs will always word those differently.
3. **`auth_methods` fragmenting on comma-split.** The agent was returning full
   sentences inside the array instead of short tokens, so pattern analysis split one
   real auth method into several fake ones. **Fixed** at the prompt level — controlled
   vocabulary only (OAuth2 / API Key / Basic Auth / Token / Other), with a separate
   `auth_notes` field for the nuance.

## How it works

For each app (`src/orchestrate.py`):
1. **Search** official docs for auth / API / MCP (`research_tool.py`, Composio-backed
   by default — set `COMPOSIO_API_KEY` to use Composio's hosted search/browse toolkits;
   falls back to plain `requests`/`trafilatura` otherwise).
2. **Fetch** the top candidate pages.
3. **Synthesize** a structured `AppResult` (`schema.py`) via an LLM call, grounded
   strictly in the fetched text.
4. **Validate** (`validate.py`) — checks every claim actually has cited evidence, that
   evidence excerpts really appear in the fetched content (catches hallucinated
   quotes/URLs), and that claims aren't internally contradictory (e.g. "self-serve"
   next to "requires partnership approval").
5. **Repair** — if validation fails, the agent re-searches *only the failing fields*
   and re-synthesizes. Bounded to 2 attempts to avoid endless loops.
6. **Checkpoint** — saves `src/results/<app>.json`. Reruns skip apps that already have
   a checkpoint (`--force` to redo).

## Running it

```bash
cd src
pip install -r ../requirements.txt

export COMPOSIO_API_KEY=...      # for hosted search/browse
export ANTHROPIC_API_KEY=...     # for the synthesis LLM call

python -m orchestrate --app Salesforce
python -m orchestrate --app Salesforce --app HubSpot --app Slack
python -m orchestrate --limit 10       # next 10 un-researched apps
python -m orchestrate --limit 100      # the whole set
```

Without `COMPOSIO_API_KEY`, `research_tool.py` falls back to a plain-`requests`
fetcher (no search backend — you'd need to wire in a search API key, or pass known
hint URLs directly) — useful for local testing but the intended path is Composio's
own SDK, in the spirit of the assignment.

## Human verification

```bash
python -m verify --sample 15          # pick a random sample of researched apps
python -m verify --record salesforce --field auth_methods --correct true
python -m verify --summary            # accuracy by field and overall
```

Results are logged to `src/verification/human_review.json` and drive the "verified
accuracy" numbers in the case study.

## Repository structure

```
composio-research/
├── README.md
├── requirements.txt
├── case_study.html          # the deliverable
└── src/
    ├── app_list.py           # the 100 apps
    ├── schema.py              # AppResult / Evidence dataclasses
    ├── research_tool.py       # pluggable search+fetch (Composio-backed)
    ├── llm_client.py          # synthesis LLM call
    ├── orchestrate.py         # main pipeline: search -> fetch -> synthesize -> validate -> repair
    ├── validate.py            # evidence-grounding checks
    ├── verify.py               # human verification harness
    ├── results/                # one JSON per app
    └── verification/
        └── human_review.json
```

## Human vs agent

The agent handles the repetitive parts: documentation discovery, fetching, structured
synthesis, evidence collection, self-validation, and targeted repair research. A human
is needed for: judgment calls on ambiguous gating language, independent verification
against real docs (the agent's validator only checks internal consistency with its own
fetched evidence, not ground truth), and the final pattern synthesis. Where the agent
got something wrong, it's reported honestly in the case study rather than smoothed over.
