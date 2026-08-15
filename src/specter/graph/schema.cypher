// Project Specter graph schema (plan §6.1). 11 node types, 11 relationship
// types. Every node and relationship carries: data_origin, source_id,
// observed_at, ingested_at, confidence (not enforced by constraints below —
// Pydantic contracts at the loader boundary are what actually guarantee
// this; Cypher constraints below only cover natural-key uniqueness).
//
// Temporal valid_from/valid_to live only on LOCATED_AT, HAS_PHONE,
// HAS_OFFICER — the relationships that actually change over a provider's
// life. Do not add them elsewhere; it costs write throughput for no
// Phase 1 benefit.
//
// Idempotent: every statement is IF NOT EXISTS, safe to re-run.

// --- Provider ---
CREATE CONSTRAINT provider_npi IF NOT EXISTS
  FOR (p:Provider) REQUIRE p.npi IS UNIQUE;
CREATE INDEX provider_state IF NOT EXISTS FOR (p:Provider) ON (p.state);
CREATE INDEX provider_enum_date IF NOT EXISTS FOR (p:Provider) ON (p.enumeration_date);

// --- Address ---
// normalized_key = street_number|street_name_normalized|street_type_abbrev|zip5
// (unit/suite deliberately excluded — see CLAUDE.md "Address normalization")
CREATE CONSTRAINT address_key IF NOT EXISTS
  FOR (a:Address) REQUIRE a.normalized_key IS UNIQUE;

// --- Phone ---
CREATE CONSTRAINT phone_e164 IF NOT EXISTS
  FOR (ph:Phone) REQUIRE ph.e164 IS UNIQUE;

// --- Officer ---
// No uniqueness constraint: name collisions (e.g. "John Smith") are expected
// and disambiguation is an entity-resolution problem (M4/M5), not a DB
// constraint. officer_id is a deterministic hash assigned at load time so
// the *same* raw (name, state) pair always maps to the same node.
CREATE CONSTRAINT officer_id IF NOT EXISTS
  FOR (o:Officer) REQUIRE o.officer_id IS UNIQUE;
CREATE INDEX officer_last_name IF NOT EXISTS FOR (o:Officer) ON (o.last_name);

// --- Taxonomy ---
CREATE CONSTRAINT taxonomy_code IF NOT EXISTS
  FOR (t:Taxonomy) REQUIRE t.code IS UNIQUE;

// --- Exclusion ---
// exclusion_id is deterministic (hash of exclusion_authority + jurisdiction +
// source row content) since neither LEIE nor state lists provide a clean
// numeric ID. CLAUDE.md Amendment 1 discriminator fields:
CREATE CONSTRAINT exclusion_id IF NOT EXISTS
  FOR (e:Exclusion) REQUIRE e.exclusion_id IS UNIQUE;
CREATE INDEX exclusion_authority IF NOT EXISTS FOR (e:Exclusion) ON (e.exclusion_authority);
CREATE INDEX exclusion_jurisdiction IF NOT EXISTS FOR (e:Exclusion) ON (e.jurisdiction);
CREATE INDEX exclusion_npi IF NOT EXISTS FOR (e:Exclusion) ON (e.npi);

// --- EnforcementCase ---
CREATE CONSTRAINT enforcement_case_id IF NOT EXISTS
  FOR (c:EnforcementCase) REQUIRE c.case_id IS UNIQUE;
CREATE INDEX enforcement_case_legal_status IF NOT EXISTS
  FOR (c:EnforcementCase) ON (c.legal_status);

// --- Community ---
CREATE CONSTRAINT community_id IF NOT EXISTS
  FOR (cm:Community) REQUIRE cm.community_id IS UNIQUE;

// --- DataSource --- (one node per SourceManifest.source_id)
CREATE CONSTRAINT data_source_id IF NOT EXISTS
  FOR (ds:DataSource) REQUIRE ds.source_id IS UNIQUE;

// --- EvidenceArtifact ---
CREATE CONSTRAINT evidence_artifact_id IF NOT EXISTS
  FOR (ev:EvidenceArtifact) REQUIRE ev.artifact_id IS UNIQUE;

// --- RiskSignal ---
// No uniqueness constraint — the same signal_type recomputes per screening
// run and is expected to recur. Indexed for the tools/signal_tools.py read
// path (get_provider_profile, hybrid retrieval).
CREATE INDEX risk_signal_npi_type IF NOT EXISTS
  FOR (rs:RiskSignal) ON (rs.provider_npi, rs.signal_type);

// --- Vector indexes ---
// text-embedding-3-large is 3072-dim. If dimensions is reduced via the API
// `dimensions` parameter, both indexes below must be updated to match.
CREATE VECTOR INDEX case_embedding IF NOT EXISTS
  FOR (c:EnforcementCase) ON (c.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072,
                          `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX community_embedding IF NOT EXISTS
  FOR (cm:Community) ON (cm.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072,
                          `vector.similarity_function`: 'cosine'}};

// --- Relationships ---
// LOCATED_AT (Provider -> Address), HAS_PHONE (Provider -> Phone),
// HAS_OFFICER (Provider -> Officer): valid_from/valid_to live on these three.
// HAS_TAXONOMY (Provider -> Taxonomy)
// EXCLUDED_BY (Provider -> Exclusion)
// MENTIONED_IN (Provider -> EnforcementCase)
// CHANGED_ADDRESS_TO (Address -> Address, chronological)
// IN_COMMUNITY (Provider -> Community)
// EVIDENCED_BY (RiskSignal|EnforcementCase|CasePacket claim -> EvidenceArtifact)
// SIGNAL_ON (RiskSignal -> Provider)
// SUCCEEDS (Provider -> Provider, phoenix-pattern successor link)
//
// Relationship properties aren't constrained by Cypher schema (Neo4j doesn't
// support relationship property existence/uniqueness constraints the way
// node labels do here); the loader's Pydantic contracts are the enforcement
// point for data_origin/source_id/observed_at/ingested_at/confidence.
