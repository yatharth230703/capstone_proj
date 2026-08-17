JUDGE INDEPENDENCE: LIMITED.
The rubric judge (gpt-5.4) shares a model family with the agents it grades,
introducing self-preference bias. LLM rubric scores are therefore reported as
SECONDARY. Primary evaluation is deterministic (citation validity, numeric
grounding, entity existence) and does not involve an LLM.
Judge accuracy on injected-defect calibration cases: 8/8.
Cross-family validation (Kimi K2.6 or Claude) deferred to Phase 2.

## Deterministic checks (PRIMARY)

| Provider NPI | citations OK | numbers OK | entities OK |
|---|---|---|---|
| 1003001439 | 0/0 | 19 violations | 4/4 |
| 1003008756 | 0/0 | 55 violations | 48/48 |
| 9010000000 | 0/0 | 21 violations | 4/4 |
| 9020000000 | 1/1 | 0 violations | 1/1 |
| 9030000000 | 2/2 | 6 violations | 1/2 |
| 9040000000 | 1/1 | 17 violations | 7/8 |
| 9050000000 | 3/3 | 0 violations | 1/2 |
| 9060000001 | 3/3 | 8 violations | 2/5 |
| 9070000000 | 1/1 | 1 violations | 1/1 |
| 9080000000 | 0/0 | 11 violations | 2/2 |
| 9090000000 | 1/1 | 2 violations | 3/3 |
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
- **C04** (Counter-evidence section empty): expected criterion `counter_evidence` mean score 2.0 — CAUGHT
- **C05** (A fabricated NPI in linked entities): expected criterion `hallucination` mean score 0.0 — CAUGHT
- **C06** (Banned word 'fraudulent' in the narrative): expected criterion `legal_discipline` mean score 0.0 — CAUGHT
- **C07** (Two signals from one underlying fact, weighted twice): expected criterion `numeric_grounding` mean score 1.0 — CAUGHT
- **C08** (Synthetic provider presented without disclosed data_origin): expected criterion `citation_validity` mean score 2.0 — CAUGHT

## Rubric judge scores (SECONDARY)

| Provider NPI | citation_validity | counter_evidence | hallucination | legal_discipline | numeric_grounding | Low-reliability criteria |
|---|---|---|---|---|---|---|
| 1003001439 | 1.0 | 2.0 | — | 5.0 | 4.3 | hallucination |
| 1003008756 | 0.7 | — | 1.3 | 5.0 | — | counter_evidence, numeric_grounding |
| 9010000000 | 1.0 | 2.0 | 2.3 | 5.0 | 4.3 | — |
| 9020000000 | 2.0 | 5.0 | 3.0 | 5.0 | 5.0 | — |
| 9030000000 | 3.7 | 5.0 | 3.7 | 5.0 | 4.3 | — |
| 9040000000 | 2.7 | 5.0 | 2.0 | 5.0 | 3.7 | — |
| 9050000000 | 4.0 | 5.0 | 4.0 | 5.0 | 5.0 | — |
| 9060000001 | 4.3 | 5.0 | 4.0 | 5.0 | 5.0 | — |
| 9070000000 | 3.0 | 5.0 | 3.7 | 5.0 | 4.0 | — |
| 9080000000 | 1.0 | 4.0 | 1.3 | 5.0 | 2.7 | — |
| 9090000000 | 4.0 | 5.0 | 3.0 | 5.0 | 4.0 | — |
| 9100000000 | 4.0 | 5.0 | 4.0 | 5.0 | 5.0 | — |

## Deterministic-vs-LLM disagreement

- **9030000000**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9030000000**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9050000000**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9050000000**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9050000000**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9060000001**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 0: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 1: LLM scored hallucination=4 but the deterministic check found a fabricated identifier
- **9100000000**: sample 2: LLM scored hallucination=4 but the deterministic check found a fabricated identifier

## Three worst-scoring cases

### 1003008756 (overall 2.3/5)
  - `citation_validity` (0/5): The packet makes many factual claims in the narrative but provides zero citations for any of them; a clean resolution report with total_citations 0 does not satisfy the requirement that claims trace to stored artifacts or graph nodes.
  - `numeric_grounding` (2/5): Some numbers are grounded by the bundle, such as provider_npi 1003008756 and the empty signals/enforcement arrays supporting 0 indicators, but the narrative introduces one-hop and two-hop counts and a long list of related NPIs without any structured hybrid-search result in the packet to ground those numbers.
  - `hallucination` (1/5): The narrative relies on a hybrid-search neighborhood, specific officer_id, phone, normalized_key, and many two-hop NPIs, but no hybrid-search evidence object is included in the packet. Those entities and relationships therefore appear unsupported by the packet's own evidence, even if they may exist elsewhere.
  - `citation_validity` (1/5): The packet makes many factual claims in the narrative, including specific hop distances, an officer_id, a phone number, a normalized_key, and many NPIs, but the packet provides zero citations for any of them. The citation report shows total_citations 0, so the claims do not trace to stored artifacts or graph nodes within the packet.
  - `hallucination` (2/5): The narrative introduces a large set of entities and relationships from an asserted hybrid search, but the packet contains no structured hybrid-search result, no citations, and no attached graph extract supporting those identifiers or the one-hop and two-hop relationships. Those entities may be real, but within this packet they are unsupported appearances.

### 9080000000 (overall 2.8/5)
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative about a shared officer, shared phone, shared address, small communities, and enforcement-search results, but it provides zero citations and zero source_ids anywhere in the bundle, so those claims do not trace to stored artifacts or graph nodes within the packet itself.
  - `numeric_grounding` (2/5): Some numbers are grounded by the structured packet, including provider_npi 9080000000, the empty signals array, member_count 3, and the statement that the provider exhibits 0 indicators. But the narrative also references a phone number and address key without any structured evidence object showing where those values came from, so numeric content is only partially grounded within the packet.
  - `hallucination` (1/5): The packet introduces specific entities and relationships—an officer_id, a phone number, an address normalized_key, and community findings—but the evidence bundle contains no supporting graph objects, no source_ids, no signals, and no structured neighborhood data establishing those relationships. Those details therefore appear unsupported by the packet's own evidence.
  - `citation_validity` (1/5): The packet reports zero citations while the narrative makes multiple factual claims about a shared officer, shared phone, shared address, community search results, and lack of direct community context. Because those claims are uncited in the packet, they do not trace to stored artifacts or graph nodes within the packet itself.
  - `hallucination` (1/5): The packet introduces specific identifiers and relationships—officer_id ba470fec46f979be7f8a1c79, phone +14075559400, normalized_key 50|SLEEPY HOLLOW|DR|32801, and community member_count 3—without any supporting structured evidence or citations in the bundle. Those details may be true, but within this packet they are unsupported.

### 9010000000 (overall 2.9/5)
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative but provides zero citations for any of them. Although the citation report says all resolved, it also shows total_citations 0, so claim-level traceability is missing rather than demonstrated.
  - `counter_evidence` (2/5): The packet does not provide a substantive benign explanation for an adverse signal; it mainly explains that rebuttal was impossible because there were no fired signals. The nearby-community discussion offers some benign context, but it is not framed as a developed alternative explanation to a concrete indicator.
  - `citation_validity` (1/5): The packet makes multiple factual claims in the narrative but provides zero citations for any of them. The citation report resolves because there were no citations to check, not because the claims were actually sourced to stored artifacts or graph nodes.
  - `counter_evidence` (2/5): The packet does include a benign explanation — 'That pattern is consistent with a small, tightly connected provider neighborhood rather than a broad or highly dispersed one' — but it is not tied to any fired signal and the structured counter_evidence section explicitly says there are no signal_type entries to rebut. That makes the counter-evidence present but only weakly operative as rebuttal.
  - `hallucination` (2/5): This narrative introduces community candidates, California location, shared-address/shared-officer linkage, and specific nearby synthetic entities, but the bundle does not include the underlying community records, neighborhood expansion output, or source-linked evidence for those relationships. Those details may be true, but in this packet they are unsupported assertions rather than demonstrated evidence.
