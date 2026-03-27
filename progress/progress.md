# 项目架构与开发约束准则 (System Architecture & Development Constraints)

## 1. 全局架构与设计规约 (Global Architecture & Design Conventions)

### 1.1 GUI 包装器模式 (GUI Wrapper Architecture)
*   **核心原则**：GUI 仅作为 CLI 的“输入生成器”与“结果展示器”。严禁将业务逻辑直接耦合在 GUI 事件回调中。
*   **解耦实现**：所有核心功能必须首先实现为独立的 CLI 或底层 API。GUI 通过调用子进程（或 Socket 桥接）与 CLI 交互。
*   **通信协议**：GUI 与 CLI 之间使用严格格式化的 JSON 对象进行异步双向通信。
*   **独立运行**：确保即便没有 GUI，程序依然可以通过终端或脚本自动化运行。

### 1.2 单一职责原则 (SRP) 在 CLI 中的体现
*   **TerminalRenderer**：专职负责 Rich 终端的消息渲染与着色，解耦 UI 展示逻辑。
*   **SocketBridgeServer**：独立处理与外部（如 GUI）的通信，确保网络传输不干扰业务逻辑。
*   **CommandDispatcher**：规范化命令注册与分发（如 `/provider`, `/state`），取代散乱的 `if-elif` 逻辑。
*   **ChatCLI**：作为编排者 (Orchestrator) 协调上述组件，不直接处理底层细节。

### 1.3 DRY (Don't Repeat Yourself) & SSOT (Single Source of Truth)
*   **状态唯一事实来源**：`contexts/session-*.json` 是对话状态的唯一来源。内存中的 `messages` 仅作为实时缓存。
*   **配置集中化**：常量、魔术字符串、API 配置必须定义在统一的配置文件（如 `config.yaml`）中。

---

## 2. 状态管理与核心防线 (State Management & Core Defenses)

### 2.1 对话上下文持久化 (JSON Persistence)
*   **原子写入**：为防止 JSON 损坏，必须采用“写临时文件 + `os.replace`”的原子覆盖方式进行落盘（使用 `os.fsync` 确保数据物理写入）。
*   **数据一致性**：在执行任何逻辑（发送、工具调用）前必须先 `_load_state()`，修改完成后立即 `_save_state()`。

### 2.2 Token 效率与上下文干扰
*   **思维链过滤**：在构建向大模型发送的 API Payload 时，必须显式过滤掉历史消息中的 `reasoning_content`。这能显著节省 Token 消耗并减少模型对长上下文指令遵循的干扰。

### 2.3 并发安全 (Concurrency Safety)
*   **Socket 锁保护**：在多线程环境（如 Socket 监听与消息广播并行）下，必须使用 `threading.Lock()` 保护共享资源（如 `self.clients` 列表）。
*   **广播策略**：采用“先收集异常客户端，后统一清理”的策略，避免在迭代列表时进行删除操作导致程序崩溃。

### 2.4 工具规范
*   **纯 Python 实现**：对于文件系统与搜索工具（如 `glob`, `grep_search`），必须优先使用 Python 内置模块（如 `pathlib`, `re`）进行纯代码实现，避免依赖外部系统级命令（如 `git grep` 或系统 `grep`）。这确保了在不同操作系统（特别是 Windows）和无特定环境变量的机器上不会出现不可预期的异常。
*   **结构化输出与降噪**：工具输出结果应格式化为易于大模型阅读的纯文本格式（包含文件路径和对应行号），摒弃冗长的 JSON 数组输出。此外，必须复用 `pathspec` 库强行拦截所有在 `.gitignore` 中的文件（如 `node_modules/`, `__pycache__/`），最大限度减少上下文噪音和 Token 消耗。
*   **Shell 执行防线**：对于非交互式的 shell 命令（如 `run_shell_command`），强制设定 `timeout`（如 120 秒）以防止进程因等待输入（如 Windows `set /p`）而导致整个代理系统挂起；此外，对超长的终端日志输出（如构建输出）必须执行掐头去尾截断以防撑爆 Token 上限。在 Windows 环境下必须封装为 `powershell.exe -NoProfile -Command` 执行以兼容复杂命令与管道。必须在 `subprocess.run` 和 `subprocess.Popen` 调用中显式传入 `stdin=subprocess.DEVNULL`，以防止如 `git status` 等命令在继承父进程管道时意外阻塞等待输入，从而引发死锁。

### 2.5 测试与自动化死循环防御
*   **状态推进强保证**: 在执行自动化的工具调用循环时，即使在工具执行层面或模块加载时发生未捕获异常（如 `SyntaxError` ），状态管理器也必须确保该工具调用的 `executed` 状态或整体 `tool_call_mode` 被正确推进或标记为失败，而非直接中断跳过状态更新。否则，未完成状态将被重新发送给大模型，导致大模型不断重复发起相同的工具调用，从而引发自动化测试脚本或自动执行循环中的无限重试死循环。

### 2.6 调试元数据记录 (Debug Metadata)
*   **启用工具记录**: 在 `add_message` 中，如果角色为 `user`，会自动在 `metadata` 中记录当前启用的工具列表 (`enabled_tools`)，以便在分析 JSON 会话记录时定位工具调用异常。
*   **Payload 过滤**: 在 `get_full_payload` 中，必须显式过滤掉 `enabled_tools` 等仅限本地调试的元数据，确保不会将其发送给大模型 API 造成潜在的 400 错误或上下文污染。

---

## 3. 环境陷阱与第三方 API 怪癖 (Environment & API Peculiarities)

### 3.1 大模型 API 适配
*   **工具参数 Schema (JSON Schema) 的多态与 Strict 模式限制**：部分模型（如 DeepSeek）在使用 Strict 模式 (Structured Outputs, `strict: True`) 时，对 JSON Schema 有严格但自相矛盾的要求。一方面它要求所有 `properties` 都必须在 `required` 列表中（OpenAI 规范），另一方面如果尝试通过 `type: ["string", "null"]` 将某些参数变为可选时，它又会报错 400 `unknown variant array`（不支持 OpenAPI 3.1 数组类型声明）。因此，为了兼容这些模型的工具调用功能，必须在构造 tool 定义时**移除 `strict: True`**，并使用纯字符串形式定义 `type`（如 `type: "string"`），从而回退到标准的无结构化输出约束的函数调用模式。
*   **Thinking/Reasoning 支持差异**：
    *   部分模型（如 Kimi）在启用思维链时对工具调用消息有特殊校验：如果包含工具调用，则必须显式包含 `reasoning_content`（哪怕为空串），否则会报 400 错误。
    *   逻辑层必须具备平滑处理不同模型对 `reasoning_content` 字段支持差异的能力。
*   **错误处理**：严禁使用宽泛的 `except Exception: pass`。必须捕获具体异常并通过 `emit_error` 向上层反馈真实的堆栈信息。

### 3.2 终端渲染保护
*   **ANSI 泄露与提示符闪烁**：在使用 `prompt_toolkit` 时，必须配合 `patch_stdout()` 拦截所有标准输出（包括 `Rich` 的打印），以保护输入提示符不被异步输出冲散。
*   **编码约定**：全系统强制使用 UTF-8 编码，以支持中文字符的正确显示与处理。

---

## 4. 短期路线图与技术债 (Short-term Roadmap & Tech Debt)

### 4.1 待办核心功能 (Backlog)
*   **工具系统扩展**: 实现鲁棒的文件系统工具 (`ls`, `read_file`, `write_file`, `replace`, `glob`, `grep_search`)，支持 `.gitignore` 过滤。(已完成)

### 4.2 技术债清理
*   **Pydantic 迁移**: 逐步将所有消息模型完全迁移至 Pydantic，利用其内置的验证与反序列化机制替代手动字典转换。