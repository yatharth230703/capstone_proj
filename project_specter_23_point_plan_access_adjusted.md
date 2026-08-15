# Project Specter

## A Multi-Agent Intelligence System for Detecting Suspicious U.S. Healthcare Provider Networks

> **Access-adjusted edition:** This version preserves the complete 23-point implementation plan while replacing dependencies on `data.cms.gov` and `cms.gov` with accessible public mirrors, independent federal/state sources, and synthetic-data generators. Because mirrors may lag official releases, every ingestion connector must record the original publisher, mirror, snapshot date, checksum, and known freshness limitations.

## 1. Project objective

Project Specter will be a U.S.-focused, multi-agent investigation platform built with Google Agent Development Kit.

It will continuously collect information from public healthcare datasets, government enforcement records, provider registries, corporate records, websites, geographic sources, and controlled synthetic datasets.

The system will:

1. Discover healthcare providers and organizations exhibiting suspicious characteristics.
2. Connect providers, owners, addresses, phone numbers, organizations, specialties, sanctions, and enforcement cases into a continuously evolving knowledge graph.
3. Detect anomalies using trained machine-learning models and deterministic analytical tools.
4. Ask LLM-powered agents to investigate, contextualize, challenge, and explain those anomalies.
5. Maintain an incremental evidence history for every entity.
6. Present ranked investigative leads through ADK Web.
7. Preserve the source, retrieval date, model version, and reasoning behind every risk indicator.

The system’s output will not be:

> “Clinic X is fraudulent.”

Its output will be:

> “Clinic X exhibits six independently observed indicators associated with shell-provider or organized provider-fraud patterns and should receive further investigation.”

---

# 2. Product definition

Project Specter should be treated as three connected systems.

## A. Continuous screening system

This layer regularly retrieves new or updated public information.

Examples:

- new provider registrations;
- changed provider addresses;
- changes in ownership;
- NPI activations and deactivations;
- large changes in publicly mirrored Medicare utilization data;
- new exclusions;
- new DOJ enforcement cases;
- new websites or altered clinic information;
- newly discovered connections to previously flagged entities.

## B. Provider intelligence knowledge base

This stores everything known about each provider and its relationships.

The system must preserve historical versions rather than simply overwriting old records. A provider changing its address, owner, taxonomy, phone number, or organizational affiliation may itself be an important signal.

## C. Multi-agent investigation engine

This layer decides which entities should be examined, invokes specialist analytical tools, gathers additional evidence, challenges the findings, and creates an explainable risk report.

---

# 3. Fundamental operating principle

Project Specter should not allow an LLM to freely decide whether a clinic is fraudulent.

The LLM should perform:

- investigation planning;
- tool selection;
- evidence synthesis;
- inconsistency detection;
- case summarization;
- hypothesis generation;
- follow-up recommendations.

Deterministic code and trained models should perform:

- joins and aggregations;
- statistical calculations;
- geospatial calculations;
- anomaly detection;
- record linkage;
- graph feature computation;
- temporal comparisons;
- document and website feature extraction;
- risk-score calculation.

This separation is essential for reproducibility.

Every important numerical claim should originate from a tool result, not from an LLM estimate.

---

# 4. Initial scope

## Geographic scope

United States only.

## Payer scope

Begin with Medicare fee-for-service patterns reconstructed from accessible public mirrors and archived provider-level utilization files, supplemented with federal and state provider records.

## Provider scope

Do not initially screen every U.S. healthcare organization equally.

Start with two or three provider categories that have:

- strong public-data or mirror coverage;
- identifiable billing patterns;
- known organized-fraud typologies;
- sufficiently large provider populations;
- reasonably comparable peers.

Recommended initial categories:

1. Durable medical equipment, prosthetics, orthotics and supplies.
2. Physical or occupational therapy.
3. Home health agencies.
4. Clinical laboratories.
5. Hospice providers.

For the first working prototype, select **one category**, preferably DME suppliers or physical-therapy providers. Different provider classes require different peer groups, features, rules, and interpretations.

---

# 5. Public data foundation

## Tier 1: Core provider identity and enrollment data

### NPI/provider identity mirrors and registry interfaces

Use NPI data as the provider-identity backbone, but do not make the pipeline dependent on a blocked CMS download page.

Preferred access order:

1. A working NPI Registry API endpoint, where accessible.
2. Versioned NPPES snapshots mirrored on Kaggle, Hugging Face, an institutional repository, or another reputable public-data host.
3. A locally archived snapshot supplied by the project team.
4. State professional and facility licensing registries for verification and enrichment.

Relevant fields include:

- NPI;
- entity type;
- legal and alternate names;
- practice and mailing addresses;
- phone numbers;
- taxonomy codes;
- authorized official;
- enumeration date;
- last-update date;
- deactivation and reactivation details, when present.

The ingestion layer must label each record with:

- `original_publisher`;
- `mirror_provider`;
- `snapshot_date`;
- `retrieved_at`;
- `checksum`;
- `mirror_freshness`;
- `schema_version`.

NPI records are self-reported identity records. They are evidence of enumeration, not proof that a provider is licensed, credentialed, actively operating, or delivering care.

### State licensing, federal exclusion, and public enrollment substitutes

Because the public PECOS-derived files may be inaccessible through the blocked domains, replace direct PECOS dependence in the MVP with a composite enrollment-verification layer built from:

- state medical, nursing, therapy, pharmacy, laboratory, DME, home-health, hospice, and facility licensing databases;
- state health-department facility lists;
- SAM.gov entity registrations and exclusions;
- HHS OIG exclusions;
- state Medicaid exclusion lists;
- public Care Compare or provider-directory mirrors when legally available;
- archived or mirrored Medicare enrollment exports from reputable research repositories;
- National Plan and Provider Enumeration System snapshots;
- corporate registration records;
- public procurement and accreditation records where relevant.

These sources should be used to distinguish:

- an NPI that merely exists;
- an actively licensed professional;
- an actively licensed facility;
- a registered business entity;
- a provider appearing in a public payer or facility directory;
- an entity with an exclusion, sanction, lapse, or conflicting status.

Where an official enrollment status cannot be verified, the field must be recorded as **unknown**, not inferred.

---

## Tier 2: Utilization and payment data

### Mirrored Medicare provider-utilization datasets

Use accessible mirrors and archives of Medicare Physician and Other Practitioners provider-level and provider-by-service public-use files.

Preferred sources include:

- Kaggle’s public Medicare datasets, including provider, service, hospital, DME, and prescription-related snapshots;
- the ProPublica Data Store archive of Medicare provider-utilization and payment files;
- university or research-institution repositories that preserve the original public-use files;
- reproducible datasets accompanying peer-reviewed Medicare fraud-detection studies;
- Data.gov catalog records for metadata and dataset discovery, while avoiding blocked direct-download hosts;
- project-maintained snapshots whose original provenance can be verified.

Use these files for:

- number of services;
- beneficiaries;
- submitted charges;
- allowed amounts;
- Medicare payments;
- HCPCS mix;
- place of service, when included;
- beneficiary aggregates, when included;
- year-over-year changes.

Provider-by-service data should be organized by NPI, HCPCS code, reporting year, and place of service where available. Provider-level data should preserve aggregated utilization, payment, and beneficiary fields.

Mirror limitations must be explicit. A mirror may be older than the current official release, omit some provider categories, or preserve only selected years. The system must never present an old snapshot as current.

### DMEPOS datasets

Use mirrored DME provider and referring-provider utilization files from Kaggle, research repositories, or previously archived public-use releases.

Use them for:

- supplier-level utilization;
- submitted charges;
- allowed amounts;
- payment amounts;
- HCPCS or product category;
- supplier or referring-provider geography;
- rental indicators where present;
- year-over-year behavior.

### Facility-specific alternatives

Depending on the selected vertical, incorporate accessible copies or independent equivalents of:

- home-health provider data;
- hospice provider data;
- hospital general-information and quality datasets;
- laboratory registries, including CLIA-related public records or state laboratory licensing records;
- nursing-home ownership and affiliation datasets available through public mirrors or state sources;
- state facility licensing lists;
- hospital cost-report datasets mirrored by research repositories;
- HRSA facility data for federally supported health centers;
- CDC or state facility directories where relevant.

The schema must retain the year or reporting period for every observation.

---

## Tier 3: Known adverse outcomes and labels

### HHS OIG LEIE

The List of Excluded Individuals and Entities provides a downloadable, regularly updated list of currently excluded individuals and organizations.

Use it for:

- entity matching;
- network-risk propagation;
- supervised labels with strong caveats;
- testing whether suspicious providers connect to previously excluded entities.

The current LEIE does not include every historical reinstated entity in the same downloadable current file, so snapshots should be archived to create a historical exclusion timeline.

### DOJ healthcare-fraud cases

Collect structured information from DOJ healthcare-fraud announcements and case pages:

- defendant;
- provider or company name;
- NPI when discoverable;
- location;
- alleged scheme;
- service category;
- billing amount;
- date range;
- charges;
- disposition;
- linked parties;
- court jurisdiction.

DOJ maintains healthcare-fraud enforcement functions and publishes cases that can be converted into a case-pattern corpus.

Do not treat every person named in a charging announcement as convicted. Store legal status explicitly:

- alleged;
- charged;
- pleaded guilty;
- convicted;
- sentenced;
- acquitted;
- dismissed;
- civil settlement;
- excluded.

### Additional adverse-action sources

Later phases may include:

- state Medicaid exclusion lists;
- state medical-board disciplinary actions;
- licensing-board sanctions;
- federal civil False Claims Act settlements;
- state attorney-general healthcare-fraud cases;
- SAM.gov exclusions;
- HHS OIG Corporate Integrity Agreements;
- federal court documents where legally and technically accessible.

---

## Tier 4: Public existence and corporate-footprint sources

Potential sources include:

- state secretary-of-state business records;
- state facility licensing databases;
- state professional licensing databases;
- county property or assessor records;
- OpenStreetMap;
- official facility websites;
- public DNS and certificate records;
- website archives;
- permitted business directories;
- public sanctions and enforcement pages.

These sources will vary by state, availability, licensing conditions, robots.txt policies, and terms of use.

Do not build the core product around unauthorized automated scraping of Google Maps, review platforms, or websites that prohibit automated collection. Prefer:

- official APIs;
- open datasets;
- licensed data;
- permitted crawling;
- manual verification links in the user interface.

---

# 6. Synthetic data strategy

Synthetic data should support development and evaluation, not be silently mixed with real evidence.

Create three separate zones:

## Real public data

Used to generate real investigative leads.

## Synthetic training data

Used to train and test models.

## Synthetic scenario data

Used for demonstrations and controlled end-to-end evaluation.

Every record should include:

- `data_origin = public | synthetic`;
- synthetic scenario identifier;
- generator version;
- injection method;
- expected label;
- creation timestamp.

### Fraud scenarios to inject

1. Shell provider at a non-clinical address.
2. Provider registered shortly before a billing surge.
3. Multiple providers sharing a phone number or address.
4. Repeated ownership across rapidly created and dissolved companies.
5. Abnormal concentration in a small number of HCPCS codes.
6. Implausibly high service volumes.
7. Sudden geographic expansion.
8. Provider appearing in multiple distant organizations.
9. Suspicious referral loop.
10. Synthetic note cloning.
11. Reused documents and altered credentials.
12. Entity connected to a known excluded provider.
13. Frequent NPI address changes.
14. Dormant provider becoming suddenly active.
15. “Phoenix” entity replacing a recently sanctioned organization.

Use **Synthea** as the primary synthetic patient and encounter generator. Extend its output with a claims transformation layer that creates:

- claim headers;
- claim lines;
- provider and facility identifiers;
- HCPCS-like service codes;
- diagnosis fields;
- dates of service;
- submitted, allowed, and paid amounts;
- referral relationships;
- synthetic clinical notes;
- credentialing and supporting documents.

Public Kaggle copies of Medicare DE-SynPUF may be used as optional schema references or benchmark data, but the project should not depend on CMS-hosted SynPUF downloads.

---

# 7. Proposed system architecture

```text
                    PUBLIC SOURCES
                          │
          ┌───────────────┼────────────────┐
          │               │                │
 NPI/utilization      OIG/DOJ         Web/state data
 mirrors & archives
          │               │                │
          └───────────────┼────────────────┘
                          ▼
              Ingestion and source registry
                          │
                          ▼
             Raw immutable evidence storage
                          │
                          ▼
          Parsing, normalization and validation
                          │
                          ▼
                  Entity resolution
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      Analytical warehouse        Knowledge graph
             │                         │
             └────────────┬────────────┘
                          ▼
                 Feature/model services
                          │
                          ▼
               ADK investigation agents
                          │
                          ▼
            Evidence fusion and case scoring
                          │
                          ▼
           Provider cases displayed in ADK Web
```

---

# 8. Storage design

Do not use ADK session memory as the primary knowledge base.

ADK supports agents, tools, sessions, state, memory, and artifacts. Those mechanisms are useful for agent context but should not replace the authoritative data layer.

Use four storage layers.

## A. Raw evidence store

Examples:

- Google Cloud Storage;
- local object storage during development;
- MinIO.

Store original:

- CSV and JSON files;
- downloaded webpages;
- HTML;
- PDFs;
- screenshots where legally collected;
- API responses;
- source metadata.

Every artifact should have a cryptographic hash.

## B. Analytical warehouse

Recommended:

- BigQuery for a Google Cloud implementation;
- PostgreSQL or DuckDB for a low-cost prototype.

Store normalized tables and model features.

## C. Knowledge graph

Recommended prototype:

- Neo4j Community Edition;
- PostgreSQL with graph-oriented tables;
- NetworkX for offline experiments.

Possible production alternatives:

- Neo4j;
- Amazon Neptune;
- another managed graph database.

## D. Vector index

Use for:

- enforcement-case retrieval;
- semantic similarity across legal descriptions;
- document similarity;
- website-copy reuse;
- later clinical-note experimentation.

Use pgvector, Qdrant, Weaviate, or another appropriate vector store.

Do not treat the vector database as the system of record.

---

# 9. Core entity model

## Node types

- ProviderIndividual
- ProviderOrganization
- NPI
- ClinicLocation
- Address
- Phone
- Email
- Website
- Domain
- Taxonomy
- HCPCSService
- GroupPractice
- Owner
- Company
- Facility
- License
- Exclusion
- EnforcementCase
- CourtCase
- DataSource
- EvidenceArtifact
- RiskSignal
- InvestigationCase
- ModelRun

## Edge types

- HAS_NPI
- PRACTICES_AT
- ENROLLED_AS
- REASSIGNED_TO
- OWNS
- MANAGES
- SHARES_ADDRESS_WITH
- SHARES_PHONE_WITH
- SHARES_DOMAIN_WITH
- REFERS_TO
- ORDERS_FROM
- BILLS_SERVICE
- ASSOCIATED_WITH_CASE
- EXCLUDED_BY
- SUCCEEDED_ENTITY
- CHANGED_ADDRESS_TO
- EVIDENCED_BY
- SCORED_BY
- REVIEWED_BY

## Temporal properties

Every edge and node should support:

- `valid_from`;
- `valid_to`;
- `observed_at`;
- `source_published_at`;
- `ingested_at`;
- `superseded_by`;
- `confidence`.

This lets the platform answer:

- What did we know about this clinic last month?
- When did its address change?
- Was a relationship known before an enforcement action?
- Did the risk score increase because of new evidence or a model change?

---

# 10. Entity resolution

Entity resolution should be a first-class component, not a side feature.

## Exact-match signals

- NPI;
- license number;
- exact phone number;
- exact normalized address;
- corporate identifier;
- exact domain;
- tax identifier when legally public.

## Probabilistic signals

- similar organization names;
- address abbreviations;
- suite-number differences;
- shared authorized officials;
- phone-number reuse;
- similar websites;
- transliteration or spelling variation;
- historical addresses;
- matching owner names.

## Model output

Each proposed match should contain:

```json
{
  "entity_a": "provider_123",
  "entity_b": "company_781",
  "match_probability": 0.94,
  "matching_features": [
    "same normalized phone",
    "same street address",
    "similar legal name"
  ],
  "conflicting_features": [
    "different suite number"
  ],
  "resolution_status": "auto_linked"
}
```

Set separate thresholds for:

- automatically link;
- request agent review;
- require human review;
- reject.

Incorrectly merging two providers could contaminate the entire knowledge graph, so false merges should be treated as more harmful than missed matches.

---

# 11. Agent architecture in Google AI ADK

## 1. Screening Orchestrator

Responsibilities:

- receives scheduled screening jobs or user requests;
- chooses a provider cohort;
- delegates investigations;
- enforces tool and evidence policies;
- combines the final case packet;
- prevents unsupported allegations.

The orchestrator should not directly scrape or compute model scores.

---

## 2. Data Acquisition Agent

Tools:

- NPI mirror/API connector;
- Medicare utilization mirror downloader;
- ProPublica archive connector;
- Kaggle dataset connector;
- LEIE downloader;
- DOJ page collector;
- SAM.gov connector;
- state-registry connectors;
- permitted web retrieval tool.

Responsibilities:

- checks dataset versions;
- retrieves only changed data;
- validates expected schema;
- records original publisher and mirror metadata;
- saves immutable artifacts;
- opens data-quality incidents when fields unexpectedly change;
- detects stale or discontinued mirrors;
- supports switching between equivalent sources without changing downstream schemas.

---

## 3. Data Quality Agent

Responsibilities:

- detects missing columns;
- identifies schema drift;
- measures null and duplicate rates;
- checks unexpected row-count changes;
- verifies date ranges;
- compares checksums;
- measures mirror lag;
- identifies incomplete state coverage;
- blocks a screening run when the source is unreliable.

Output:

```text
Dataset status: PASS / WARN / FAIL
Original publisher
Mirror or archive
Coverage period
Snapshot date
Freshness
Known limitations
Schema changes
Recommended action
```

---

## 4. Entity Resolution Agent

This agent invokes deterministic matching and probabilistic linkage tools.

Responsibilities:

- resolves NPIs to providers;
- connects provider names to organizations;
- tracks historical addresses;
- proposes cross-source links;
- sends ambiguous matches for review;
- records why each link was accepted.

---

## 5. Billing Anomaly Agent

Model tools:

- peer-group robust z-scores;
- isolation forest;
- gradient-boosted classifier;
- autoencoder;
- change-point detector;
- service-mix entropy calculator;
- year-over-year acceleration model.

Potential signals:

- unusually high payment per beneficiary;
- unusually high number of services per beneficiary;
- extreme service concentration;
- sharp year-over-year growth;
- large deviation from same-specialty, same-state peers;
- sudden change in place-of-service pattern;
- billing profile inconsistent with declared taxonomy;
- high share of uncommon or high-reimbursement codes;
- abrupt activity after a long dormant period.

The agent interprets the outputs but cannot alter the calculated values.

When only older mirrored utilization years are available, the output must be described as a **historical anomaly assessment**, not a live billing finding.

---

## 6. Graph Investigation Agent

Model and algorithm tools:

- degree and weighted-degree calculations;
- community detection;
- PageRank or centrality;
- connected-component analysis;
- link prediction;
- graph embeddings;
- graph anomaly detection;
- later, a graph neural network.

Potential signals:

- many providers sharing one address;
- many organizations sharing one authorized official;
- chains of providers connected to excluded individuals;
- dense referral or ownership clusters;
- repeated reuse of contact information;
- rapid formation of linked companies;
- provider networks that resemble known enforcement cases.

Do not begin with a GNN. Build an interpretable graph baseline first. Introduce a GNN only after obtaining sufficient graph structure and defensible labels.

---

## 7. Geospatial and Physical-Existence Agent

Tools:

- address normalization;
- geocoding through permitted services;
- address-type classification;
- distance matrix;
- land-use lookup where available;
- facility-density comparison;
- OpenStreetMap queries;
- manual map-review links.

Potential signals:

- address cannot be geocoded;
- address appears residential or non-medical;
- numerous unrelated providers share a small location;
- provider changed across distant states repeatedly;
- claimed facility type conflicts with known property or map information;
- location lacks corroborating facility records.

The output should distinguish:

- confirmed mismatch;
- probable mismatch;
- unresolved;
- no concern found.

A virtual office is a risk signal, not proof of fraud.

---

## 8. Corporate and Ownership Agent

Responsibilities:

- retrieves corporate registration information;
- extracts directors and owners;
- detects recently incorporated entities;
- links repeated officers and addresses;
- tracks dissolution and reincorporation;
- identifies successor or “phoenix” organizations;
- searches for links to sanctioned entities.

Because U.S. corporate records are state-specific, build state adapters incrementally rather than one fragile nationwide scraper.

---

## 9. Digital Footprint Agent

Potential evidence:

- official website;
- domain registration timeline;
- certificate history;
- contact details;
- archived website pages;
- listed clinicians;
- appointment functionality;
- reused website content;
- image reuse;
- discrepancies between the website and government records.

Potential signals:

- domain created long after claimed establishment;
- website lists doctors not linked in official records;
- same website content appears across multiple organizations;
- phone or email differs across government and public records;
- site disappears soon after a billing or enforcement event.

Absence of a website should carry little weight on its own.

---

## 10. Enforcement Intelligence Agent

Responsibilities:

- parses DOJ, OIG, SAM.gov, state exclusion, and regulatory actions;
- identifies involved people and companies;
- extracts scheme typologies;
- distinguishes allegations from adjudicated outcomes;
- connects known adverse actors to the provider graph;
- retrieves comparable historical cases.

This agent should create structured case records rather than relying only on vector retrieval.

---

## 11. Synthetic Scenario Agent

Responsibilities:

- generates controlled fraud scenarios;
- injects them into sandbox data;
- records the expected signals;
- runs red-team tests;
- measures whether the system detects each scenario;
- checks whether normal providers are incorrectly flagged.

---

## 12. Evidence Fusion Agent

Responsibilities:

- gathers the outputs of all analytical agents;
- deduplicates overlapping signals;
- assesses source independence;
- separates facts from inferences;
- calculates the final risk band using a deterministic scoring service;
- produces the case narrative.

It must not count the same underlying fact multiple times.

For example:

- “same address as four providers”;
- “high address degree”;
- “address-sharing graph anomaly”

may all arise from one fact and should not receive three independent weights.

---

## 13. Skeptic or Counter-Evidence Agent

This is critical.

Its job is to argue against the suspicious hypothesis.

Questions include:

- Is the shared address a legitimate medical complex?
- Is the billing spike caused by a merger or reporting change?
- Is the specialty comparison inappropriate?
- Is the clinician practicing through a group relationship that the accessible data does not fully expose?
- Is the new website merely a redesign?
- Is the provider’s high volume plausible for laboratory or DME billing?
- Is the sanction match based on a common name?
- Is the underlying source stale?
- Could the anomaly be caused by an incomplete or outdated mirror?

The final report should include both incriminating and exculpatory evidence.

---

## 14. Case Reporter Agent

Produces:

- concise provider summary;
- timeline;
- risk level;
- confirmed facts;
- analytical indicators;
- competing explanations;
- linked entities;
- source citations;
- model outputs;
- recommended next checks;
- data limitations.

It should use controlled language and a fixed report schema.

---

# 12. Model strategy

## Model 1: Provider billing anomaly model

Start with interpretable features and strong tabular baselines:

- logistic regression;
- random forest;
- gradient-boosted trees;
- isolation forest;
- robust peer-group statistics.

Possible training labels:

- DOJ cases mapped confidently to NPI;
- OIG exclusions mapped confidently to providers;
- synthetic positives;
- carefully selected unlabeled or presumed-normal providers.

Important limitation:

LEIE and DOJ outcomes do not represent all fraud, and many exclusions are not ghost-clinic cases. Therefore, labels should include a `label_type` and `scheme_type`.

Older mirrored utilization files are suitable for retrospective model development. They are not sufficient by themselves for claiming current suspicious billing.

## Model 2: Entity-resolution model

Train a pairwise classifier over candidate entity matches.

Features:

- name similarity;
- address similarity;
- phone match;
- officer-name overlap;
- taxonomy compatibility;
- temporal compatibility;
- domain match.

## Model 3: Graph anomaly model

Phase progression:

1. Rules and graph statistics.
2. Community and motif analysis.
3. Node embeddings plus anomaly classifier.
4. GNN only after graph labels and evaluation are credible.

## Model 4: Enforcement-case classifier

Classify enforcement descriptions into typologies:

- phantom billing;
- identity misuse;
- DME fraud;
- telemedicine fraud;
- kickbacks;
- medically unnecessary services;
- laboratory fraud;
- home-health fraud;
- hospice fraud;
- shell-provider behavior;
- prescription fraud;
- documentation falsification.

## Model 5: Document and website similarity model

Use embeddings and perceptual hashes to identify:

- copied descriptions;
- reused staff biographies;
- duplicated policies;
- shared images;
- cloned websites;
- similar credential files in synthetic demonstrations.

---

# 13. Risk-scoring framework

Avoid one opaque “fraud probability.”

Use separate dimensions:

```text
Identity Integrity                0–100
Enrollment Consistency           0–100
Physical Existence               0–100
Billing Anomaly                  0–100
Network Association              0–100
Corporate Complexity             0–100
Adverse History                  0–100
Digital Footprint Consistency    0–100
Evidence Quality                 0–100
```

Then produce:

- overall investigation priority;
- confidence;
- evidence completeness;
- severity;
- recency;
- source diversity.

## Suggested case states

- Monitoring
- Emerging anomaly
- Investigation recommended
- High-priority investigation
- Known enforcement-linked entity
- Resolved benign
- Insufficient evidence
- Data-quality hold

A provider should not reach a high-priority state based only on one anomaly-model score.

Example escalation rule:

```text
High-priority investigation requires:

At least three materially independent signal families,
AND
at least one authoritative government source or strong quantitative anomaly,
AND
no unresolved critical entity-match conflict,
AND
evidence freshness within the required threshold.
```

---

# 14. Incremental knowledge behavior

Each ingestion cycle should:

1. Detect changed source records.
2. Produce entity-level change events.
3. Recompute only affected features.
4. Update the relevant graph neighborhoods.
5. Re-run investigations only where the change is material.
6. Compare the current case with its previous version.
7. Explain why the score moved.
8. Preserve the old report.

Example:

```text
Provider risk changed from 42 to 68.

New evidence:
- Address now shared with six recently enumerated organizations.
- Latest available mirrored utilization snapshot shows service volume increased 430% year over year.
- Authorized official linked to an excluded organization.

Counter-evidence:
- State license remains active.
- Address appears to be a multi-tenant medical building.
- Utilization source is historical and may not reflect current operations.
```

---

# 15. ADK Web experience

ADK Web should serve as the initial investigator interface, not as the permanent database.

## Main screen

Display:

- total providers screened;
- providers with newly changed risk;
- high-priority leads;
- new evidence collected;
- data-source health;
- model and pipeline status.

## Suspicious-provider list

Each row should include:

- provider name;
- NPI;
- specialty or provider type;
- city and state;
- risk band;
- confidence;
- top three indicators;
- score change;
- last screened;
- case status;
- latest utilization-data year.

## Provider case view

### Identity

- names;
- NPIs;
- enrollment or licensing evidence;
- taxonomy;
- addresses;
- phone numbers;
- affiliated organizations.

### Risk summary

- risk dimensions;
- confidence;
- evidence quality;
- escalation reason.

### Timeline

- NPI enumeration;
- address changes;
- licensing or directory changes;
- utilization changes;
- exclusions;
- enforcement links;
- website changes;
- previous system decisions.

### Evidence

For every item:

- exact factual statement;
- source;
- original publisher;
- mirror or archive;
- source date;
- snapshot date;
- retrieval date;
- evidence artifact;
- extraction method;
- confidence;
- agent or model responsible.

### Network

Show a graph centered on:

- provider;
- people;
- companies;
- locations;
- other providers;
- enforcement cases;
- exclusions.

### Analytical outputs

- peer comparison;
- utilization time series;
- service mix;
- graph metrics;
- entity-match confidence;
- geospatial checks.

### Counter-evidence

Display benign explanations and unresolved conflicts prominently.

### Investigation actions

- rescreen;
- expand graph;
- compare with peers;
- inspect source;
- mark false positive;
- request manual review;
- add investigator note;
- export case packet.

---

# 16. Proposed output schema

```json
{
  "case_id": "SP-US-00001234",
  "provider": {
    "canonical_name": "Example Medical Group LLC",
    "npi": "1234567890",
    "provider_type": "Organization",
    "taxonomy": ["..."],
    "locations": ["..."]
  },
  "case_status": "investigation_recommended",
  "risk": {
    "priority_score": 78,
    "confidence": 0.82,
    "evidence_quality": 74,
    "dimensions": {
      "identity_integrity": 58,
      "physical_existence": 71,
      "billing_anomaly": 89,
      "network_association": 83,
      "adverse_history": 46
    }
  },
  "signals": [
    {
      "signal_id": "SIG-1001",
      "type": "billing_growth_outlier",
      "fact": "Annual service volume increased by 418% in the latest available mirrored utilization period.",
      "peer_percentile": 99.7,
      "severity": "high",
      "source_ids": ["MIRROR-MEDICARE-PPS-..."],
      "original_publisher": "U.S. federal public-use data",
      "mirror_provider": "ProPublica/Kaggle/research archive",
      "source_period": "2023",
      "first_observed": "2026-08-01",
      "model_version": "billing-xgb-0.3.0"
    }
  ],
  "counter_evidence": [],
  "linked_entities": [],
  "timeline": [],
  "limitations": [],
  "recommended_checks": [],
  "generated_at": "...",
  "report_version": 4
}
```

---

# 17. Evaluation framework

The project needs three different evaluations.

## A. Model evaluation

Metrics:

- precision;
- recall;
- PR-AUC;
- ROC-AUC;
- precision at top K;
- false-positive rate;
- calibration;
- detection lead time.

Because fraud labels are severely incomplete, precision at top K and investigator yield may be more meaningful than ordinary accuracy.

Retrospective evaluations must use the source period, not the date on which the mirror was downloaded.

## B. Agent evaluation

Test whether agents:

- call the correct tool;
- preserve source provenance;
- distinguish allegations from convictions;
- avoid unsupported conclusions;
- identify counter-evidence;
- produce schema-valid outputs;
- avoid duplicate evidence;
- refrain from inventing NPIs or relationships;
- correctly disclose stale or incomplete mirrored data.

## C. End-to-end scenario evaluation

Create synthetic cases for each fraud pattern and verify:

- which signals are detected;
- time to detection;
- final risk band;
- explanation quality;
- whether benign controls remain unflagged.

---

# 18. Finding a real-world candidate

A responsible real-world demonstration should use a retrospective-first approach.

## Stage 1: Retrospective validation

Select providers already associated with finalized enforcement outcomes.

Hide the outcome from the screening system and use only information that would have been publicly available before the enforcement date.

Then ask:

- Would Specter have ranked the entity highly?
- Which signals appeared first?
- How much advance warning was possible?
- Which signals were only visible after enforcement?
- Did similar legitimate providers receive high scores?

This is the strongest and safest proof of concept.

For utilization evidence, freeze the exact mirrored or archived dataset version that corresponds to the historical cutoff.

## Stage 2: Prospective screening

Run the system on currently active providers using current identity, licensing, corporate, exclusion, web, and geospatial sources, plus the latest accessible utilization snapshot.

Publish findings only as anonymized or internally reviewed investigative leads unless the evidence already appears in authoritative public enforcement records.

Clearly distinguish:

- current public facts;
- historical billing anomalies;
- unresolved inferences;
- synthetic test results.

## Stage 3: External validation

Possible routes:

- collaborate with a healthcare-fraud researcher;
- work with an insurer or payment-integrity team;
- partner with a university;
- submit high-confidence evidence through an appropriate government reporting channel;
- compare flagged providers with future enforcement outcomes.

The project should never contact, harass, impersonate, or publicly accuse a provider.

---

# 19. Implementation phases

## Phase 0: Definitions and governance

Deliverables:

- operational definition of “ghost clinic”;
- broader fraud taxonomy;
- evidence policy;
- prohibited conclusions;
- source-usage policy;
- case status vocabulary;
- ethical and legal review checklist.

## Phase 1: Data foundation

Build:

- NPI mirror/API downloader and parser;
- state licensing and facility-registry connectors;
- Medicare utilization mirror ingestion;
- ProPublica archive connector;
- Kaggle dataset connector;
- LEIE snapshot pipeline;
- DOJ case collector;
- SAM.gov connector;
- raw evidence store;
- normalized warehouse;
- source registry;
- data-quality and mirror-freshness checks.

Output:

A searchable, historical provider database.

## Phase 2: Baseline screening

Build:

- provider cohorts;
- peer-group definition;
- rule-based risk indicators;
- robust statistical outlier detection;
- initial ADK agents;
- provider list and case-report output in ADK Web.

Output:

Ranked leads with explainable, deterministic signals.

## Phase 3: Entity and graph intelligence

Build:

- entity-resolution service;
- knowledge graph;
- shared-attribute analysis;
- graph communities;
- relationship timeline;
- graph investigation agent.

Output:

Provider networks rather than isolated provider scores.

## Phase 4: Trained models

Train:

- billing anomaly model;
- entity-resolution model;
- enforcement typology classifier;
- graph anomaly model;
- risk calibration layer.

Output:

Versioned model tools callable by ADK agents.

## Phase 5: OSINT and physical-existence checks

Add permitted:

- state licensing lookups;
- corporate registry adapters;
- address classification;
- OpenStreetMap checks;
- website and domain analysis;
- archive comparisons.

Output:

A digital and physical existence profile for high-risk entities.

## Phase 6: Synthetic red-team environment

Build:

- Synthea-based patient and encounter generation;
- claims transformation layer;
- fraud scenario generator;
- normal-provider controls;
- scenario benchmark;
- regression suite;
- agent evaluation harness.

Output:

Repeatable proof that the system detects known patterns without depending on anecdotes.

## Phase 7: Retrospective real-case validation

Build historical case cohorts from adjudicated enforcement actions.

Run time-aware backtests using only evidence available before each cutoff date and the correct archived utilization snapshot.

Output:

A defensible evaluation of whether Specter could have surfaced known schemes earlier.

## Phase 8: Controlled prospective pilot

Run recurring screening on one provider category and limited geography.

Require human approval for high-priority designations.

Output:

A monitored, real-world research pilot.

---

# 20. Recommended first MVP

The first MVP should be narrower than the final vision.

## Cohort

One provider category across the United States, such as DME suppliers.

## Sources

- NPI Registry API where accessible, otherwise a versioned NPPES mirror or local snapshot;
- one accessible Medicare provider-by-service or DME utilization mirror from Kaggle, ProPublica, or a research repository;
- state licensing or facility records for the selected cohort;
- HHS OIG LEIE;
- DOJ enforcement pages;
- SAM.gov exclusions and entity records;
- Synthea-generated claims for controlled tests.

## Agents

1. Orchestrator.
2. Data Quality Agent.
3. Entity Resolution Agent.
4. Billing Anomaly Agent.
5. Graph Agent.
6. Enforcement Intelligence Agent.
7. Skeptic Agent.
8. Case Reporter Agent.

## Models

- isolation forest;
- gradient-boosted tabular classifier;
- probabilistic entity matcher;
- basic graph anomaly score.

## MVP output

For every screened provider:

- canonical identity;
- licensing and registry profile;
- historical utilization profile;
- peer anomalies;
- adverse-action matches;
- connected entities;
- top signals;
- counter-evidence;
- evidence links;
- investigation priority;
- historical score changes;
- source freshness and mirror limitations.

Do not include clinical-note NLP or document-forgery detection in the first public-data MVP. Public data normally will not provide the clinical notes, utility bills, leases, insurance claim documents, or credentialing documents required to test those capabilities properly. Keep them as synthetic or partner-data modules.

---

# 21. Suggested technology stack

## Agent layer

- Google AI ADK, Python;
- Gemini model for orchestration and evidence synthesis;
- structured outputs using Pydantic models;
- deterministic agent workflows for critical steps.

## Data and orchestration

- Python;
- Polars or Pandas;
- DuckDB for development;
- PostgreSQL or BigQuery for normalized data;
- Cloud Scheduler or an external workflow scheduler;
- Prefect, Dagster, Airflow, or Cloud Workflows for ingestion jobs;
- Kaggle API for permitted dataset downloads;
- source-specific adapters for ProPublica, OIG, DOJ, SAM.gov, state registries, and mirrors.

Do not use an LLM agent as the scheduler for routine ETL.

## Graph

- NetworkX for prototypes;
- Neo4j Community Edition or PostgreSQL graph tables for the MVP.

## ML

- scikit-learn;
- XGBoost or LightGBM;
- PyTorch Geometric later;
- MLflow for experiment tracking and model registry.

## Retrieval

- PostgreSQL full-text search;
- pgvector or Qdrant for semantic retrieval.

## Observability

- structured application logs;
- ADK traces;
- source and tool-call audit logs;
- OpenTelemetry;
- model-drift monitoring;
- data-quality dashboards;
- mirror freshness and availability monitoring.

---

# 22. Non-negotiable safeguards

1. Every claim must cite stored evidence.
2. Facts, model inferences, and LLM hypotheses must be visibly separated.
3. Allegations must not be presented as convictions.
4. A risk score must not be described as a probability of guilt unless it is demonstrably calibrated for that exact interpretation.
5. Common-name matches cannot automatically create adverse links.
6. The system must preserve counter-evidence.
7. High-risk findings require human review.
8. Raw public data and synthetic data must remain distinguishable.
9. Source terms, API restrictions, licenses, and robots.txt requirements must be respected.
10. The public-facing system should not expose unnecessary personal information.
11. Every score must be reproducible from a model version and feature snapshot.
12. Providers must be removable from active watchlists when evidence is corrected or resolved.
13. A mirror must never be represented as more current or authoritative than its underlying snapshot.
14. Records from unofficial mirrors must preserve original provenance and be independently validated where possible.
15. Missing official enrollment information must be represented as unknown, not as evidence of fraud.

---

# 23. Final definition of success

Project Specter succeeds when it can:

- continuously screen a defined U.S. provider population;
- create a reliable longitudinal identity for each provider;
- detect meaningful changes and anomalies;
- uncover networks that claim-level rules miss;
- explain each finding with traceable evidence;
- identify benign explanations;
- reproduce its decisions;
- surface known enforcement-linked providers in retrospective tests;
- generate a manageable number of high-quality leads for human investigators;
- remain usable when a primary government portal is blocked by switching to validated mirrors and independent sources without losing provenance.

The initial research claim should therefore be:

> Project Specter is an evidence-grounded, multi-agent provider-risk intelligence system that combines accessible public healthcare-utilization archives, provider identity and licensing records, enforcement intelligence, graph analytics, anomaly models, and incremental investigation workflows to surface potentially suspicious U.S. healthcare provider entities and networks.

It should not initially claim:

> Project Specter definitively identifies ghost clinics from public internet data.

---

## Accessible-source replacement matrix

| Original dependency | Replacement for the project | Important limitation |
|---|---|---|
| NPPES bulk download on CMS | Working NPI Registry API; versioned Kaggle/Hugging Face/institutional NPPES mirror; locally archived snapshot | Mirrors can be incomplete or stale |
| PECOS-derived enrollment files | State licensing and facility records, SAM.gov, LEIE, public directory mirrors, archived enrollment datasets | No single free substitute provides complete PECOS equivalence |
| Medicare provider/service utilization files | Kaggle Medicare datasets, ProPublica Data Store archive, university/research repositories, frozen project snapshots | Often historical rather than live |
| DME provider/service files | Kaggle or research mirrors of DME public-use files, archived releases | Coverage and reporting years vary |
| Facility datasets | State health departments, HRSA, CDC/state directories, Kaggle/BigQuery public hospital datasets, research mirrors | Schemas differ by source and state |
| CMS synthetic claims | Synthea plus a custom claims/document generator; optional Kaggle DE-SynPUF copies | Synthetic behavior must not be treated as real-world evidence |
| CMS metadata pages | Data.gov catalog entries, research documentation, mirror data dictionaries, archived documentation | Verify schema against the actual downloaded file |

## Practical source policy

For every external dataset, create a source manifest containing:

```yaml
source_id: unique-source-id
dataset_name: human-readable name
original_publisher: original issuing organization
access_provider: mirror, archive, API, or repository used
source_url: stored internally
license_or_terms: applicable terms
snapshot_date: date represented by the data
retrieved_at: download timestamp
checksum_sha256: file checksum
schema_version: project schema version
coverage: states, provider types, and years covered
freshness_status: current, delayed, historical, or unknown
known_limitations:
  - limitation one
  - limitation two
```

This source-abstraction layer is what allows the project to switch away from blocked portals without changing the agent architecture or silently degrading evidentiary quality.
