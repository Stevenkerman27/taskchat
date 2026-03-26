# `run_shell_command` Tool Design Spec

## Overview
Implement the `run_shell_command` tool in the agent program, referencing the provided `good_egs/shell.md`. This tool allows the agent to execute shell commands within the current workspace environment. As discussed and approved by the user, we are implementing "Option A": basic command execution with background process support, omitting interactive pseudo-terminal (PTY) capabilities for simplicity and stability on Windows.

## Architecture

The tool will be implemented as a Python function in `tools/tools_impl.py` and registered via the `ToolRegistry`. Its configuration and JSON schema will be added to `tools/tools.yaml`.

### 1. Tool Parameters (JSON Schema)
- `command` (string, required): The exact shell command to execute.
- `description` (string, optional): A brief description shown to the user for confirmation.
- `dir_path` (string, optional): The path (absolute or relative to current dir) where the command runs. Defaults to current directory (`.`).
- `is_background` (boolean, optional): Whether to run the process in the background. Defaults to `false`.

### 2. Execution Logic (`tools_impl.py`)
- **Platform Base**: Windows (win32).
- **Command Wrapper**: Commands will be executed using `powershell.exe -NoProfile -Command "{command}"`. This aligns with Gemini standard guidelines for Windows and allows robust handling of basic pipes/chains.
- **Directory Resolution**: Safely resolve `dir_path` against the current working directory (`os.path.abspath('. ')`). Ensure the target directory exists before running.
- **Foreground Execution (`is_background=False`)**:
  - Use `subprocess.run()`.
  - Arguments: `capture_output=True, text=True, timeout=120, cwd=resolved_dir_path, encoding='utf-8', errors='replace'`.
  - Capture `stdout`, `stderr`, and `returncode`.
- **Background Execution (`is_background=True`)**:
  - Use `subprocess.Popen()`.
  - Arguments: `stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=resolved_dir_path, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`. (On Windows, `CREATE_NEW_PROCESS_GROUP` is needed for detaching).
  - Do not `wait()`. Immediately return the process PID.

### 3. Return Structure (JSON String)
```json
{
  "Command": "string",
  "Directory": "string",
  "Stdout": "string (truncated if too long, or empty for background)",
  "Stderr": "string (truncated if too long, or empty for background)",
  "Exit Code": 0, // Omitted for background
  "Background PIDs": [1234] // Omitted for foreground
}
```

### 4. Constraints & Defense Lines
- **Output Truncation**: To prevent exceeding token limits, `stdout` and `stderr` will be truncated if they exceed 10,000 characters. We'll keep the first 2,000 and the last 8,000 characters to show how it started and how it ended.
- **Security Context**: The `GEMINI_CLI=1` environment variable will be injected into `os.environ` for the subprocess, as specified in the reference document.

## Files to Modify
1. `tools/tools_impl.py`: Add `run_shell_command` function and register it.
2. `tools/tools.yaml`: Add tool definition to the schema and include it in the `basic` tool group.

## Self-Review Checklist
- [x] Does it handle both foreground and background tasks?
- [x] Does it prevent hanging on long-running tasks? (Yes, `timeout=120`).
- [x] Is token flooding prevented? (Yes, via truncation).
- [x] Are the parameters exact matches to the specification? (Yes).
