import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS: dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

app = FastAPI(title="Effective Configuration API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


def coerce(key: str, value: Any) -> Any:
    text = str(value)
    normalized = key.lower()
    if normalized in {"port", "workers"}:
        return int(text)
    if normalized == "debug":
        return text.strip().lower() in {"true", "1", "yes", "on"}
    return text


def apply_layer(config: dict[str, Any], layer: dict[str, Any], *, env_layer: bool = False) -> None:
    for raw_key, value in layer.items():
        if value is None:
            continue
        key = str(raw_key).strip().lower()
        if env_layer:
            if key == "app_port":
                key = "port"
            elif key in {"app_workers", "num_workers"}:
                key = "workers"
            elif key == "app_debug":
                key = "debug"
            elif key == "app_log_level":
                key = "log_level"
            elif key == "app_api_key":
                key = "api_key"
            else:
                continue
        if key.startswith("app_"):
            key = key[4:]
        config[key] = coerce(key, value)


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])) -> dict[str, Any]:
    config = dict(DEFAULTS)

    # Layer 2: environment-specific YAML configuration.
    environment = os.environ.get("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as handle:
            yaml_layer = yaml.safe_load(handle) or {}
        if isinstance(yaml_layer, dict):
            apply_layer(config, yaml_layer)

    # Layer 3: .env values. NUM_WORKERS is an explicit alias for workers.
    dotenv_layer = dotenv_values(BASE_DIR / ".env")
    apply_layer(config, dict(dotenv_layer), env_layer=True)

    # Layer 4: real OS environment variables with APP_ prefix.
    os_layer = {key: value for key, value in os.environ.items() if key.startswith("APP_")}
    apply_layer(config, os_layer, env_layer=True)

    # Highest precedence: repeatable CLI-style query overrides.
    for assignment in set:
        if "=" not in assignment:
            continue
        key, value = assignment.split("=", 1)
        key = key.strip().lower()
        if not key:
            continue
        config[key] = coerce(key, value)

    # Never reveal the underlying secret, including for CLI overrides.
    config["api_key"] = "****"
    return config
