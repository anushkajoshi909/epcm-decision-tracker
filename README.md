# EPCM Decision & Interface Action Tracker

A tiny, end-to-end prototype: **one meeting protocol → one automated
structured result → one warning.**

Built as interview preparation for an AI & Automation Engineer role in the
EPCM/construction industry. It's deliberately adjacent to — not a copy of —
the kinds of prototypes that team is known to work on (early project
warning, document control, deliverable status checking). This one focuses on
a different, common gap: **decisions and actions buried inside meeting
protocols**, where a missing owner or a missed deadline on a cross-discipline
dependency is easy to lose track of.

All data in `data/` is synthetic. No real Drees & Sommer information is used
anywhere in this repository.

---

## 1. Architecture

```
Meeting protocol (text)
        |
        v
   n8n Webhook  ───────────────────────────────────────────┐
        |                                                   │ POST JSON
        v                                                   │
FastAPI  POST /analyse-protocol  <───────────────────────────┘
        |
        |-- 1. validate input (missing text -> HTTP 400)
        |-- 2. call LLM API, ask for structured JSON only
        |-- 3. validate LLM output against a Pydantic schema
        |         (invalid -> one controlled retry, then HTTP 502)
        |-- 4. run deterministic Python rule checks
        |         (missing owner, missing deadline, deadline passed,
        |          unresolved dependency, unknown/closed deliverable)
        |-- 5. optionally cross-check against data/deliverables.csv
        |         via GET /deliverables/{id}
        v
Structured JSON  { decisions, actions, issues, requires_attention }
        |
        v
   n8n IF requires_attention == true
        |
        v
   Create/log warning  (stubbed - not wired to Teams/email yet)
```

Two REST endpoints, five Python modules, three synthetic protocols, one CSV,
one n8n workflow, one eval script. That's the whole MVP.

---

## 2. Project layout

```
epcm-decision-tracker/
├── app/
│   ├── main.py          FastAPI app + routes
│   ├── models.py        Pydantic schemas (LLM contract + API contract)
│   ├── llm.py            LLM call + structured-output validation/retry
│   ├── rules.py          deterministic business rules
│   └── deliverables.py   tiny CSV-backed "deliverables register"
├── data/
│   ├── meeting_protocol_0{1,2,3}.txt   synthetic EPCM protocols
│   └── deliverables.csv                synthetic deliverables register
├── n8n/
│   ├── epcm_workflow.json   importable workflow
│   └── README.md            how to import it / build it by hand
├── eval/
│   ├── test_cases.json      8 synthetic cases with expected values
│   └── run_eval.py          hits the running API and scores it
├── requirements.txt
└── .env.example
```

---

## 3. Setup

```bash
cd epcm-decision-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# defaults to the SCADS.AI endpoint, reading the key from
# ~/.scadsai-api-key. To use a different OpenAI-compatible endpoint
# instead, edit .env: set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

uvicorn app.main:app --reload
```

The API is now at `http://127.0.0.1:8000`. Interactive docs (auto-generated
by FastAPI from the Pydantic models) are at `http://127.0.0.1:8000/docs`.

---

## 4. Using the API

### Health check
```bash
curl http://127.0.0.1:8000/health
```

### Analyse a protocol
```bash
curl -X POST http://127.0.0.1:8000/analyse-protocol \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ALPHA",
    "text": "During today'\''s coordination meeting, the HVAC layout was changed because of a new ceiling requirement. Electrical must review the cable routing based on the new HVAC layout. Updated drawings are required before 15 September. No responsible person has currently been assigned for the electrical review. Construction Package EL-04 depends on this clarification."
  }'
```

Expect something close to:
```json
{
  "project_id": "PROJECT_ALPHA",
  "decisions": [
    {"decision": "HVAC layout changed due to new ceiling requirement", "affected_disciplines": ["HVAC", "Electrical"]}
  ],
  "actions": [
    {"action": "Review electrical cable routing", "owner": null, "deadline": "2026-09-15",
     "affected_deliverable": "EL-04", "dependencies": ["Updated HVAC layout"]}
  ],
  "issues": [
    {"type": "missing_owner", "severity": "high", "message": "No owner is assigned for action: 'Review electrical cable routing'"}
  ],
  "requires_attention": true
}
```

### Look up a deliverable
```bash
curl http://127.0.0.1:8000/deliverables/EL-04
curl -i http://127.0.0.1:8000/deliverables/DOES-NOT-EXIST   # -> 404
```

### Error cases (deliberately included, kept small)
| Situation | Response |
|---|---|
| `text` field missing/blank | `400 Bad Request` |
| LLM returns invalid/non-schema JSON twice in a row | `502 Bad Gateway` (one controlled retry happens first) |
| Unknown `deliverable_id` | `404 Not Found` |
| FastAPI process is down | n8n's HTTP Request node fails → its own error output path |

---

## 5. n8n workflow

See [`n8n/README.md`](n8n/README.md). Six nodes: **Webhook → HTTP Request →
IF → Code (log warning) → Respond to Webhook → Notify Discord**. n8n does no
business logic itself — it only routes based on the `requires_attention`
boolean that FastAPI already computed, and posts the warning to a Discord
channel when true.

The Discord node reads its webhook URL from `{{ $env.DISCORD_WEBHOOK_URL }}`
rather than a hardcoded value, so the real URL only ever lives in an
environment variable on whichever machine runs n8n — see `RUNBOOK.md` for
how to set it. Never paste a real webhook/API URL directly into a workflow
JSON that gets committed: if that ever happens, the fix is to revoke the
credential (e.g. delete and recreate the Discord webhook) immediately,
since removing it from git afterward doesn't undo a public exposure.

---

## 6. Evaluation

```bash
# with the API running in another shell:
python eval/run_eval.py
```

`eval/test_cases.json` has 8 synthetic protocols, each with hand-defined
expected values (decision detected, action detected, owner, deadline,
affected deliverable, missing-owner flag, unresolved-dependency flag,
requires_attention). `run_eval.py` calls the live API for each, compares
actual vs. expected field by field, prints per-case and aggregate accuracy,
and reports precision/recall for `requires_attention` treated as a binary
classifier. This isn't meant to be a rigorous benchmark — it's meant to show
the prototype was actually tested, not just demoed once by hand.

---

## 7. REST / webhook concepts this project is built to exercise

- **REST API**: FastAPI exposes resources (`/analyse-protocol`,
  `/deliverables/{id}`) over HTTP, using standard methods (`POST` to create
  an analysis, `GET` to read a deliverable) and status codes (`200`, `400`,
  `404`, `502`) to communicate outcome — not just a 200 with an error string
  buried in the body.
- **Webhook**: n8n's Webhook node is *itself* the server side of a webhook —
  it exposes a URL that something else calls (a form, a Teams bot, a script)
  the moment an event happens. This is different from...
- **REST request**: ...n8n's HTTP Request node, which is n8n acting as a
  *client*, actively calling FastAPI's REST API. In one workflow, n8n is a
  webhook receiver on one side and a REST client on the other — a good
  concrete example of "webhook vs. REST call" instead of an abstract one.
- **JSON over HTTP both ways**: n8n sends `{"project_id": ..., "text": ...}`
  as a JSON body to FastAPI; FastAPI validates it against the
  `AnalyseRequest` Pydantic model, and returns JSON validated against
  `AnalyseResponse`. Same content type, same serialization, both directions.
- **Headers**: `Content-Type: application/json` on both the request and
  response is what tells each side how to parse the body.
- **Status codes as control flow**: n8n's IF node branches on a field
  *inside* a `200` response (`requires_attention`), while a `400`/`404`/`502`
  would instead show up in n8n's HTTP Request node as a request failure —
  two different mechanisms for two different kinds of "something to react
  to."

---

## 8. Why these technologies (and not others)

**Why n8n for orchestration, not just Python glue code?**
Because the orchestration here is genuinely a workflow with branching and a
notification step — exactly what n8n is for — and it's also the tool this
role expects hands-on familiarity with. A shell script or a Python `if`
statement could do the same routing, but wouldn't demonstrate webhook/REST
orchestration skills. n8n is also how this would realistically plug into
enterprise systems (Teams, email, SharePoint) later without touching the
FastAPI code.

**Why Python/FastAPI for the actual logic, not an n8n Code node for
everything?**
Because Pydantic validation, retry logic, and rule checks are non-trivial
enough to want real tests, type checking, and version control — n8n Code
nodes are fine for small glue expressions (see the warning-formatting step)
but not for a schema-validated service boundary.

**Why the LLM is only used for semantic extraction, never for the rule
checks:**
"Is there an owner named in this sentence?" requires understanding free
text — that's what LLMs are for. "Is `owner` null?" and "Is this deadline
before today?" are exact, deterministic questions with one right answer
every time; asking an LLM to answer them would make the result
non-reproducible, slower, and harder to unit test for no benefit. The
architectural rule followed throughout: **use deterministic code when the
rule is known, use the LLM only where interpretation of language is
required.**

**Why Pydantic structured output instead of parsing free-form LLM text:**
Free-form text extraction ("please list the decisions...") is brittle to
parse and silently drifts in format between calls. Defining `LLMExtraction`
as a Pydantic model gives one explicit contract, machine-checked on every
call, with a controlled retry when the model doesn't comply — instead of
regex-scraping prose.

**Why this doesn't need LangGraph:**
The flow is a straight line: extract → apply rules → return. There's no
loop, no "is this good enough, should I go fetch more context and try
again" state machine yet. LangGraph earns its place when the workflow
becomes *stateful and conditional across multiple LLM calls* — for example
the RAG-augmented "extract → check sufficiency → retrieve context →
reassess" idea sketched in Extension 2 below. Introducing it now for a
linear sequence would be a framework for its own sake.

**Why this doesn't need multiple agents:**
There's one job (extract + check), not multiple specialists that need to
negotiate or hand off work to each other. A single LLM call plus
deterministic Python already does it; splitting it into "extraction agent"
+ "rule agent" + "coordinator agent" would add orchestration overhead
without adding capability.

**Why RAG/Qdrant and MCP are not in v1:**
Nothing in the MVP's use case requires retrieving prior project context —
every check today is derivable from the current protocol text plus the
current `deliverables.csv` row. RAG becomes worth it the moment a protocol
references history ("EL-04 is delayed *again*") that isn't in the current
message. MCP becomes worth it when something *other than this one FastAPI
service* (a different AI assistant, a different tool) needs to call
`get_deliverable()` etc. Neither condition is true yet, so neither is here.

---

## 9. What was deliberately left out of the MVP

No frontend, no login/auth, no real database, no multi-agent setup, no
knowledge graph, no SharePoint integration, no large synthetic dataset, no
LangGraph, no MCP, no RAG. Every one of these is a legitimate next step
(see below) but none is required to prove the core idea end-to-end, and
adding any of them now would be scope creep relative to the stated goal:
hands-on practice with n8n, webhooks, REST, FastAPI, Pydantic, structured
LLM output, and deterministic business rules.

## 10. Optional extensions (only after the MVP works end-to-end)

1. **RAG / Qdrant** — index a handful of past protocols/decisions; if a new
   protocol references something like "EL-04 is delayed again," retrieve
   the relevant prior context before/alongside extraction. Only worth
   adding once a test case actually needs history the current message
   doesn't contain.
2. **LangGraph** — once the flow needs a loop: extract → is information
   sufficient? → if no, retrieve context → reassess → if still uncertain,
   flag for human review. Not needed for the current linear pipeline.
3. **MCP** — expose `get_deliverable()`, `get_open_actions()`,
   `get_project_issues()` as MCP tools so any MCP-aware assistant (not just
   this FastAPI service) can query project state. Worth doing once there's
   a second consumer of that data.

No A2A, no multi-agent architecture, unless a genuine second specialist
role shows up that can't be handled by one extraction call plus rules.

---

## 11. Two-minute pitch

> I wanted to understand the kind of practical AI automation used in EPCM,
> so I built a small adjacent use case rather than copying an existing
> prototype. My workflow analyses project meeting protocols and extracts
> decisions, actions, owners, deadlines and affected deliverables. A meeting
> protocol enters through an n8n webhook, n8n calls a Python FastAPI service
> through REST, the LLM performs structured semantic extraction using
> Pydantic, deterministic Python rules identify things like missing owners
> or unresolved dependencies, and n8n handles the downstream warning
> workflow. I also created a small evaluation dataset to test the
> structured extraction and issue detection.
