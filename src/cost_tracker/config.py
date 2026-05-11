from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class CommaSeparatedEnvSource(EnvSettingsSource):
    """Custom env source that treats jira_projects as simple string, not complex."""

    def __call__(self) -> dict[str, Any]:
        """Override to handle comma-separated projects."""
        from pydantic_settings.exceptions import SettingsError

        data: dict[str, Any] = {}

        for field_name, field in self.settings_cls.model_fields.items():
            try:
                field_value, _, value_is_complex = self._get_resolved_field_value(
                    field, field_name
                )
            except Exception as e:
                raise SettingsError(
                    f'error getting value for field "{field_name}" '
                    f'from source "{self.__class__.__name__}"'
                ) from e

            # Special handling for jira_projects: don't treat as complex
            if field_name == "jira_projects" and isinstance(field_value, str):
                data[field_name] = [
                    p.strip() for p in field_value.split(",") if p.strip()
                ]
                continue

            try:
                field_value = self.prepare_field_value(
                    field_name, field, field_value, value_is_complex
                )
            except ValueError as e:
                raise SettingsError(
                    f'error parsing value for field "{field_name}" '
                    f'from source "{self.__class__.__name__}"'
                ) from e

            if field_value is not None:
                data[field_name] = field_value

        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_projects: list[str]
    db_path: str = "./cost_tracker.db"
    export_dir: str = "./exports"

    @classmethod
    def _settings_build_values(
        cls, sources: tuple[Any, ...], init_kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Override to replace EnvSettingsSource with our custom one."""
        # Replace EnvSettingsSource with CommaSeparatedEnvSource
        custom_sources = []
        for source in sources:
            if (
                isinstance(source, EnvSettingsSource)
                and type(source) is EnvSettingsSource
            ):
                custom_sources.append(CommaSeparatedEnvSource(cls))
            else:
                custom_sources.append(source)

        # Call parent implementation with modified sources
        return super()._settings_build_values(tuple(custom_sources), init_kwargs)

    @field_validator("jira_projects", mode="before")
    @classmethod
    def parse_projects(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return v
        # Fallback: return empty list if not a string or list
        return []
