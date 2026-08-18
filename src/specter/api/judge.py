"""Judge report endpoint (M13). Serves the real, already-generated
`JudgeReport.md` (CLAUDE.md Amendment 2's five self-preference-bias
mitigations), split into JSON by its own `## ` section headers.

**Deliberately does not re-run the rubric judge or re-derive it from
`judge/detection_eval.py` at request time**, despite the M13 Action Plan's
stated preference for that ("cleaner than regexing markdown"): the report's
scenario/rubric sections need a *live* M5 agent chain run per scenario
(`scripts/50_judge.py`'s `_build_scenario_case` — real Azure calls) and the
rubric judge itself (`judge/rubric_judge.judge_case`, three more real Azure
calls per case at T2 pricing) — neither `JudgeVerdict` nor the scenario
corpus is persisted anywhere on disk. Re-running either per HTTP GET would
(a) cost real money on every request and (b) violate this milestone's own
scope ("no new data is generated in this milestone"). Parsing the persisted
markdown by section boundary — not a fine-grained number regex — is the
honest way to expose what's real without either problem; see
BUILD_MILESTONES.md M13 Result for this deviation, recorded there per §0.2's
"verify, don't assume" rule.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from specter.core.errors import SpecterError

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
JUDGE_REPORT_PATH = _REPO_ROOT / "JudgeReport.md"
_SECTION_HEADER_RE = re.compile(r"^## (.+)$", re.MULTILINE)


@router.get("/judge")
def judge_report() -> dict[str, Any]:
    if not JUDGE_REPORT_PATH.exists():
        raise SpecterError(
            f"{JUDGE_REPORT_PATH} is missing — run `python scripts/50_judge.py` "
            "to regenerate it (real Azure calls, costs money — run by hand)."
        )
    text = JUDGE_REPORT_PATH.read_text()
    headers = list(_SECTION_HEADER_RE.finditer(text))
    limitation_block = (text[: headers[0].start()] if headers else text).strip()

    sections: dict[str, str] = {}
    for i, match in enumerate(headers):
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()

    return {"limitation_block": limitation_block, "sections": sections}
