# `shared/` Folder

Both the controller and the sandbox load files from `shared/`, so it acts like the common source of truth for tool names and tool descriptions.

## Files

### `shared/__init__.py`
- Marks `shared` as a Python package.
- Its docstring explains that the folder contains shared tool catalog helpers.
- This lets other code import from `shared` cleanly.

### `shared/tool_catalog.py`
- Loads the tool catalog from `shared/tools.yaml`.
- Converts the YAML into Python data that the app can use.
- Also provides `allowed_tool_names()` so the sandbox can enforce the allow-list.
- This file is important because both services need to agree on the same tool set.

### `shared/tools.yaml`
- Stores the list of allowed tools and their descriptions.
- This is the main file that defines what tools exist.
- The controller uses it to tell the LLM what tools are available.
- The sandbox uses it to decide which tools are allowed to run.
