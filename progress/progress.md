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

### 2.4 跨平台鲁棒性优先
*   **纯 Python 实现**：对于文件系统与搜索工具（如 `glob`, `grep_search`），必须优先使用 Python 内置模块（如 `pathlib`, `re`）进行纯代码实现，避免依赖外部系统级命令（如 `git grep` 或系统 `grep`）。这确保了在不同操作系统（特别是 Windows）和无特定环境变量的机器上不会出现不可预期的异常。
*   **结构化输出与降噪**：工具输出结果应格式化为易于大模型阅读的纯文本格式（包含文件路径和对应行号），摒弃冗长的 JSON 数组输出。此外，必须复用 `pathspec` 库强行拦截所有在 `.gitignore` 中的文件（如 `node_modules/`, `__pycache__/`），最大限度减少上下文噪音和 Token 消耗。

---

## 3. 环境陷阱与第三方 API 怪癖 (Environment & API Peculiarities)

### 3.1 大模型 API 适配
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