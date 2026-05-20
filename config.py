import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from providers.base import Provider


@dataclass
class LLMConfig:
    model: str
    api_key: str | None = None
    api_base: str | None = None


@dataclass
class OutputConfig:
    path: str = "./reports"


@dataclass
class Config:
    providers: dict[str, dict]
    llm: LLMConfig | None
    service_map: dict[str, str]
    output: OutputConfig


_PROVIDER_REGISTRY: dict[str, str] = {
    "github":    "providers.github.GitHubProvider",
    "git":       "providers.git.GitProvider",
    "datadog":   "providers.datadog.DatadogProvider",
    "linear":    "providers.linear.LinearProvider",
    "pagerduty": "providers.pagerduty.PagerDutyProvider",
    "sentry":    "providers.sentry.SentryProvider",
}

_CODE_PROVIDERS = {"github", "git"}


def load(path: str = "harness.config.toml") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        print(f"Config file not found: {path}", file=sys.stderr)
        print("Copy harness.config.toml.example to harness.config.toml and fill in your keys.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    if "providers" not in raw or not (_CODE_PROVIDERS & set(raw["providers"])):
        print("Error: config must include [providers.github] or [providers.git].", file=sys.stderr)
        sys.exit(1)

    llm_raw = raw.get("llm")
    llm = LLMConfig(
        model=llm_raw["model"],
        api_key=llm_raw.get("api_key"),
        api_base=llm_raw.get("api_base"),
    ) if llm_raw else None

    return Config(
        providers=raw.get("providers", {}),
        llm=llm,
        service_map=raw.get("service_map", {}),
        output=OutputConfig(path=raw.get("output", {}).get("path", "./reports")),
    )


def load_providers(cfg: Config) -> list[Provider]:
    import importlib

    providers: list[Provider] = []

    for name, provider_cfg in cfg.providers.items():
        class_path = _PROVIDER_REGISTRY.get(name)
        if class_path is None:
            print(f"Warning: unknown provider '{name}' — skipping.")
            continue

        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        try:
            instance = _instantiate(name, cls, provider_cfg)
            providers.append(instance)
        except TypeError as e:
            print(f"Warning: could not instantiate provider '{name}': {e}")

    return providers


def _instantiate(name: str, cls, cfg: dict):
    if name == "github":
        return cls(token=cfg["token"], repos=cfg["repos"])
    if name == "git":
        paths = cfg.get("paths") or [cfg.get("path", ".")]
        return cls(paths=paths)
    if name == "datadog":
        return cls(api_key=cfg["api_key"], app_key=cfg["app_key"], dashboards=cfg.get("dashboards", []))
    if name == "linear":
        return cls(api_key=cfg["api_key"], team_ids=cfg.get("team_ids", []))
    if name == "pagerduty":
        return cls(api_key=cfg["api_key"])
    if name == "sentry":
        return cls(auth_token=cfg["auth_token"], org_slug=cfg["org_slug"])
    raise ValueError(f"No instantiation logic for provider '{name}'")
