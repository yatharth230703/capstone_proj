## B3 Exemplar: Enforcement Record Matching

**Evidence given** (from `graph_tools.search_enforcement_cases` and a LEIE
exclusion record matched by exact NPI): provider NPI 1093800195 has an
`EXCLUDED_BY` relationship to an Exclusion node with `exclusion_authority =
federal_oig`, `excl_type = 1128b7`, and `excl_date = 2019-03-11`.

**Facts:**
- Federal OIG exclusion record exists for this exact NPI, exclusion type
  `1128b7`, effective 2019-03-11. (source_ids: ["graph:exclusion:leie:<id>"])
- `legal_status` for this record is `excluded` — the record does not carry
  a `convicted` or `charged` status field; those are separate legal
  proceedings this record does not speak to. (source_ids: ["graph:exclusion:leie:<id>"])

**Inference:** An active federal exclusion on the operating provider's exact
NPI is a strong, government-sourced adverse-action signal — one of the two
authoritative-source conditions the escalation gate requires. This provider
exhibits 1 independently observed indicator from an authoritative government
source.

**Hypothesis:** none required — this is a direct, exact-identifier match,
not an inference requiring further disambiguation.

Contrast with a common-name match: if the exclusion record had matched only
on business name similarity with no NPI on either side, the correct output
is a `requires_disambiguation` flag, not an `EXCLUDED_BY` claim — never
auto-link an exclusion lacking an exact identifier. Note also what this
exemplar does not do: it does not say "convicted," does not say "guilty,"
and does not say "confirmed fraud" — the record says `excluded`, and that is
exactly what gets reported.
