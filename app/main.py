"""FastAPI service — the REST layer n8n talks to.

Endpoints:
  GET  /health                       liveness check
  POST /analyse-protocol             main use case (see README)
  GET  /deliverables/{deliverable_id} small lookup service, independent REST call
"""
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402

from .deliverables import get_deliverable, load_deliverables  # noqa: E402
from .llm import LLMExtractionError, extract_structured  # noqa: E402
from .models import AnalyseRequest, AnalyseResponse, Deliverable  # noqa: E402
from .rules import check_issues  # noqa: E402

app = FastAPI(
    title="EPCM Decision & Interface Action Tracker",
    description=(
        "Extracts decisions, actions, owners, deadlines and affected "
        "deliverables from EPCM meeting protocols, and flags simple "
        "coordination issues using deterministic rules."
    ),
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyse-protocol", response_model=AnalyseResponse)
def analyse_protocol(request: AnalyseRequest):
    # 1. Basic input validation -> HTTP 400 (Pydantic already rejects a
    #    missing "text" field entirely; this catches an empty/blank string).
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Field 'text' must not be empty.")

    # 2. Semantic extraction via LLM, validated against a Pydantic schema.
    try:
        extraction = extract_structured(request.text)
    except LLMExtractionError as exc:
        # Controlled failure -> HTTP 502 (upstream/LLM problem, not our bug).
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 3. Deterministic rule checks, enriched with the deliverables register.
    deliverables_index = load_deliverables()
    issues, requires_attention = check_issues(extraction, deliverables_index)

    # 4. Structured JSON response back to n8n.
    return AnalyseResponse(
        project_id=request.project_id,
        decisions=extraction.decisions,
        actions=extraction.actions,
        issues=issues,
        requires_attention=requires_attention,
    )


@app.get("/deliverables/{deliverable_id}", response_model=Deliverable)
def get_deliverable_endpoint(deliverable_id: str):
    deliverable = get_deliverable(deliverable_id)
    if deliverable is None:
        raise HTTPException(
            status_code=404, detail=f"Deliverable '{deliverable_id}' not found."
        )
    return deliverable
