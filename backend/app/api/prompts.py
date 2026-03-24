from fastapi import APIRouter, HTTPException, Depends
from app.services.prompt_service import PromptService, get_prompt_service

router = APIRouter()


@router.get("/prompts/{task_type}")
def list_prompts(
    task_type: str,
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """List available prompt names for a task type."""
    try:
        return prompt_service.list_prompts(task_type)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/prompts/{task_type}/{name}")
def get_prompt(
    task_type: str,
    name: str,
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """Get the raw system and user template for a named prompt."""
    try:
        return prompt_service.get_raw(task_type, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
