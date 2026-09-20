"""
Validation checks run against every synthesized AppResult before it's accepted.

The point: an LLM synthesis pass can hallucinate a plausible-sounding answer even
when the fetched content doesn't actually support it. This module checks the
result *against its own cited evidence*, not against ground truth (that's what
the human verification pass in verify.py is for).

Returns a list of failing field names (empty list = passed).
"""

VALID_AUTH = {"OAuth2", "API Key", "Basic Auth", "Token", "Other", "None found"}
VALID_SURFACE = {"REST", "GraphQL", "REST + GraphQL", "none found"}
VALID_BUILDABILITY = {"ready today", "buildable with workaround", "blocked"}


def validate_result(result, fetched_content: str) -> list:
    failures = []

    # 1. Every claim needs at least one evidence entry citing a real URL.
    fields_needing_evidence = {"auth_methods", "self_serve", "api_surface", "mcp_support"}
    cited_claims = {e.claim for e in result.evidence}
    for f in fields_needing_evidence:
        val = getattr(result, f)
        is_meaningful = val not in (None, "", [], "unknown", "none found")
        if is_meaningful and f not in cited_claims:
            failures.append(f"missing_evidence:{f}")

    # 2. Auth methods must be from the controlled vocabulary.
    for m in result.auth_methods:
        if m not in VALID_AUTH:
            failures.append("unsupported_auth_method")
            break

    # 3. api_surface must be from the controlled set.
    if result.api_surface and result.api_surface not in VALID_SURFACE:
        failures.append("unsupported_api_surface")

    # 4. self_serve claim: if True, access_notes shouldn't contradict it
    #    (e.g. claiming self-serve while also saying "requires approval").
    if result.self_serve is True and any(
        kw in result.access_notes.lower() for kw in ["approval required", "contact sales", "partnership only"]
    ):
        failures.append("self_serve_contradicts_access_notes")

    # 5. Evidence excerpts must actually appear in what was fetched (catches
    #    fabricated quotes / hallucinated URLs the model never actually read).
    normalized_fetched = " ".join(fetched_content.split()).lower()
    for e in result.evidence:
        excerpt_norm = " ".join(e.excerpt.split()).lower()
        # allow partial match on a meaningful chunk, not exact substring of the whole excerpt,
        # since minor whitespace/formatting differences are expected
        chunk = excerpt_norm[:60]
        if chunk and chunk not in normalized_fetched:
            failures.append(f"unverifiable_excerpt:{e.claim}")

    # 6. buildability must be from controlled set and consistent with main_blocker
    if result.buildability and result.buildability not in VALID_BUILDABILITY:
        failures.append("unsupported_buildability_label")
    if result.buildability == "blocked" and not result.main_blocker:
        failures.append("blocked_without_blocker_stated")

    return failures
