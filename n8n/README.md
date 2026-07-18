# n8n workflow

## Import the ready-made workflow
1. Open n8n → **Workflows → Import from File** → select `epcm_workflow.json`.
2. Open the **Call FastAPI /analyse-protocol** node and confirm the URL
   points at your running FastAPI service (default `http://localhost:8000`).
3. Activate the workflow, or just click **Execute Workflow** and use the
   "Listen for test event" URL shown on the Webhook node.

## Or build it by hand (recommended once, for learning)
This is the same workflow, five nodes, built manually:

1. **Webhook** node — HTTP Method `POST`, Path `epcm-protocol`, Response Mode
   `Using Respond to Webhook Node`. This is the entry point: n8n listens on a
   public URL and wakes up the moment someone POSTs a meeting protocol to it.
2. **HTTP Request** node — Method `POST`, URL
   `http://localhost:8000/analyse-protocol`, Body → JSON →
   `{{ JSON.stringify($json.body) }}`. This is n8n acting as a REST *client*
   calling your FastAPI REST *server*.
3. **IF** node — condition `{{ $json.requires_attention }}` is `true`.
   This is the deterministic branch: n8n itself doesn't decide anything, it
   just routes based on the boolean FastAPI already computed.
4. **Code** node (true branch only) — formats the issues into a readable
   warning string and `console.log`s it. Stands in for "send to Teams/email"
   without needing real credentials for the MVP.
5. **Respond to Webhook** node — returns the final JSON (with or without the
   warning) to whoever called the webhook.

## Test it
```bash
curl -X POST http://localhost:5678/webhook-test/epcm-protocol \
  -H "Content-Type: application/json" \
  -d @../data/meeting_protocol_01.txt   # (wrap the text in {"project_id": "...", "text": "..."} first)
```

Or simplest of all while developing: skip n8n entirely and call FastAPI
directly (see the main README) — n8n is the orchestration/notification
layer on top, not where the logic lives.
