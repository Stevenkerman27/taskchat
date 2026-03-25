# Development Progress: 2026.3.20

## 决策意图
- **架构演进至 CLI Wrapper (GUI 包装器模式):** 严格执行 `GEMINI.md` 规范。新增了真正的 CLI 模块 `chat_cli_v2.py`。
- **解耦 GUI 与核心逻辑:** `ChatGUIV2` 不再直接 `import ChatLogicV2` 并持有其实例，而是通过 `subprocess.Popen` 以子进程的形式运行 `chat_cli_v2.py`。
- **通信协议设计:** CLI 设计了支持人类可读 (`stdout`) 和机器可读 (`--json`) 双模式。GUI 通过 `--json` 启动 CLI 子进程，它们之间通过 `stdin` 与 `stdout` 交换严格格式化的 JSON 对象。GUI 负责发送如 `{"cmd": "chat", "args": {"msg": "hello"}}` 的命令，而 CLI 返回 `{type: "...", content: ...}` 状态反馈，从而实现松耦合的交互和双向数据流。
- **扩展性提升:** 此时的核心引擎完全可以脱离界面以纯后台模式运行（甚至在 CI/CD 中进行自动化），也可以直接用于终端交互。由于分离了进程，网络堵塞/模型异常崩溃将不再导致界面卡死或崩溃。

## 验证依据
- CLI 核心 (`chat_cli_v2.py`) 可以被直接调用并在交互控制台内工作。
- GUI (`chat_gui_v2.py`) 正确启用了 JSON IPC 并能完美复现之前的界面功能。
- 子进程日志捕获、多线程管道监听逻辑被证实可以在 Tkinter 中无缝更新 UI 而不产生阻塞（由于 `root.after()` 的正确使用）。
