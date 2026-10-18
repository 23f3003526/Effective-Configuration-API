import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Query
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
    """Convert known keys to their required types; keep all others as strings."""
    normalized_key = key.strip().lower()
    text = str(value)

    if normalized_key in {"port", "workers"}:
        try:
            return int(text)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"{normalized_key} must be an integer",
            ) from exc

    if normalized_key == "debug":
        return text.strip().lower() in {"true", "1", "yes", "on"}

    return text


def apply_config_layer(
    config: dict[str, Any],
    layer: dict[str, Any],
    *,
    environment_layer: bool = False,
) -> None:
    """Apply one layer in-place. Later layers have higher precedence."""
    for raw_key, value in layer.items():
        if value is None:
            continue

        key = str(raw_key).strip().lower()
        if not key:
            continue

        if environment_layer:
            # Explicit alias required by the task.
            if key == "num_workers":
                key = "workers"
            elif key.startswith("app_"):
                # APP_ENV selects the YAML file; it is not a config output key.
                key = key[4:]
                if key == "env":
                    continue
            else:
                # Environment layers accept APP_* names, plus NUM_WORKERS.
                continue

        config[key] = coerce(key, value)


def load_effective_config(cli_overrides: list[str]) -> dict[str, Any]:
    config = dict(DEFAULTS)

    # 1. Defaults are already present.

    # 2. Environment-specific YAML.
    environment = os.environ.get("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{environment}.yaml"
    if yaml_path.exists():
        try:
            with yaml_path.open("r", encoding="utf-8") as handle:
                yaml_layer = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=500, detail="Invalid YAML configuration") from exc

        if isinstance(yaml_layer, dict):
            apply_config_layer(config, yaml_layer)

    # 3. .env file. Read values without mutating/overwriting the process environment.
    dotenv_layer = dotenv_values(BASE_DIR / ".env")
    apply_config_layer(config, dict(dotenv_layer), environment_layer=True)

    # 4. Actual OS-level APP_* variables override .env values.
    os_layer = {
        key: value
        for key, value in os.environ.items()
        if key.startswith("APP_") and key != "APP_ENV"
    }
    apply_config_layer(config, os_layer, environment_layer=True)

    # 5. CLI-style query overrides have highest precedence.
    for assignment in cli_overrides:
        key, separator, value = assignment.partition("=")
        key = key.strip().lower()
        if not separator or not key:
            continue
        config[key] = coerce(key, value)

    # Do not leak the underlying secret, even if it was overridden from the CLI.
    config["api_key"] = "****"
    return config


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])) -> dict[str, Any]:
    return load_effective_config(set)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "endpoint": "/effective-config"}
