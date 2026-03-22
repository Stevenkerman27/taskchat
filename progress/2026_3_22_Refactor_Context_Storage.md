# 2026-03-22: 重构对话上下文存储机制为JSON持久化

## 决策意图
在此次重构中，改变了原本完全依赖内存 (`self.messages`) 作为唯一活性状态（Active State）的架构，转而采用以 JSON 文件 (`contexts/current_session.json`) 作为“Single Source of Truth”的设计模式。
* **解决核心冲突**：由于 CLI 运行模式及程序可能因异常崩溃等问题，仅存在内存中的实时对话易丢失。采用每次操作前拉取 JSON 状态，操作后刷新 JSON 状态的方式，既保证了状态的持久化，又在多轮（发送、工具调用、接收等）操作期间确保一致性。
* **按需过滤读取**：在持久化文件内储存**所有**底层元数据（包括 `reasoning_content` 及未执行完成的 `tool_calls`）。但在与大模型交互拉取 `payload` 时，显式地去除了 `reasoning_content`。原因是上一轮的思维链如果被拼接进历史上下文中，不仅无谓消耗大量 tokens 且容易在长上下文中扰乱模型的指令遵循。

## 防御性记录
* **文件读写并发风险**：如果多线程读写容易导致 JSON 损坏。解决方案是采用安全的原子写入方式——先使用 `tempfile.mkstemp` 写入临时文件并执行 `os.fsync` 落盘，再用 `os.replace` 原子覆盖目标文件 `current_session.json`。这样即使在此过程中发生崩溃或断电，原有上下文文件也不会被破坏成半拉子状态。
* **对象和字典相互转换陷阱**：在使用 Pydantic 构建的 `InternalMessage` 中，`content` 可能是 `MessagePart` 对象的列表。在序列化为 JSON 时，需要在 `_save_state` 中通过 `part.model_dump()` 将其强转为字典。而在加载时，通过向 `InternalMessage` 传递 `content` 列表，Pydantic 会自动利用其内置校验机制再次反序列化为对象，避免了手动重建嵌套类型的繁琐判断。
* **UI状态同步问题**：之前的实现中工具调用模式（`tool_call_mode`）、未决工具列表（`pending_tool_calls`）等保存在对象内存中。现已将其也归入 JSON 文件中的 `state` 对象。否则重新加载上下文时将会出现消息已更新但工具调用状态却丢失导致死锁的情况。

## 验证依据
* **重构逻辑检查**：涉及加载状态与修改的全部入口（包括但不限于 `chat`, `_handle_tool_calls`, `get_full_payload`, `execute_pending_tools`, `send_tool_results_to_agent`, `cancel_tool_calls` 以及各种 getters）都在前置条件中加入了 `self._load_state()` 并在修改完结后调用 `self._save_state()`。
* **代码编译检查**：通过 `python -m py_compile chat_logic_v2.py` 和帮助命令直接执行的验证。确保了语法及类型调用的正确性，且与 CLI/GUI 所使用的方法保持签名兼容。