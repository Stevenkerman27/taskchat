# Progress Report - 2026-03-27

## Task 20: Record allowed tools in context for debugging

### Decision Intent
- **Goal**: Record the list of enabled tools in the session JSON file whenever a user sends a message to facilitate debugging tool-calling issues.
- **Implementation**: Modified `ChatLogicV2.add_message` to automatically inject `enabled_tools` into the `metadata` of `user` messages.
- **Security & Integrity**: Explicitly filtered out `enabled_tools` in `ChatLogicV2.get_full_payload` to ensure this internal debug information is never leaked to the LLM API, preventing potential 400 errors or context pollution.

### Defensive Measures
- Used `msg.metadata.copy()` in `get_full_payload` before deletion to avoid side effects on the primary message objects in memory.
- Added checks in `add_message` to avoid redundant recording if `enabled_tools` is already provided in `kwargs`.

### Verification Basis
- Created `test/test_task20.py` to verify:
    1. `enabled_tools` is correctly added to user message metadata in memory.
    2. `enabled_tools` is correctly persisted to the session JSON file on disk.
    3. `enabled_tools` is NOT present in the payload generated for API calls.
- Verified in `myml` environment to ensure all provider strategies were correctly registered and tested.
