"""Load plaintext prompt templates from prompt_templates/."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompt_templates"


def load_prompt_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")
