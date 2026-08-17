#!/usr/bin/env bash
# Clean-machine setup (BUILD_MILESTONES.md M10, plan §14 step 1).
#
#   bash scripts/00_bootstrap.sh
#
# Installs deps, brings up neo4j/phoenix/redis, waits for them healthy, and
# creates the Neo4j read-only user (CLAUDE.md "Neo4j MCP guardrails").
# Does NOT populate .env, ingest data, or build the graph — those are
# scripts/10_ingest.py / scripts/20_build_graph.py, run separately once real
# credentials exist.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example. Fill in AZURE_API_KEY/AZURE_API_BASE" \
       "and the Vertex GOOGLE_* vars before running any live agent."
  cp .env.example .env
fi

echo "Installing dependencies (uv sync)..."
uv sync

echo "Starting infra (neo4j, phoenix, redis)..."
docker compose up -d

echo "Waiting for containers to report healthy..."
for i in $(seq 1 30); do
  unhealthy=$(docker compose ps --format '{{.Health}}' | grep -vc '^healthy$' || true)
  if [ "$unhealthy" -eq 0 ]; then
    echo "All containers healthy."
    break
  fi
  sleep 2
done
docker compose ps

echo "Bootstrapping Neo4j read-only user (specter_ro)..."
uv run python scripts/06_bootstrap_neo4j_readonly.py

echo "Bootstrap complete. Next: uv run python scripts/10_ingest.py --live, then --freeze," \
     "then scripts/20_build_graph.py, then scripts/40_screen.py."
