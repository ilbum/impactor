import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitHubConfig:
    token: str
    repos: list[str]


@dataclass
class DatadogConfig:
    api_key: str
    app_key: str
    dashboards: list[str]


@dataclass
class AnthropicConfig:
    api_key: str
    model: str = "claude-opus-4-7"


@dataclass
class OutputConfig:
    path: str = "./reports"


@dataclass
class Config:
    github: GitHubConfig
    datadog: DatadogConfig
    anthropic: AnthropicConfig
    service_map: dict[str, str]
    output: OutputConfig


def load(path: str = "harness.config.toml") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        print(f"Config file not found: {path}", file=sys.stderr)
        print("Copy harness.config.toml.example to harness.config.toml and fill in your keys.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    return Config(
        github=GitHubConfig(
            token=raw["github"]["token"],
            repos=raw["github"]["repos"],
        ),
        datadog=DatadogConfig(
            api_key=raw["datadog"]["api_key"],
            app_key=raw["datadog"]["app_key"],
            dashboards=raw["datadog"].get("dashboards", []),
        ),
        anthropic=AnthropicConfig(
            api_key=raw["anthropic"]["api_key"],
            model=raw["anthropic"].get("model", "claude-opus-4-7"),
        ),
        service_map=raw.get("service_map", {}),
        output=OutputConfig(
            path=raw.get("output", {}).get("path", "./reports"),
        ),
    )
