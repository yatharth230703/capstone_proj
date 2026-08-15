## B3 Exemplar: Address Cluster Narration

**Evidence given** (from `signal_tools.address_degree` and
`graph_tools.expand_neighborhood`): provider NPI 1770247926 is located at a
normalized address shared by 9 other Provider nodes, all enumerated within a
90-day window; the address is not co-located with any hospital or known
medical office building in the graph.

**Facts** (each with `source_ids` pointing to the tool call that produced it):
- `address_degree` signal value: 9 distinct providers at this
  `normalized_key`, threshold 5. (source_ids: ["signal:address_degree:1770247926"])
- `enumeration_burst` signal value: 9 of 9 co-located providers enumerated
  within a 90-day window. (source_ids: ["signal:enumeration_burst:1770247926"])
- No `co_located_facility` relationship to a hospital or clinic exists for
  this address in the graph. (source_ids: ["graph:address:2500|NW79TH|AVE|33122"])

**Inference:** The combination of high address degree, a tight enumeration
window, and the absence of a co-located institutional facility is consistent
with a shell-cluster registration pattern rather than a legitimate
multi-tenant medical building. This provider exhibits 2 independently
observed indicators associated with a shell-cluster registration pattern.

**Hypothesis:** Confirm via Playwright-fetched imagery or business-registry
lookup whether this address corresponds to a residential unit, a mailbox
service, or a genuine multi-suite commercial building — the Skeptic agent
should evaluate this before the finding is scored.

Note what this exemplar does NOT do: it does not say the provider "is
fraudulent," it does not invent a tenth co-located provider, and it does not
state the enumeration window as anything other than the exact value the tool
returned.
