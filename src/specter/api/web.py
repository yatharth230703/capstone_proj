"""The judge-facing server-rendered UI (M14, CLAUDE.md Amendment 4(a)) over
M13's own JSON API. Mounted under `/ui` so it never collides with M13's
existing `GET /cohort`/`/cases/{npi}`/`/judge` routes on the same app — the
Scope section's own `/ui/cases/{npi}` wording is what this follows; an
earlier draft of this Action Plan's Steps text said `/cases/{npi}` for the
page route too, which would have shadowed M13's JSON endpoint of the same
path (see BUILD_MILESTONES.md M14 Result).

Every page calls the same M13 router functions directly — `cases.
cohort_overview(request)`, `cases.case_detail(npi, request)`,
`judge.judge_report()` — rather than round-tripping HTTP to this same
process. `Jinja2Templates` autoescapes `.html` templates by default
(`select_autoescape`), so LLM-authored prose (case narratives, judge report
text) is safe to interpolate directly.

Nothing here generates new data. The one write path stays exactly where
M13 put it, `POST /research` — the case-detail template's "run grounded
research" button calls it via a plain browser `fetch()`, user-triggered
only, never on page load or a timer.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from specter.api import cases, costs, judge

router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@router.get("/ui")
def cohort_page(request: Request) -> HTMLResponse:
    cohort = cases.cohort_overview(request)
    cost_data = costs.costs()
    tier_values = cohort["priority_tier_counts"].values()
    signal_values = cohort["signal_type_counts"].values()
    return _templates.TemplateResponse(
        request,
        "cohort.html",
        {
            "cohort": cohort,
            "costs": cost_data,
            "max_tier_count": max(tier_values) if tier_values else 0,
            "max_signal_count": max(signal_values) if signal_values else 0,
        },
    )


@router.get("/ui/cases/{npi}")
def case_page(npi: str, request: Request) -> HTMLResponse:
    detail = cases.case_detail(npi, request)
    return _templates.TemplateResponse(request, "case_detail.html", {"detail": detail})


@router.get("/ui/judge")
def judge_page(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "judge.html", {"judge": judge.judge_report()})
