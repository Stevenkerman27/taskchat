# 2026-03-25 CLI 终端渲染修复

## 决策意图
修复 CLI 中出现的两个核心问题：
1. **Prompt 消失**: 在后台线程（如 Socket 通信或异步输出）打印内容时，`prompt_toolkit` 的提示符 `>` 会被覆盖或移位。
2. **ANSI 源码泄露**: 引入 `patch_stdout()` 后，由于 `rich` 直接向 `stdout` 写入 ANSI 转义序列，`prompt_toolkit` 默认将其作为纯文本截获并重新打印，导致屏幕上出现 `\x1b[31m` 等代码。

**采用方案**:
参考 `ansitest.py` 的方案，将 `rich` 的渲染管线与 `prompt_toolkit` 的输出管线统一：
- 使用 `rich.console.capture()` 拦截原本要输出的内容。
- 将捕获的带有 ANSI 码的字符串包装为 `prompt_toolkit.formatted_text.ANSI` 对象。
- 使用 `prompt_toolkit.print_formatted_text` 进行最终输出。
- 在 `input_thread` 中，使用 `patch_stdout()` 上下文包装 `session.prompt()`。

## 防御性记录
- **直接使用 `print()` 的失败**: 直接在 `patch_stdout` 开启时使用 `print()` 会导致 `prompt_toolkit` 无法识别字符串内的 ANSI 颜色代码，从而将其作为字面量打印。
- **并发冲突**: 必须确保所有向终端打印的操作都经过 `safe_print`，否则未被拦截的 `stdout.write` 依然可能破坏 `prompt_toolkit` 的提示符管理。

## 验证依据
- 在 `TerminalRenderer` 中实现了 `safe_print` 方法。
- 更新了所有渲染方法（`render_error`, `render_system` 等）以使用 `safe_print`。
- 更新了主程序的 `_cmd_state` 和 `_cmd_multiline` 等直接打印处。
- 在 `input_thread` 中正确包裹了 `session.prompt`。
- 确认了 `json_mode` 下依然保持原始的 `print(json.dumps(...))` 逻辑，以兼容管道重定向。
