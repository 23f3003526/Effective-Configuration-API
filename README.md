# Effective Configuration API

FastAPI service for merging configuration layers in this order: hardcoded defaults, `config.<APP_ENV>.yaml`, `.env`, OS `APP_*` variables, and repeatable `set=key=value` query overrides.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Try:

```text
http://127.0.0.1:8000/effective-config?set=port=9000&set=debug=true
```

`api_key` is always returned as `****`. CORS allows browser requests from any origin without credentials.

## Render

Push the files to GitHub and create a Render Web Service. Build command: `pip install -r requirements.txt`; start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
