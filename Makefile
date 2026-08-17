.PHONY: demo

# Reproduces plan §14's demo script end to end against the real CLI surface
# (BUILD_MILESTONES.md M10). Real Azure calls — costs money.
demo:
	docker compose up -d
	docker compose ps
	uv run python scripts/40_screen.py --limit 250
	uv run python scripts/40_screen.py --limit 250
	uv run python -m specter.cli dashboard
	uv run python scripts/50_judge.py
