# Runbook - how to run everything

Quick reference for starting the project day-to-day. See README.md for the
full architecture/explanation; this file is just the commands.

---

## 1. Start FastAPI

```bash
cd epcm-decision-tracker
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
npx --cache "$HOME/.cache/n8n-npm-cache" n8n@2.37.10
```

- `nvm use 24` - n8n's `isolated-vm` dependency requires Node >=24; this
  session-only switch doesn't touch your default Node 20 anywhere else.
- `N8N_SECURE_COOKIE=false` - avoids a Safari-specific cookie error on plain
  `http://localhost`.
- `--cache "$HOME/.cache/n8n-npm-cache"` - routes around a broken permission
  on your default global npm cache (root-owned files from a past
  `sudo npm`). To fix that properly instead:
  `sudo chown -R $(id -u):$(id -g) "$HOME/.npm"`, then you can drop the
  `--cache` flag entirely.
- `n8n@2.37.10` - pinning the version, instead of just `n8n`, is what stops
  it reinstalling on every run. Unpinned `npx n8n` re-asks npm's registry
  "what's latest?" each time, and since n8n ships new releases often,
  "latest" keeps changing and npx treats each change as a brand-new package
  to install - regardless of caching. `2.37.10` is the version already
  confirmed working end-to-end here (Node 24, Discord notification node
  included). Bump it deliberately later if you want a newer n8n, rather
  than by accident.

If you ever see `Need to install the following packages: n8n@X.Y.Z` on a
run where you expected it to just start, one of two things happened: you're
running the unpinned `npx n8n` (missing the `@2.37.10`), or the cache
directory got cleared (this is exactly why `~/.cache/` is used instead of
`/tmp` - macOS periodically clears `/tmp`, which was the original cause of
this repeating).

Wait for the line `Editor is now accessible via: http://localhost:5678`,
then open that URL in your browser (first time: create a local owner
account, stored only on your machine).

Import the workflow once: **Workflows -> Import from File ->
`n8n/EPCM Decision & Interface Action Tracker.json`** (your local copy,
with the real Discord webhook URL already in it).

> Only if you instead import the sanitized `n8n/epcm_workflow.json` template
> from GitHub - that one has no real webhook baked in on purpose, it
> references `{{ $env.DISCORD_WEBHOOK_URL }}` - add this line **before**
> `npx` above: `export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"`.
> Never put a real webhook URL into a file that gets committed - if that
> ever happens by accident, revoke the webhook in Discord immediately;
> removing it from git afterward does not undo the exposure.

### Test webhook vs production webhook
- **Test URL** (`/webhook-test/...`): only active for **one call** after you
  click **Execute Workflow** in the editor. Used while building/debugging.
- **Production URL** (`/webhook/...`): always listening, no click needed -
  only works once the workflow's **Active** toggle (top right) is switched on.

---

## 3. Example curl commands

**Two different ports do two different things - easy to mix up:**

| Port | Hits | Result |
|---|---|---|
| **8000** | FastAPI directly | Returns JSON. n8n is never involved, canvas never lights up. |
| **5678** | n8n's webhook | Triggers the full workflow - this is what makes nodes turn green in the browser. |

If you want to *see the n8n workflow run*, you must curl **port 5678**, not
8000. Curling 8000 will still "work" (you'll get a valid JSON response) but
it silently skips n8n entirely - that's the most common mix-up.

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

**B) Call through the n8n webhook** (the one that actually runs the
workflow: n8n -> FastAPI -> LLM -> rules -> IF -> Discord). Two steps, in
this exact order:
1. In the n8n browser tab, click **Execute Workflow** (arms the test
   webhook for exactly one call).
2. **Immediately** switch to your terminal and run:

```bash
curl -X POST http://localhost:5678/webhook-test/epcm-protocol \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ALPHA",
    "text": "Julia Wenzel was assigned to revise the fire safety concept by 2026-08-20. The revised concept is still outstanding."
  }'
```

If you wait too long, or already used that one-shot call, you'll get back
`{"code":404,"message":"The requested webhook \"epcm-protocol\" is not
registered."}` - just click **Execute Workflow** again and re-curl.

**Another example** (same click-then-curl sequence) - this one triggers
three issue types at once (missing owner, missing deadline, unresolved
dependency) instead of just the one deadline issue above, so it's a good
contrast case for showing off multiple flags landing in Discord together:

```bash
curl -X POST http://localhost:5678/webhook-test/epcm-protocol \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "PROJECT_ALPHA",
    "text": "It was decided to reroute the plumbing risers on level 3 because the structural beam position changed in the latest steel drawings. Maria Novak will update the structural drawings, but the plumbing riser diagram (PL-03) cannot be finalized until the new beam position is confirmed. No deadline has been agreed yet for this confirmation."
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
cd epcm-decision-tracker
source .venv/bin/activate
python eval/run_eval.py              # summary: per-field accuracy + precision/recall
python eval/run_eval.py --verbose    # + input text, expected values, full actual response per case
```

---

## 5. Stop / kill a stuck process

If a terminal tab running `uvicorn` or `n8n` got closed without Ctrl+C, or
you get an "address already in use" error trying to start one again, the old
process is still running in the background and holding the port.

**Find what's using a port:**
```bash
lsof -i :8000    # FastAPI
lsof -i :5678    # n8n
```
The `PID` column in the output is the process id you need below.

**Kill by port** (find + kill in one step):
```bash
kill -9 $(lsof -t -i :8000)    # stop FastAPI
kill -9 $(lsof -t -i :5678)    # stop n8n
```

**Kill by process name** (if you don't know/care about the port):
```bash
pkill -f "uvicorn app.main:app"   # stop FastAPI
pkill -f "npm exec n8n"           # stop n8n (this is what `npx n8n` actually runs as)
```

**Check it's actually gone before restarting:**
```bash
lsof -i :8000 2>/dev/null | grep LISTEN || echo "port 8000 is free"
lsof -i :5678 2>/dev/null | grep LISTEN || echo "port 5678 is free"
```

If a normal `kill` (or Ctrl+C) doesn't stop it, `kill -9` (used above) forces
it — safe for these two dev processes, no data/state to lose.

---

## 6. If you move/rename the project folder

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
