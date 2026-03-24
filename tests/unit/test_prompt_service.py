import pytest
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))


def make_yaml(tmp_path, task: str, name: str, system: str, user: str) -> None:
    task_dir = tmp_path / task
    task_dir.mkdir(exist_ok=True)
    (task_dir / f"{name}.yaml").write_text(f"system: |\n  {system}\nuser: |\n  {user}\n")


def test_list_prompts(tmp_path):
    from app.services.prompt_service import PromptService
    make_yaml(tmp_path, "rag", "default", "sys", "usr")
    make_yaml(tmp_path, "rag", "concise", "sys2", "usr2")

    service = PromptService(str(tmp_path))
    result = service.list_prompts("rag")

    assert result == ["concise", "default"]


def test_list_prompts_unknown_task_raises(tmp_path):
    from app.services.prompt_service import PromptService
    service = PromptService(str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Unknown task type"):
        service.list_prompts("nonexistent")


def test_get_raw_returns_content_with_name(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text("system: You are helpful\nuser: Answer {question}\n")

    service = PromptService(str(tmp_path))
    result = service.get_raw("rag", "default")

    assert result["system"] == "You are helpful"
    assert "question" in result["user"]
    assert result["name"] == "default"


def test_get_raw_not_found_raises(tmp_path):
    from app.services.prompt_service import PromptService
    (tmp_path / "rag").mkdir()

    service = PromptService(str(tmp_path))

    with pytest.raises(FileNotFoundError, match="not found"):
        service.get_raw("rag", "nonexistent")


def test_render_substitutes_variables(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text(
        "system: You are {role}\nuser: Answer {question}\n"
    )

    service = PromptService(str(tmp_path))
    result = service.render("rag", "default", role="a helper", question="What is AI?")

    assert result.system == "You are a helper"
    assert result.user == "Answer What is AI?"


def test_render_missing_variable_raises(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text(
        "system: You are a helper\nuser: Answer {question} using {context}\n"
    )

    service = PromptService(str(tmp_path))

    with pytest.raises(ValueError, match="Missing template variable"):
        service.render("rag", "default", question="What is AI?")  # context missing


def test_render_missing_yaml_keys_raises(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text("system: You are helpful\n")  # no user key

    service = PromptService(str(tmp_path))

    with pytest.raises(ValueError, match="must have 'system' and 'user' keys"):
        service.render("rag", "default")


def test_validate_defaults_warns_on_missing_default(tmp_path, caplog):
    from app.services.prompt_service import PromptService
    import logging
    (tmp_path / "rag").mkdir()  # no default.yaml inside

    with caplog.at_level(logging.WARNING):
        PromptService(str(tmp_path))

    assert "No default.yaml" in caplog.text
