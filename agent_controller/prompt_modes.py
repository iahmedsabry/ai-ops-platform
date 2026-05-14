"""Focus modes loaded from prompt_modes/*.txt next to the package root on disk."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_PROMPT_STEM_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_PROMPT_MODES_DIR = Path(__file__).resolve().parent / "prompt_modes"


def _load_prompt_mode_files() -> dict[str, str]:
    out: dict[str, str] = {}
    base = _PROMPT_MODES_DIR
    if not base.is_dir():
        return out
    for path in sorted(base.glob("*.txt")):
        stem = path.stem.lower()
        if not _PROMPT_STEM_PATTERN.match(stem):
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            out[stem] = text
    return out


PROMPT_MODE_FILES = _load_prompt_mode_files()
ALLOWED_PROMPT_MODES = frozenset(set(PROMPT_MODE_FILES.keys()) | {"general"})


def normalize_prompt_mode(mode: Optional[str]) -> str:
    if mode is None:
        return "general"
    cleaned = str(mode).strip().lower()
    if cleaned in ALLOWED_PROMPT_MODES:
        return cleaned
    return "general"


def focus_instruction_block(mode: str) -> str:
    if mode == "general":
        return ""
    return PROMPT_MODE_FILES.get(mode, "")
