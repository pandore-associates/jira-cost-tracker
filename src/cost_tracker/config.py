from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource, InitSettingsSource


class _NoJsonForProjects:
    """Mixin: return jira_projects as a raw string so the field_validator can parse it."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name == "jira_projects" and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)  # type: ignore[misc]


class _EnvSource(_NoJsonForProjects, EnvSettingsSource):
    pass


class _DotEnvSource(_NoJsonForProjects, DotEnvSettingsSource):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_projects: list[str]
    db_path: str = "./cost_tracker.db"
    export_dir: str = "./exports"
    api_port: int = 8765
    plan_man_days: float = 107.0
    plan_budget_eur: float = 137470.0
    plan_contingency: float = 0.30

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: InitSettingsSource,
        env_settings: EnvSettingsSource,  # noqa: ARG002
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        return (
            init_settings,
            _EnvSource(settings_cls),
            _DotEnvSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("jira_projects", mode="before")
    @classmethod
    def parse_projects(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return list(v) if v else []
