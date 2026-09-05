# Runbook - how to run everything

Quick reference for starting the project day-to-day. See README.md for the
full architecture/explanation; this file is just the commands.

---

## 1. Start FastAPI

```bash
cd "/Users/anushkajoshi/Desktop/Fulltime_apply/Drees_Sommer/epcm-decision-tracker"
source .venv/bin/activate
uvicorn app.main:app --reload
```

Open in browser: **http://127.0.0.1:8000/docs** (interactive Swagger UI -
"Try it out" on any endpoint without needing curl).

Health check: `curl http://127.0.0.1:8000/health`

---

## 2. Start n8n

n8n needs Node **24+** (your system default Node is 20 - untouched, unaffected).
Every time you open a new terminal for n8n, run:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use 24
export N8N_SECURE_COOKIE=false
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
npx --cache /tmp/npm-cache-fresh n8n
```

- `nvm use 24` - n8n's `isolated-vm` dependency requires Node >=24; this
  session-only switch doesn't touch your default Node 20 anywhere else.
- `N8N_SECURE_COOKIE=false` - avoids a Safari-specific cookie error on plain
  `http://localhost`.
- `DISCORD_WEBHOOK_URL` - the real Discord webhook URL for the "Notify
  Discord" node at the end of the workflow. Set to your actual webhook URL
  (from Discord: channel settings -> Integrations -> Webhooks). Never commit
  the real value anywhere - the checked-in workflow only references
  `{{ $env.DISCORD_WEBHOOK_URL }}`, never the literal URL. If this ever gets
  hardcoded into an exported JSON and pushed by accident, revoke that
  webhook in Discord immediately and create a new one - removing it from
  git afterward does not undo the exposure.
- `--cache /tmp/npm-cache-fresh` - routes around a broken permission on your
  default global npm cache (root-owned files from a past `sudo npm`). To fix
  that properly instead: `sudo chown -R 501:20 "/Users/anushkajoshi/.npm"`,
  then you can drop the `--cache` flag.

Wait for the line `Editor is now accessible via: http://localhost:5678`,
then open that URL in your browser (first time: create a local owner
account, stored only on your machine).

Import the workflow once: **Workflows -> Import from File ->
`n8n/epcm_workflow.json`**.

### Test webhook vs production webhook
- **Test URL** (`/webhook-test/...`): only active for **one call** after you
  click **Execute Workflow** in the editor. Used while building/debugging.
- **Production URL** (`/webhook/...`): always listening, no click needed -
  only works once the workflow's **Active** toggle (top right) is switched on.

---

## 3. Example curl commands

**A) Call FastAPI directly** (bypasses n8n entirely - useful to isolate
whether a problem is in the extraction/rules logic or in the n8n wiring):

```bash
curl -X POST http://127.0.0.1:8000/analyse-protocol \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ALPHA",
    "text": "During today'\''s coordination meeting, the HVAC layout was changed because of a new ceiling requirement. Electrical must review the cable routing based on the new HVAC layout. Updated drawings are required before 15 September. No responsible person has currently been assigned for the electrical review. Construction Package EL-04 depends on this clarification."
  }'
```

**B) Call through the n8n webhook** (full pipeline: n8n -> FastAPI -> LLM ->
rules -> IF -> warning/notification). Click **Execute Workflow** in n8n
first (test mode, one-shot), then:

```bash
curl -X POST http://localhost:5678/webhook-test/epcm-protocol \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ALPHA",
    "text": "Julia Wenzel was assigned to revise the fire safety concept by 2026-08-20. The revised concept is still outstanding."
  }'
```

Once the workflow is **Active**, swap the URL for the production one and
skip the "Execute Workflow" click:

```bash
curl -X POST http://localhost:5678/webhook/epcm-protocol \
  -H "Content-Type: application/json" \
  -d '{"project_id": "PROJECT_ALPHA", "text": "your protocol text..."}'
```

---

## 4. Run the evaluation suite

FastAPI must be running first (Section 1).

```bash
cd "/Users/anushkajoshi/Desktop/Fulltime_apply/Drees_Sommer/epcm-decision-tracker"
source .venv/bin/activate
python eval/run_eval.py              # summary: per-field accuracy + precision/recall
python eval/run_eval.py --verbose    # + input text, expected values, full actual response per case
```

---

## 5. If you move/rename the project folder

Everything uses **relative paths from the project root** (`data/`, `.env`,
`.venv/`) except:
- The `.venv` itself is tied to the absolute path it was created at. If you
  move the folder, recreate it: `python3 -m venv .venv && source
  .venv/bin/activate && pip install -r requirements.txt`.
- `.env` isn't affected by moving the folder (it's read relative to wherever
  you run `uvicorn`/`python` from - always `cd` into the project root first).
- n8n's `epcm_workflow.json` hardcodes `http://localhost:8000/...` and
  `http://127.0.0.1:8000/...` for the FastAPI calls - these stay correct as
  long as FastAPI still runs on port 8000, regardless of where the project
  folder lives on disk.
