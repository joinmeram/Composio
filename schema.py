"""
Structured output schema for a single app's research result.
Used by the orchestrator, the validator, and the HTML report generator.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class Evidence:
    claim: str          # which field this evidence supports, e.g. "auth_method"
    url: str            # the docs / source URL
    excerpt: str         # short excerpt (<= 300 chars) copied from the fetched page


@dataclass
class AppResult:
    app: str
    category: str
    one_liner: str = ""

    auth_methods: list = field(default_factory=list)     # e.g. ["OAuth2", "API Key"]
    self_serve: Optional[bool] = None                     # True / False / None (unknown)
    access_notes: str = ""                                 # "free tier", "paid plan required", "contact sales", etc.

    api_surface: str = ""                                  # "REST", "GraphQL", "REST + GraphQL", "none found"
    api_breadth: str = ""                                  # "broad", "narrow", "unknown"
    mcp_support: Optional[bool] = None
    mcp_notes: str = ""

    buildability: str = ""                                 # "ready today" / "buildable with workaround" / "blocked"
    main_blocker: str = ""

    evidence: list = field(default_factory=list)           # list[Evidence]

    # research + validation metadata
    research_pass: int = 1                                  # incremented on each repair attempt
    validation_status: str = "unvalidated"                  # "passed" / "failed" / "unvalidated"
    validation_failures: list = field(default_factory=list)
    human_verified: Optional[bool] = None
    human_notes: str = ""

    def to_dict(self):
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d):
        ev = [Evidence(**e) if isinstance(e, dict) else e for e in d.get("evidence", [])]
        d = dict(d)
        d["evidence"] = ev
        return AppResult(**d)

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
