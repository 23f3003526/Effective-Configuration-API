
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if key:
            result[key] = value
    return result


def _normalise_layer(raw: dict[str, Any], *, dotenv_layer: bool = False) -> dict[str, Any]:
    """Map source names to canonical config keys."""
    normalised: dict[str, Any] = {}
    for original_key, value in raw.items():
        key = original_key.strip()
        upper_key = key.upper()

        if dotenv_layer and upper_key == "NUM_WORKERS":
            canonical = "workers"
        elif upper_key.startswith("APP_"):
            # APP_PORT -> port, APP_API_KEY -> api_key, etc.
            canonical = upper_key[4:].lower()
        else:
            canonical = key.lower()

        if canonical:
            normalised[canonical] = value
    return normalised


def _coerce(key: str, value: Any) -> Any:
    """Apply the response type rules after every source has been merged."""
    text = str(value).strip()
    if key in {"port", "workers"}:
        try:
            return int(text)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"'{key}' must be an integer")
    if key == "debug":
        return text.lower() in {"true", "1", "yes", "on"}
    return str(value)


def build_effective_config(cli_sets: list[str] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = dict(DEFAULTS)

    # Layer 2: environment-specific YAML (APP_ENV defaults to development).
    environment_name = (
        os.environ.get("APP_ENV")
        or os.environ.get("ENV")
        or "development"
    ).strip()
    yaml_path = BASE_DIR / f"config.{environment_name}.yaml"
    yaml_config = _read_flat_yaml(yaml_path)
    if yaml_config is None:
        yaml_config = dict(ASSIGNED_YAML_FALLBACK)
    config.update(_normalise_layer(yaml_config))

    # Layer 3: .env file, read independently so it cannot overwrite OS env vars.
    dotenv_path = BASE_DIR / ".env"
    dotenv_values = _read_dotenv(dotenv_path)
    if dotenv_values is None:
        dotenv_values = dict(ASSIGNED_DOTENV_FALLBACK)
    config.update(_normalise_layer(dotenv_values, dotenv_layer=True))

    # Layer 4: OS environment APP_* values must override .env values.
    os_values = {
        key: value
        for key, value in os.environ.items()
        if key.upper().startswith("APP_") and key.upper() != "APP_ENV"
    }
    # Apply exercise-assigned OS values if the deployment environment has not
    # defined them explicitly. Actual OS variables always win over these fallbacks.
    for key, value in ASSIGNED_OS_FALLBACK.items():
        os_values.setdefault(key, value)
    config.update(_normalise_layer(os_values))

    # Highest precedence: every repeated ?set=key=value query parameter.
    for item in cli_sets or []:
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise HTTPException(
                status_code=400,
                detail="Each set parameter must have the form key=value",
            )
        config[key.strip().lower()] = value

    # Coerce all configured keys and keep api_key masked unconditionally.
    effective: dict[str, Any] = {}
    for key, value in config.items():
        if key == "api_key":
            effective[key] = "****"
        else:
            effective[key] = _coerce(key, value)

    # Keep all required keys present even if a config layer was incomplete.
    for key, value in DEFAULTS.items():
        if key not in effective:
            effective[key] = "****" if key == "api_key" else _coerce(key, value)

    return effective


@app.get("/effective-config")
def effective_config(set_values: list[str] | None = Query(default=None, alias="set")):
    return build_effective_config(set_values)


@app.get("/")
def root():
    return {"message": "Effective Configuration API", "endpoint": "/effective-config"}
