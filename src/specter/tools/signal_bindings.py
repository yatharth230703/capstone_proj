"""Model-facing bindings for the deterministic signal detectors (plan §8).

Split out of `bindings.py` to keep both modules under the 400-line ceiling in
`CLAUDE.md` — these are a different job from the graph read tools: each one is
a threshold comparison that either fires or does not, and the threshold comes
from `config/screening.yaml`, never from the model.

Every detector records the `threshold` it used alongside the measured `value`,
so a case packet stays reproducible even if the config changes later.

See `bindings.py` for why `from __future__ import annotations` matters to the
stability of the generated B0 block.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from neo4j import Driver
from pydantic import BaseModel

from specter.core.contracts import ScreeningThresholds
from specter.tools import signal_tools


def _dump(model: BaseModel | None) -> dict[str, Any] | None:
    return None if model is None else model.model_dump(mode="json")


def build_signal_bindings(
    driver: Driver, thresholds: ScreeningThresholds
) -> list[Callable[..., Any]]:
    """Bind driver + thresholds into each detector and return them in a stable
    order. `generate_b0_tool_schemas` sorts by name regardless.
    """

    # ---- signal detectors --------------------------------------------
    #
    # Each returns a RiskSignal or None. The threshold is bound from
    # config/screening.yaml and recorded on the signal, so a case packet stays
    # reproducible even if the config changes later. The model never picks a
    # threshold and never computes a value.

    def _run_signal(
        detector: Callable[[Driver, str, ScreeningThresholds], Any], npi: str
    ) -> dict[str, Any]:
        signal = detector(driver, npi, thresholds)
        return {"fired": signal is not None, "signal": _dump(signal)}

    def address_degree(npi: str) -> dict[str, Any]:
        """Count the distinct providers registered at this provider's address.

        Fires when the count reaches the configured threshold. A high count is
        equally consistent with a shell cluster and with a legitimate medical
        office building — the number alone does not distinguish them.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} where the signal carries the
            measured `value`, the `threshold` it was compared against, and
            `source_ids`. Quote these numbers exactly; never restate them
            approximately.
        """
        return _run_signal(signal_tools.address_degree, npi)

    def phone_degree(npi: str) -> dict[str, Any]:
        """Count the distinct providers sharing this provider's phone number.

        Fires at the configured threshold. Answering services, billing agents,
        and practice-management companies legitimately produce shared numbers.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value`, `threshold`,
            and `source_ids`.
        """
        return _run_signal(signal_tools.phone_degree, npi)

    def officer_degree(npi: str) -> dict[str, Any]:
        """Count the distinct organizations sharing an authorized official with
        this provider.

        Fires at the configured threshold. Multi-site practices and management
        companies produce the same pattern legitimately.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value`, `threshold`,
            and `source_ids`.
        """
        return _run_signal(signal_tools.officer_degree, npi)

    def enumeration_burst(npi: str) -> dict[str, Any]:
        """Detect several providers at this provider's address being enumerated
        within a short window.

        Fires when the count within the configured window reaches the threshold.
        A new medical building filling up produces this pattern too.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value`, `threshold`,
            and `source_ids`.
        """
        return _run_signal(signal_tools.enumeration_burst, npi)

    def address_churn(npi: str) -> dict[str, Any]:
        """Count this provider's recorded address changes within the configured
        trailing window.

        Fires at the threshold. Relocations, corrections to a mis-keyed
        registration, and practice moves are ordinary reasons for churn.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value`, `threshold`,
            and `source_ids`.
        """
        return _run_signal(signal_tools.address_churn, npi)

    def exclusion_proximity(npi: str) -> dict[str, Any]:
        """Measure the graph distance from this provider to the nearest excluded
        entity.

        Fires when the shortest path is at or under the configured hop limit.
        Proximity is structural: it does not imply the provider knew of, or
        participated in, whatever led to that exclusion.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value` (hop count),
            `threshold`, and `source_ids`.
        """
        return _run_signal(signal_tools.exclusion_proximity, npi)

    def community_exclusion_density(npi: str) -> dict[str, Any]:
        """Compute the fraction of this provider's graph community that carries
        an exclusion.

        Fires above the configured fraction. This describes the community, not
        the provider.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value` (a fraction
            between 0 and 1), `threshold`, and `source_ids`.
        """
        return _run_signal(signal_tools.community_exclusion_density, npi)

    def geographic_spread(npi: str) -> dict[str, Any]:
        """Compute the maximum distance between organizations sharing an
        authorized official with this provider.

        Fires above the configured kilometre threshold. Distances are derived
        from ZIP-code centroids, so they are approximate at street level; the
        threshold is set high enough that this imprecision does not matter.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value` (kilometres),
            `threshold`, and `source_ids`.
        """
        return _run_signal(signal_tools.geographic_spread, npi)

    def phoenix_pattern(npi: str) -> dict[str, Any]:
        """Detect whether this provider is a recently created organization
        sharing an address and officer with an organization excluded shortly
        before it appeared.

        Fires within the configured months-since-exclusion window. Succession
        can be entirely legitimate — a practice reorganizing after losing a
        principal produces the same shape.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"fired": bool, "signal": {...} | None} with `value`, `threshold`,
            and `source_ids`.
        """
        return _run_signal(signal_tools.phoenix_pattern, npi)


    return [
        address_degree,
        phone_degree,
        officer_degree,
        enumeration_burst,
        address_churn,
        exclusion_proximity,
        community_exclusion_density,
        geographic_spread,
        phoenix_pattern,
    ]
