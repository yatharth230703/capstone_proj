"""Shared enum vocabulary. All cross-boundary contracts in `core/contracts.py`
reference these instead of raw strings or `Literal` unions, so the hard rules
in CLAUDE.md (e.g. "legal_status is never collapsed") are enforced by the type
system rather than by convention.
"""

from __future__ import annotations

from enum import StrEnum


class DataOrigin(StrEnum):
    """Hard rule 5: mandatory on every node, edge, and signal."""

    PUBLIC = "public"
    SYNTHETIC = "synthetic"


class LegalStatus(StrEnum):
    """Hard rule 6: allegation != conviction, never collapsed."""

    ALLEGED = "alleged"
    CHARGED = "charged"
    CONVICTED = "convicted"
    SETTLED = "settled"
    DISMISSED = "dismissed"
    EXCLUDED = "excluded"


class Verdict(StrEnum):
    PASS_ = "pass"
    WARN = "warn"
    FAIL = "fail"


class FreshnessStatus(StrEnum):
    CURRENT = "current"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class EntityType(StrEnum):
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"


class MatchDecision(StrEnum):
    AUTO_LINK = "auto_link"
    AGENT_REVIEW = "agent_review"
    HUMAN_REVIEW = "human_review"
    REJECT = "reject"


class InvestigationDepth(StrEnum):
    SCREEN = "screen"
    FULL = "full"


class AttributeType(StrEnum):
    ADDRESS = "address"
    PHONE = "phone"
    OFFICER = "officer"


class ExclusionAuthority(StrEnum):
    """CLAUDE.md Amendment 1: federal LEIE vs. state Medicaid exclusion lists.

    Not pooled into one precision number in the judge report — a state
    termination is frequently administrative, not fraud-related.
    """

    FEDERAL_OIG = "federal_oig"
    STATE_MEDICAID = "state_medicaid"


class CacheLayer(StrEnum):
    NONE = "none"
    L1 = "L1"
    L3 = "L3"


class PriorityTier(StrEnum):
    """Output of `workflow/state.ScoringService` (plan §10, M6). `HIGH_PRIORITY`
    means the case met all four escalation-gate conditions verbatim; never set
    by an agent, never collapsed with the others.
    """

    HIGH_PRIORITY = "high_priority"
    STANDARD = "standard"
    LOW = "low"
