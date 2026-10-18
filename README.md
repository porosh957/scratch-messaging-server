# Scratch Messaging Server (starter)

A small Python/Flask API starter for experimenting with the custom 8-bit letter encoding.

## Current scope

- `GET /` — service information
- `GET /health` — health check
- `POST /api/encode` — encode English A–Z and a–z into 8-bit values
- `POST /api/decode` — decode those bytes back into letters

**This is a demo, not an account or messaging service yet.** It has no database, user accounts, authentication, ID registry, or message persistence.

## Encoding rule used by this demo

- The first seven bits represent the letter index (`A`/`a` = 0 through `Z`/`z` = 25).
- The last bit is the case flag: `0` uppercase, `1` lowercase.
- In the byte, this is equivalent to `2 * index + case_flag`.

Examples:
- `A` = `00000000`
- `B` = `00000010`
- `a` = `00000001`
- `b` = `00000011`

## Run locally

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

The server starts on `http://localhost:10000`.

Example encode request:

```bash
curl -X POST http://localhost:10000/api/encode ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"Hello\"}"
```

Example decode request:

```bash
curl -X POST http://localhost:10000/api/decode ^
  -H "Content-Type: application/json" ^
  -d "{\"binary\":\"00010001001011000010011000101110\"}"
```

## Deploy to Render

1. Create a new GitHub repository and upload these files to its root.
2. In Render, choose **New → Web Service** and connect that repository.
3. Render can detect `render.yaml`; otherwise set:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Deploy. Open the service URL and check `/health`.

## Scratch integration note

Normal Scratch blocks do not provide arbitrary HTTP API requests. Scratch cloud variables also cannot directly act as a general HTTP client. This API can be tested from a browser or other client now; a Scratch-compatible bridge or a supported extension/custom client will be needed before a Scratch project can call it directly.

Do not add passwords or real personal information to this demo. Before building accounts or real messaging, add persistent storage, authentication, rate limiting, and appropriate access controls.
