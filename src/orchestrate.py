"""
Composio 100-App Research Orchestrator.

Pipeline per app:
  1. search()   -> find official docs for auth / API / MCP
  2. fetch()    -> pull raw page content for the best candidate URLs
  3. synthesize()-> LLM call that turns fetched text into a structured AppResult
  4. validate() -> checks the LLM's claims against the fetched evidence
  5. repair()   -> if validation fails, do targeted re-search on just the failing
                   field(s) and re-synthesize (bounded to MAX_REPAIR_ATTEMPTS)
  6. checkpoint -> save src/results/<app>.json so reruns skip completed apps

Research/browsing is done through a pluggable ResearchTool. In production this
is backed by Composio's own SDK: a hosted web-search toolkit
(e.g. COMPOSIO_SEARCH / TAVILY) for `search()`, and a browser-use-style
toolkit for `fetch()` on pages that need JS rendering. Swap the
CompositoResearchTool implementation below for whichever toolkits your
Composio project has enabled -- the orchestrator logic doesn't change.
"""

import argparse
import json
import os
import time
from dataclasses import asdict

from app_list import APPS
from schema import AppResult, Evidence
from validate import validate_result
from research_tool import ResearchTool  # pluggable: Composio-backed or local

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
MAX_REPAIR_ATTEMPTS = 2


SYNTHESIS_PROMPT = """You are researching an app for an AI-agent integration platform.

App: {app}
Category: {category}
Hint URL: {hint}

Here is fetched content from official documentation / marketing pages:
---
{fetched_content}
---

Based ONLY on the content above, return a JSON object with these fields:
- one_liner: what the app does, one sentence
- auth_methods: list, subset of ["OAuth2", "API Key", "Basic Auth", "Token", "Other", "None found"]
- self_serve: true if a developer can get credentials themselves for free/trial, false if it
  requires paid plan / admin approval / partnership / contact-sales, null if unclear
- access_notes: short note on the gating (e.g. "free dev sandbox", "requires paid plan + approval")
- api_surface: "REST", "GraphQL", "REST + GraphQL", or "none found"
- api_breadth: "broad" (many resources/endpoints), "narrow" (limited), or "unknown"
- mcp_support: true / false / null
- mcp_notes: short note, e.g. "official MCP server at docs.devin.ai/mcp"
- buildability: "ready today", "buildable with workaround", or "blocked"
- main_blocker: short phrase, "" if none
- evidence: list of {{"claim": "<field name>", "url": "<source url>", "excerpt": "<=300 char quote
  from the fetched content above that supports the claim>"}}

Only claim what the fetched content actually supports. If the content doesn't answer a field,
use null/"unknown"/"none found" rather than guessing. Return ONLY the JSON object.
"""


def synthesize(app, category, hint, fetched_content, llm_call):
    prompt = SYNTHESIS_PROMPT.format(
        app=app, category=category, hint=hint, fetched_content=fetched_content[:12000]
    )
    raw = llm_call(prompt)
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    evidence = [Evidence(**e) for e in data.pop("evidence", [])]
    return AppResult(app=app, category=category, evidence=evidence, **data)


def research_app(app, category, hint, tool: ResearchTool, llm_call):
    # 1. search + fetch
    queries = [
        f"{app} API documentation authentication",
        f"{app} developer API self-serve OR sandbox OR free trial",
        f"{app} MCP server model context protocol",
    ]
    urls = []
    for q in queries:
        urls.extend(tool.search(q, max_results=3))
    urls = list(dict.fromkeys(urls))[:6]  # dedupe, cap

    fetched = []
    for url in urls:
        try:
            fetched.append(f"URL: {url}\n{tool.fetch(url)}")
        except Exception as e:
            fetched.append(f"URL: {url}\n[fetch failed: {e}]")
    fetched_content = "\n\n---\n\n".join(fetched)

    # 2. synthesize
    result = synthesize(app, category, hint, fetched_content, llm_call)

    # 3. validate + repair loop
    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        failures = validate_result(result, fetched_content)
        if not failures:
            result.validation_status = "passed"
            result.research_pass = attempt
            break
        result.validation_status = "failed"
        result.validation_failures = failures
        result.research_pass = attempt

        if attempt == MAX_REPAIR_ATTEMPTS:
            break  # give up, keep last result flagged as failed

        # targeted repair: re-search only for the failing fields
        repair_queries = [f"{app} {field_name} site:{hint.split('/')[0]}" for field_name in failures]
        repair_urls = []
        for q in repair_queries:
            repair_urls.extend(tool.search(q, max_results=2))
        for url in dict.fromkeys(repair_urls):
            try:
                fetched_content += f"\n\n---\n\nURL: {url}\n{tool.fetch(url)}"
            except Exception:
                pass
        result = synthesize(app, category, hint, fetched_content, llm_call)

    return result


def load_checkpoint(app):
    path = os.path.join(RESULTS_DIR, f"{slug(app)}.json")
    if os.path.exists(path):
        with open(path) as f:
            return AppResult.from_dict(json.load(f))
    return None


def slug(app):
    return app.lower().replace(" ", "_").replace("(", "").replace(")", "").replace(".", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", action="append", help="Research a specific app (repeatable)")
    parser.add_argument("--limit", type=int, help="Research the first N un-checkpointed apps")
    parser.add_argument("--force", action="store_true", help="Re-research even if checkpoint exists")
    args = parser.parse_args()

    from research_tool import make_default_tool
    from llm_client import call_llm  # thin wrapper around Composio-hosted or Anthropic model call

    tool = make_default_tool()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    targets = APPS
    if args.app:
        wanted = {a.lower() for a in args.app}
        targets = [t for t in APPS if t[0].lower() in wanted]
    if args.limit:
        targets = [t for t in targets if args.force or load_checkpoint(t[0]) is None][: args.limit]

    for app, category, hint in targets:
        if not args.force and load_checkpoint(app) is not None:
            print(f"[skip] {app} (checkpoint exists)")
            continue
        print(f"[research] {app} ...")
        try:
            result = research_app(app, category, hint, tool, call_llm)
        except Exception as e:
            print(f"  ERROR researching {app}: {e}")
            continue
        result.save(os.path.join(RESULTS_DIR, f"{slug(app)}.json"))
        print(f"  -> {result.validation_status} (pass {result.research_pass})")
        time.sleep(0.5)  # be polite to rate limits


if __name__ == "__main__":
    main()
