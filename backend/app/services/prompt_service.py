from dataclasses import dataclass
from pathlib import Path
import logging
import yaml
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class RenderedPrompt:
    system: str
    user: str


class PromptService:
    def __init__(self, prompts_dir: str):
        self._dir = Path(prompts_dir)
        self._validate_defaults()

    def _validate_defaults(self) -> None:
        """Warn at startup if any task directory is missing a default.yaml."""
        if not self._dir.exists():
            logger.warning("Prompts directory not found: %s", self._dir)
            return
        for task_dir in self._dir.iterdir():
            if task_dir.is_dir() and not (task_dir / "default.yaml").exists():
                logger.warning("No default.yaml found for task '%s'", task_dir.name)

    def list_prompts(self, task_type: str) -> list[str]:
        """Return sorted prompt names available for a task type."""
        task_dir = self._dir / task_type
        if not task_dir.exists():
            raise FileNotFoundError(f"Unknown task type: '{task_type}'")
        return sorted(f.stem for f in task_dir.glob("*.yaml"))

    def get_raw(self, task_type: str, name: str) -> dict:
        """Return raw YAML content with name injected. Used by the API for display."""
        path = self._dir / task_type / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt '{name}' not found for task '{task_type}'")
        data = yaml.safe_load(path.read_text())
        data["name"] = name
        return data

    def render(self, task_type: str, name: str, **variables) -> RenderedPrompt:
        """Render system and user prompts with variables substituted."""
        raw = self.get_raw(task_type, name)
        if "system" not in raw or "user" not in raw:
            raise ValueError(
                f"Prompt '{name}' for task '{task_type}' must have 'system' and 'user' keys"
            )
        template = ChatPromptTemplate.from_messages([
            ("system", raw["system"]),
            ("human", raw["user"]),
        ])

        # If the YAML declares `variables:`, validate it matches the template exactly.
        declared = raw.get("variables")
        if declared is not None:
            declared_set = set(declared)
            actual_set = set(template.input_variables)
            if declared_set != actual_set:
                undeclared = sorted(actual_set - declared_set)
                stale = sorted(declared_set - actual_set)
                parts = []
                if undeclared:
                    parts.append(f"used in template but not declared: {undeclared}")
                if stale:
                    parts.append(f"declared but not used in template: {stale}")
                raise ValueError(
                    f"Prompt '{name}' for task '{task_type}': variable mismatch — {'; '.join(parts)}"
                )

        # Validate all template variables are provided by the caller.
        missing = sorted(set(template.input_variables) - set(variables))
        if missing:
            raise ValueError(
                f"Missing template variable(s) {missing} for prompt '{name}' in task '{task_type}'"
            )

        messages = template.invoke(variables).to_messages()
        return RenderedPrompt(
            system=messages[0].content,
            user=messages[1].content,
        )


# Module-level singleton — instantiated at import time using settings.
# Tests override this via FastAPI dependency_overrides[get_prompt_service].
from app.core.config import settings as _settings  # noqa: E402

_prompt_service = PromptService(_settings.prompts_dir)


def get_prompt_service() -> PromptService:
    return _prompt_service
