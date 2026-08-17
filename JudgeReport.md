JUDGE INDEPENDENCE: LIMITED.
The rubric judge (gpt-5.4) shares a model family with the agents it grades,
introducing self-preference bias. LLM rubric scores are therefore reported as
SECONDARY. Primary evaluation is deterministic (citation validity, numeric
grounding, entity existence) and does not involve an LLM.
Judge accuracy on injected-defect calibration cases: 7/8.
Cross-family validation (Kimi K2.6 or Claude) deferred to Phase 2.

## Deterministic checks (PRIMARY)

| Provider NPI | citations OK | numbers OK | entities OK |
|---|---|---|---|
| 1003001439 | 0/0 | 19 violations | 4/4 |
| 1003008756 | 0/0 | 23 violations | 4/4 |
| 9010000000 | 1/1 | 18 violations | 4/4 |
| 9020000000 | 1/1 | 16 violations | 3/4 |
| 9030000000 | 2/2 | 5 violations | 1/2 |
| 9040000000 | 1/1 | 10 violations | 4/5 |
| 9050000000 | 3/3 | 4 violations | 0/2 |
| 9060000001 | 3/3 | 4 violations | 2/3 |
| 9070000000 | 1/1 | 0 violations | 1/1 |
| 9080000000 | 0/0 | 16 violations | 2/3 |
| 9090000000 | 1/1 | 5 violations | 3/3 |
| 9100000000 | 2/2 | 0 violations | 1/3 |

## Detection evaluation

| k | precision@k |
|---|---|
| 10 | 0.00 |
| 25 | 0.00 |
| 50 | 0.00 |

Real positives: **4** out of **8445** real providers loaded (BUILD_MILESTONES.md debt D-21 — this denominator is thin by design, not a bug in this evaluation).

Ranking method: `signal_count_proxy`.

## Per-scenario recall

| Scenario | Expected signals | Fired signals | Detector exists | Recall hit |
|---|---|---|---|---|
| S01 | physical_existence | physical_existence | yes | ✅ |
| S02 | phone_degree | phone_degree | yes | ✅ |
| S03 | address_degree, enumeration_burst | address_degree, enumeration_burst | yes | ✅ |
| S04 | officer_degree | officer_degree | yes | ✅ |
| S05 | exclusion_proximity | address_degree, enumeration_burst, exclusion_proximity | yes | ✅ |
| S06 | phoenix_pattern | address_degree, exclusion_proximity, phoenix_pattern | yes | ✅ |
| S07 | address_churn | address_churn | yes | ✅ |
| S08 | — | — | no (by design) | ✅ |
| S09 | geographic_spread | geographic_spread | yes | ✅ |
| S10 | community_exclusion_density | exclusion_proximity, community_exclusion_density | yes | ✅ |

**Headline: 9/9 scenarios with a Phase 1 detector were detected.** The remaining scenarios have no Phase 1 detector by design (no utilization data) and are reported separately above rather than folded into a misleading 10/10.

## Calibration accuracy (C01-C08, judge's own accuracy metric)

- **C01** (Citation pointing to a non-existent artifact ID): expected criterion `citation_validity` mean score 0.0 — CAUGHT
- **C02** (A number absent from every tool result): expected criterion `numeric_grounding` mean score 1.0 — CAUGHT
- **C03** ("convicted" used where source says "charged"): expected criterion `legal_discipline` mean score 0.0 — CAUGHT
- **C04** (Counter-evidence section empty): expected criterion `counter_evidence` mean score 2.0 — CAUGHT
- **C05** (A fabricated NPI in linked entities): expected criterion `hallucination` mean score 0.0 — CAUGHT
- **C06** (Banned word 'fraudulent' in the narrative): expected criterion `legal_discipline` mean score 0.0 — CAUGHT
- **C07** (Two signals from one underlying fact, weighted twice): expected criterion `numeric_grounding` mean score 1.0 — CAUGHT
- **C08** (Synthetic provider presented without disclosed data_origin): expected criterion `citation_validity` mean score 3.0 — MISSED

## Rubric judge scores (SECONDARY)

| Provider NPI | citation_validity | counter_evidence | hallucination | legal_discipline | numeric_grounding | Low-reliability criteria |
|---|---|---|---|---|---|---|
| 1003001439 | 1.0 | 5.0 | 2.0 | 5.0 | — | numeric_grounding |
| 1003008756 | 1.7 | 5.0 | — | 5.0 | 4.7 | hallucination |
| 9010000000 | 3.7 | 5.0 | 2.0 | 5.0 | 2.7 | — |
| 9020000000 | 3.0 | 5.0 | 2.7 | 5.0 | 4.7 | — |
| 9030000000 | 2.0 | 5.0 | 2.3 | 5.0 | 4.0 | — |
| 9040000000 | 2.0 | 5.0 | 2.0 | 5.0 | 2.3 | — |
| 9050000000 | 4.0 | 5.0 | 3.7 | 5.0 | 5.0 | — |
| 9060000001 | 4.0 | 5.0 | 4.0 | 4.0 | 5.0 | — |
| 9070000000 | 2.0 | 5.0 | 2.7 | 5.0 | 4.0 | — |
| 9080000000 | 1.0 | 1.7 | 1.0 | 5.0 | 5.0 | — |
| 9090000000 | 3.0 | 5.0 | 2.0 | 5.0 | 2.0 | — |
| 9100000000 | 4.0 | 5.0 | 4.0 | 5.0 | 5.0 | — |

## Deterministic-vs-LLM disagreement

- **9050000000**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9050000000**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier

## Three worst-scoring cases

### 9080000000 (overall 2.7/5)
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative about a community_id, an officer_id, a phone number, and an address normalized_key, but it provides zero citations overall, so those claims do not trace to stored artifacts or graph nodes within the packet itself.
  - `counter_evidence` (1/5): The packet does not provide a substantive benign explanation for any observed pattern; instead it explains why rebuttal could not be performed. That is a process note, not meaningful counter-evidence such as a legitimate office-sharing or management-company explanation.
  - `hallucination` (1/5): The packet introduces specific entities and relationships from contextual search results without source_ids or data_origin labels, and it does not include the underlying evidence for those nodes in the structured bundle. That makes these details unsupported within the packet and creates hallucination risk.
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative about a community_id, an officer_id, a phone node, and an address normalized_key, but it provides zero citations overall, so those claims do not trace to stored artifacts or graph nodes within the packet.
  - `counter_evidence` (2/5): The packet does include limiting language, but it does not provide a substantive benign explanation for the contextual patterns; it mainly explains why rebuttal could not be performed, which is procedural rather than a real alternative explanation.

### 1003001439 (overall 3.2/5)
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative but provides zero citations and zero resolved source ids, so the claims do not trace to stored artifacts or graph nodes within the packet itself.
  - `hallucination` (2/5): The narrative introduces specific entities, an officer_id, a normalized_key, community references, and enforcement case ids that are not represented in the structured fields of the packet beyond the prose itself, so those entities and relationships are not independently supported by packet evidence.
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative but provides zero citations and zero source_ids, so the claims do not trace to stored artifacts or graph nodes within the packet even though the citation report says there were no citations to validate.
  - `hallucination` (2/5): The packet introduces several specific entities and relationships in the narrative, but the structured evidence shown contains only empty signals, empty enforcement_matches, and no underlying neighborhood records or community objects. Because those named officers, organizations, communities, and hop-distance relationships are not separately present in the packet's structured evidence, the narrative appears to rely on unsupported context rather than fully evidenced packet contents.
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative, but it provides zero citations and zero source_ids. Because there are no stored-artifact or graph-node references attached to the claims, citation validity is largely unsupported even though the citation report says all_resolved is true for an empty citation set.

### 9040000000 (overall 3.3/5)
  - `citation_validity` (2/5): The packet's own counter-evidence says broader community facts are not fully validated: "the cited fired signal provides only the officer node source_id; additional source validation would be needed before relying on the broader cluster description as evidence." That means some narrative claims extend beyond the single resolved citation.
  - `numeric_grounding` (2/5): Some numbers are grounded by the structured signal, but other narrative numbers are not shown in the packet's structured data fields, including "member_count=4," "excluded_member_count=0," the date range "2026-08-06..2026-10-05," and the count in "shares an authorized officer with 4 organizations" when the only structured source shown is one officer_degree signal with one source_id and no separate community object.
  - `hallucination` (2/5): The packet itself flags unsupported narrative additions beyond the cited signal, including the community identifier, related NPIs, and detailed community/date-range relationships. Those entities and relationships may be real, but within this packet they are not adequately supported by the displayed evidence.
  - `citation_validity` (2/5): The packet's own citation report shows only 1 resolved citation total, while the narrative makes additional claims about community membership, enumeration dates, and related NPIs without corresponding source_ids in the structured evidence. The packet itself also admits this gap: "the cited fired signal provides only the officer node source_id; additional source validation would be needed before relying on the broader cluster description as evidence."
  - `numeric_grounding` (2/5): Several numbers in the narrative are not present in the packet's structured signals or citation report, including the community member_count=4, excluded_member_count=0, the enumeration range 2026-08-06..2026-10-05, and the count implied by the listed related NPIs. Those numbers may be accurate, but they are not grounded in the packet's own structured evidence fields beyond the single officer_degree signal.
