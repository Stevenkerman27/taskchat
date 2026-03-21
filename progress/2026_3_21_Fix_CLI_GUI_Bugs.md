# 开发进展记录 - 2026.03.21 - 修复 CLI/GUI 桥接及 Kimi 工具调用 Bug

## 修复 Bug 1：GUI 显示 "CLI bridge disconnected" 问题
**问题现象**：在展示长的 reasoning content（通常包含大量中文字符）后，GUI 容易异常断开并报错，而底层 CLI 依然正常输出了结果。
**决策意图**：
- 问题的根源在于原本的 Socket 读取逻辑：`data = self.sock.recv(4096).decode('utf-8')`。因为 `recv(4096)` 按字节数截断，很容易在 3 字节的 UTF-8 中文字符中间截断，导致 `decode('utf-8')` 抛出 `UnicodeDecodeError` 异常，从而中断了整个 Socket 监听线程。
- 将 `chat_gui_v2.py` 和 `chat_cli_v2.py` 中的读取逻辑均替换为 `with sock.makefile('r', encoding='utf-8') as f:`，利用标准的基于行的文本缓冲流进行读取。这样能够确保处理完整的字符边界，杜绝因为分块引发的解码错误。
**防御性记录**：
- 曾考虑使用 `.decode('utf-8', errors='ignore')` 或 `'replace'`，但这会破坏 JSON 的完整性，导致 `json.loads` 失败，治标不治本。使用 `makefile()` 是最标准且安全的解决网络流文本数据的方法。

## 修复 Bug 2：Kimi 模型在带有工具调用时报错 "missing reasoning_content"
**问题现象**：使用 Kimi 模型时，如果开启了思维链（thinking is enabled），当模型进行工具调用时，发送回传请求会报 HTTP 400 错误（`reasoning_content is missing in assistant tool call message`）。
**决策意图**：
- 某些提供商（例如开启了思考模式的 Kimi）严格遵循协议，当上下文中出现了包含工具调用的助手消息时，即使是工具调用也必须带有 `reasoning_content` 字段（哪怕为空），否则会被视为上下文格式不一致。
- 之前代码中 `chat_logic_v2.py` 在 `_handle_tool_calls` 时，完全丢弃了当前一轮提取出的 `reasoning_content`。
- 我们重构了相关方法的参数签名：
  1. `providers/openai_compatible.py` 中 `parse_response` 现在能正确捕获空字符串的 `reasoning_content`。
  2. `chat_logic_v2.py` 中，`chat()` 将 `reasoning_content` 传递给 `_handle_tool_calls()`。
  3. `_create_assistant_message_with_tool_calls` 现在会把 `reasoning_content` 存在 `msg.metadata` 中。
  4. `providers/openai_compatible.py` 的 `format_messages()` 针对 `assistant` 角色做了兼容：如果有保存下来的 `reasoning_content` 就带上；如果是带有 `tool_calls` 的助手消息，作为 Kimi 的防御性兜底，自动填充 `"reasoning_content": ""`。
**验证依据**：
- 确保 OpenAI 兼容 API 在生成消息序列时，对所有 `assistant` 附带了工具调用的消息都妥善处理了 `reasoning_content` 结构，能够通过诸如 Kimi、DeepSeek R1 等具有强 schema 校验的后端。
