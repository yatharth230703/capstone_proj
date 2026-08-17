## B0: Tool Schemas

```json
{
  "address_churn": {
    "docstring": "Count this provider's recorded address changes within the configured\ntrailing window.\n\nFires at the threshold. Relocations, corrections to a mis-keyed\nregistration, and practice moves are ordinary reasons for churn.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value`, `threshold`,\n    and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "address_degree": {
    "docstring": "Count the distinct providers registered at this provider's address.\n\nFires when the count reaches the configured threshold. A high count is\nequally consistent with a shell cluster and with a legitimate medical\noffice building \u2014 the number alone does not distinguish them.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} where the signal carries the\n    measured `value`, the `threshold` it was compared against, and\n    `source_ids`. Quote these numbers exactly; never restate them\n    approximately.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "community_exclusion_density": {
    "docstring": "Compute the fraction of this provider's graph community that carries\nan exclusion.\n\nFires above the configured fraction. This describes the community, not\nthe provider.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value` (a fraction\n    between 0 and 1), `threshold`, and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "enumeration_burst": {
    "docstring": "Detect several providers at this provider's address being enumerated\nwithin a short window.\n\nFires when the count within the configured window reaches the threshold.\nA new medical building filling up produces this pattern too.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value`, `threshold`,\n    and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "exclusion_proximity": {
    "docstring": "Measure the graph distance from this provider to the nearest excluded\nentity.\n\nFires when the shortest path is at or under the configured hop limit.\nProximity is structural: it does not imply the provider knew of, or\nparticipated in, whatever led to that exclusion.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value` (hop count),\n    `threshold`, and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "expand_neighborhood": {
    "docstring": "Return the subgraph around a provider: every node reachable within\n`hops` relationships, plus the edges connecting them.\n\nUse this to see a provider's structural context \u2014 who shares its\naddress, phone, or officers, and what those entities connect to in turn.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n    hops: relationship depth, 1-3. Values above 3 are clamped to 3.\n    limit: maximum nodes returned, up to 200. Higher values are clamped.\n\nReturns:\n    {\"center_npi\": str, \"nodes\": [...], \"edges\": [...], \"node_count\": int,\n     \"edge_count\": int}. Counts are computed here, not by you.",
    "params": {
      "hops": "int",
      "limit": "int",
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "find_shared_attribute_peers": {
    "docstring": "List the other providers that share a given attribute with this one.\n\nSharing an address or phone number is a fact, not a finding: legitimate\nmedical office buildings and multi-site practices produce the same\npattern. Report what is shared and let the counter-evidence step judge it.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n    attribute: exactly one of \"address\", \"phone\", or \"officer\".\n\nReturns:\n    {\"peers\": [...], \"peer_count\": int} where each peer carries the\n    shared value and its source_ids. On an invalid `attribute` value,\n    returns {\"error\": \"...\"} \u2014 pass one of the three literal strings.",
    "params": {
      "attribute": "str",
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "geographic_spread": {
    "docstring": "Compute the maximum distance between organizations sharing an\nauthorized official with this provider.\n\nFires above the configured kilometre threshold. Distances are derived\nfrom ZIP-code centroids, so they are approximate at street level; the\nthreshold is set high enough that this imprecision does not matter.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value` (kilometres),\n    `threshold`, and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "get_community_context": {
    "docstring": "Return the graph community this provider belongs to, with the\ndeterministic structural facts about it (member count, shared\nattributes, excluded-member count) and, when available, a written\ncharacterization of the community.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"found\": bool, \"community\": {...} | None}. Providers not in any\n    community return found=False \u2014 most providers are isolated and\n    that is unremarkable.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "get_provider_profile": {
    "docstring": "Look up one provider's full identity record: legal name, entity type,\nstate, enumeration date, addresses, phones, authorized officers,\ntaxonomies, and any exclusions attached to it.\n\nThis is the first call to make when investigating a provider. Every\nvalue it returns is read directly from the knowledge graph.\n\nArgs:\n    npi: the provider's 10-digit National Provider Identifier.\n\nReturns:\n    {\"found\": bool, \"profile\": {...} | None}. `found` is False when no\n    provider with that NPI exists in the graph \u2014 that is a valid\n    answer, not an error, and you must not invent a profile for it.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "name_similarity": {
    "docstring": "Score how similar two organization or person names are, 0-100.\n\nA high score is a reason to investigate whether two records refer to one\nentity. It is never on its own a reason to link them, and a common name\nmatching a sanctioned party is not a match.\n\nArgs:\n    a: the first name.\n    b: the second name.\n\nReturns:\n    {\"score\": float} on a 0-100 scale.",
    "params": {
      "a": "str",
      "b": "str"
    },
    "returns": "dict[str, Any]"
  },
  "normalize_address": {
    "docstring": "Parse a raw U.S. address into its deterministic collision key.\n\nSuite and unit are deliberately excluded from the key, so two providers\nin different suites of one building share a key. That is correct\nbehaviour and must not be worked around.\n\nArgs:\n    raw: a raw address string, e.g. \"1500 Biscayne Blvd Unit 3B, Miami, FL 33132\".\n\nReturns:\n    The parsed address, including `normalized_key` and a\n    `parse_confidence` of \"high\" or \"low\".",
    "params": {
      "raw": "str"
    },
    "returns": "dict[str, Any]"
  },
  "officer_degree": {
    "docstring": "Count the distinct organizations sharing an authorized official with\nthis provider.\n\nFires at the configured threshold. Multi-site practices and management\ncompanies produce the same pattern legitimately.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value`, `threshold`,\n    and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "phoenix_pattern": {
    "docstring": "Detect whether this provider is a recently created organization\nsharing an address and officer with an organization excluded shortly\nbefore it appeared.\n\nFires within the configured months-since-exclusion window. Succession\ncan be entirely legitimate \u2014 a practice reorganizing after losing a\nprincipal produces the same shape.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value`, `threshold`,\n    and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "phone_degree": {
    "docstring": "Count the distinct providers sharing this provider's phone number.\n\nFires at the configured threshold. Answering services, billing agents,\nand practice-management companies legitimately produce shared numbers.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value`, `threshold`,\n    and `source_ids`.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "physical_existence": {
    "docstring": "Report whether this provider's practice address is a type that is\nimplausible for a place of business \u2014 a home, a mailbox store, or a PO\nbox \u2014 and how many providers share it.\n\nThe address type comes from a postal-address database, not from a site\nvisit: a legitimate solo practitioner registering a home office, a\npractice that uses a mail service for correspondence, and a shell\nregistration all produce the same classification. The measured value is\nthe co-located provider count, not a judgement about the address.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n\nReturns:\n    {\"fired\": bool, \"signal\": {...} | None} with `value` (co-located\n    provider count), `threshold`, `source_ids`, and a\n    `known_limitations` entry naming the classified type.",
    "params": {
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "propose_entity_matches": {
    "docstring": "Compute the deterministic match features between this provider and\neach candidate NPI: name similarity, and whether they share an address,\nphone, or officer.\n\nThis returns features only \u2014 it deliberately does not decide whether the\nrecords match. That adjudication is yours, and a false merge is far more\ndamaging than a missed match.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n    candidates: NPIs to compare against.\n\nReturns:\n    {\"proposals\": [...], \"proposal_count\": int}.",
    "params": {
      "candidates": "list[str]",
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "search_enforcement_cases": {
    "docstring": "Search the stored corpus of enforcement cases (DOJ press releases and\nrelated records) for text matching `query`.\n\nResults are candidate reading material, not matches to your provider. A\ncase mentioning a similar name or scheme is not evidence that this\nprovider is connected to it \u2014 treat any linkage as requiring explicit\ndisambiguation.\n\nArgs:\n    query: free-text search terms, e.g. \"durable medical equipment\n        billing scheme Florida\".\n    k: maximum number of cases to return, default 10.\n\nReturns:\n    {\"hits\": [...], \"hit_count\": int}, each hit carrying case_id, title,\n    a snippet, and source_ids.",
    "params": {
      "k": "int",
      "query": "str"
    },
    "returns": "dict[str, Any]"
  },
  "shortest_path_to_exclusion": {
    "docstring": "Find the shortest relationship path from this provider to any excluded\nindividual or organization in the graph.\n\nA short path is a proximity fact, never an accusation: it says this\nprovider is N relationships away from an entity that carries an\nexclusion, and nothing about this provider's own conduct.\n\nArgs:\n    npi: the provider's 10-digit NPI.\n    max_hops: maximum path length to search, default 4.\n\nReturns:\n    {\"found\": bool, \"path\": {...} | None}. `found` False means no\n    exclusion is reachable within `max_hops` \u2014 report that as the\n    absence of a signal, not as evidence of anything.",
    "params": {
      "max_hops": "int",
      "npi": "str"
    },
    "returns": "dict[str, Any]"
  },
  "validate_citations": {
    "docstring": "Check that every source id resolves to a stored evidence artifact or\nan existing graph node.\n\nRun this before finalizing any output that carries citations. An\nunresolved source id is a bug in the claim, not a formatting problem.\n\nArgs:\n    source_ids: the source ids to verify.\n\nReturns:\n    {\"total_citations\": int, \"resolved_citations\": int,\n     \"unresolved_source_ids\": [...], \"all_resolved\": bool}.",
    "params": {
      "source_ids": "list[str]"
    },
    "returns": "dict[str, Any]"
  }
}
```
