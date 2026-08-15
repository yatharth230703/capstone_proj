"""Shared agent error types.

Split out of `_base.py` (M3) purely to break a circular import: `_base.py`
(agent construction) and `_llm_call.py` (agent invocation) both need to raise
these, and `_llm_call.py` must not import from `_base.py` at runtime.
"""

from __future__ import annotations

from specter.core.errors import SpecterError


class AgentOutputError(SpecterError):
    """The model returned something that is not valid against the agent's
    `output_schema`. Raised rather than repaired — a case built on a
    half-parsed agent response is worse than no case (CLAUDE.md hard rule 7).
    """


class PrefixInstabilityError(SpecterError):
    """The system prefix reaching the model differs from the one the compiler
    produced. This means something is leaking above the cache boundary and the
    caching pillar has silently stopped working — halt rather than continue
    paying full price while reporting success.
    """
