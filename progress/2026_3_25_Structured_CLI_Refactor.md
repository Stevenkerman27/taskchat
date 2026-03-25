# 2026-03-25 Structured CLI Refactor & Interactive Enhancements

## 决策意图
- **目标**: 实现 CLI 界面的结构化与交互着色，移除原本臃肿的 `if/else` 指令处理块。
- **架构设计**: 提取了 `CommandManager` 作为装饰器驱动的命令注册器，用于自动解析带引号的参数（通过 `shlex`）并分发请求。为了保证对 GUI 的最高向后兼容性（遵循 GUI Wrapper 模式），我们采用了**条件 I/O 分支策略 (Option A)**。
- **具体实现**: 当 `json_mode=True` 时，完全绕过 `rich` 渲染和 `prompt_toolkit` 输入，降级回使用基础的 `sys.stdin.readline` 和标准的 `print()`；当 `json_mode=False` 时，启用带有持久化历史记录支持的 `PromptSession` 和带有样式/面板支持的 `Console`。

## 防御性记录
- **关于第三方 UI 库与 JSON 通信的冲突**: 尝试过统一在所有模式下使用 `prompt_toolkit` 和 `rich`，但考虑到非交互环境（被 GUI 子进程调用）下，ANSI 控制字符和异步重绘逻辑极易破坏 JSON 数据流的纯净度，导致 GUI 端的 JSON 解析器崩溃。因此选择了物理隔离两套输入/输出流，这是针对 `json_mode` 最稳健的设计。
- **线程管理与 Prompt 阻塞**: `prompt_toolkit` 的 `session.prompt()` 会阻塞调用线程，因此在交互模式下我们在主线程运行它，将解析到的输入送入 `cmd_queue` 以复用现有的异步处理逻辑，从而不对整个程序的并发架构做侵入式修改。

## 验证依据
- **交互模式验证**: 通过带有模拟 API Key 的测试验证了 `/help` 和 `/exit` 等指令。证实了 Rich 格式化输出有效，且 `CommandManager` 成功处理了指令和参数拆分。
- **GUI 兼容性验证**: 使用 `--json` 启动参数模拟了 GUI 行为，系统按照预期生成了纯净的、无转义乱码的 JSON Lines 字符串（如 sys message 和 state 字典）。
- 验证了 `/multiline` 切换能够在交互模式下正确向 `prompt_toolkit` 传递多行标识（Esc+Enter 提交）。