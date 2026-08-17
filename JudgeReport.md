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
| 1003001439 | 0/0 | 15 violations | 3/3 |
| 1003008756 | 0/0 | 18 violations | 3/3 |
| 9010000000 | 0/0 | 21 violations | 4/4 |
| 9020000000 | 1/1 | 10 violations | 3/3 |
| 9030000000 | 2/2 | 5 violations | 1/2 |
| 9040000000 | 1/1 | 8 violations | 2/3 |
| 9050000000 | 3/3 | 4 violations | 1/3 |
| 9060000001 | 3/3 | 9 violations | 2/3 |
| 9070000000 | 1/1 | 20 violations | 4/4 |
| 9080000000 | 0/0 | 11 violations | 2/2 |
| 9090000000 | 1/1 | 5 violations | 3/3 |
| 9100000000 | 2/2 | 2 violations | 1/2 |

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
| S01 | — | — | no (by design) | ✅ |
| S02 | phone_degree | phone_degree | yes | ✅ |
| S03 | address_degree, enumeration_burst | address_degree, enumeration_burst | yes | ✅ |
| S04 | officer_degree | officer_degree | yes | ✅ |
| S05 | exclusion_proximity | address_degree, enumeration_burst, exclusion_proximity | yes | ✅ |
| S06 | phoenix_pattern | address_degree, exclusion_proximity, phoenix_pattern | yes | ✅ |
| S07 | address_churn | address_churn | yes | ✅ |
| S08 | — | — | no (by design) | ✅ |
| S09 | geographic_spread | geographic_spread | yes | ✅ |
| S10 | community_exclusion_density | exclusion_proximity, community_exclusion_density | yes | ✅ |

**Headline: 8/8 scenarios with a Phase 1 detector were detected.** The remaining scenarios have no Phase 1 detector by design (no address-type classification, no utilization data) and are reported separately above rather than folded into a misleading 10/10.

## Calibration accuracy (C01-C08, judge's own accuracy metric)

- **C01** (Citation pointing to a non-existent artifact ID): expected criterion `citation_validity` mean score 0.0 — CAUGHT
- **C02** (A number absent from every tool result): expected criterion `numeric_grounding` mean score 1.0 — CAUGHT
- **C03** ("convicted" used where source says "charged"): expected criterion `legal_discipline` mean score 0.0 — CAUGHT
- **C04** (Counter-evidence section empty): expected criterion `counter_evidence` mean score 1.6666666666666667 — CAUGHT
- **C05** (A fabricated NPI in linked entities): expected criterion `hallucination` mean score 0.3333333333333333 — CAUGHT
- **C06** (Banned word 'fraudulent' in the narrative): expected criterion `legal_discipline` mean score 0.0 — CAUGHT
- **C07** (Two signals from one underlying fact, weighted twice): expected criterion `numeric_grounding` mean score 1.6666666666666667 — CAUGHT
- **C08** (Synthetic provider presented without disclosed data_origin): expected criterion `citation_validity` mean score 3.0 — MISSED

## Rubric judge scores (SECONDARY)

| Provider NPI | citation_validity | counter_evidence | hallucination | legal_discipline | numeric_grounding | Low-reliability criteria |
|---|---|---|---|---|---|---|
| 1003001439 | 1.0 | 5.0 | 2.0 | 5.0 | 4.0 | — |
| 1003008756 | 1.0 | 3.7 | 2.7 | 5.0 | 4.7 | — |
| 9010000000 | 1.0 | 2.0 | 1.7 | 5.0 | 3.7 | — |
| 9020000000 | 2.0 | 5.0 | 2.0 | 5.0 | 3.0 | — |
| 9030000000 | 2.0 | 5.0 | 3.0 | 5.0 | 4.0 | — |
| 9040000000 | 3.0 | 5.0 | 3.0 | 5.0 | 4.0 | — |
| 9050000000 | 4.0 | 5.0 | 3.0 | 5.0 | 5.0 | — |
| 9060000001 | 4.0 | 5.0 | 3.0 | 5.0 | 5.0 | — |
| 9070000000 | 2.0 | 5.0 | 2.0 | 5.0 | 4.0 | — |
| 9080000000 | 1.0 | — | 1.7 | 5.0 | 3.3 | counter_evidence |
| 9090000000 | 4.0 | 5.0 | 3.0 | 5.0 | 3.7 | — |
| 9100000000 | 4.0 | 5.0 | 2.7 | 5.0 | 4.3 | — |

## Deterministic-vs-LLM disagreement

None observed.

## Three worst-scoring cases

### 9010000000 (overall 2.7/5)
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative, but it provides zero citations and zero source_ids. Because there are no stored-artifact or graph-node references attached to the claims, most claims cannot be traced, so citation validity is largely unsatisfied despite the empty citation report resolving cleanly.
  - `counter_evidence` (2/5): The packet does include a counter-evidence section, but it does not provide a substantive benign explanation that rebuts an actual fired signal. Its only explanation is procedural—that there were no fired signals to rebut—so the counter-evidence requirement is only weakly met.
  - `hallucination` (2/5): The narrative introduces specific community-candidate properties, synthetic nearby entities, and enforcement case identifiers that are not present as structured evidence objects in the bundle excerpt. They may be real, but within this packet they are unsupported assertions, so there is a meaningful hallucination risk even though some top-level facts like the empty signals array are supported.
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative but provides zero citations and zero source_ids, so the claims do not trace to stored artifacts or graph nodes within the packet even though the citation report says all resolved.
  - `counter_evidence` (2/5): The packet does not provide a substantive benign explanation for any actual adverse indicator; it only explains that rebuttal was impossible because there were no fired signals. The statement about a small, tightly connected provider neighborhood is contextual, but it is not framed as a concrete benign alternative to a specific signal.

### 9080000000 (overall 2.8/5)
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative but provides zero citations for any of them; although the citation report says all resolved, it only reflects that there were no citations to validate, so claim-level traceability is not demonstrated.
  - `hallucination` (2/5): The packet acknowledges missing direct community context, yet the narrative still asserts that hybrid search surfaced several communities with member_count 3 and mentions specific shared officer, phone, and address relationships without any supporting structured records in the bundle, so unsupported entities or relationships may have been introduced.
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative but provides zero citations for any of them; a clean validation report with total_citations 0 does not satisfy the requirement that claims trace to stored artifacts or graph nodes.
  - `counter_evidence` (2/5): The packet does include a benign explanation, but it is limited and weakly supported because the counter_evidence block has per_signal as an empty list and the narrative offers only a general alternative interpretation rather than a substantive rebuttal tied to concrete fired signals.
  - `hallucination` (1/5): These entities and relationships appear only in the narrative and are not supported by any structured evidence entries, source_ids, or signal outputs in the packet, so the packet presents unsupported identifiers and relationships.

### 1003001439 (overall 3.4/5)
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative about an address normalized_key, a phone number, an officer with officer_id, a taxonomy code, community search results, and a case_id, but it provides zero citations and zero source_ids for any of them. Because the packet contains claims without traceable stored artifacts or graph-node citations, citation validity is largely unsatisfied despite the internal report saying all resolved.
  - `hallucination` (2/5): The packet introduces multiple entities and relationships only in free-text narrative, not in structured evidence fields: the address normalized_key, phone, officer, taxonomy code, community search results, and the enforcement case search hit all appear without corresponding structured records in the bundle. That makes it impossible to verify from the packet alone whether these entities and relationships are supported, so hallucination risk remains material even though the narrative avoids linking the enforcement case to the provider.
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative about an address normalized_key, a phone number, an officer, a taxonomy code, community search results, and a case_id, but it provides zero citations and zero source_ids. Because the packet contains claims without any traceable stored artifact or graph-node references, citation validity is largely unsatisfied despite the citation_report saying all_resolved with total_citations 0.
  - `hallucination` (2/5): The packet introduces multiple entities and relationships in the narrative that are not backed by any structured evidence objects in the bundle: the address neighborhood, the phone-sharing context, the officer identity, the taxonomy, the community search results, and the candidate enforcement case are all asserted without accompanying evidence records or citations. Because these items may be real but are unsupported within the packet as presented, the hallucination risk is material.
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative about an address normalized_key, a phone number, an officer, a taxonomy code, community search results, and a case_id, but it provides zero citations and zero source_ids, so those claims do not trace to stored artifacts or graph nodes within the packet.
