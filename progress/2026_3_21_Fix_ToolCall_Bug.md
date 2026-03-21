# 开发进展记录 - 2026.03.21 - 修复连续工具调用导致 API 400 与无限循环的 Bug

## 修复连续工具调用导致 missing reasoning_content 与死循环
**问题现象**：当使用 Kimi 并开启思维链时，如果第一轮工具调用成功，助手发起**第二轮连续的工具调用**（例如先 get_time, 得到结果后再调用 write_file），API 会报错 `reasoning_content is missing in assistant tool call message at index 5`。随后 CLI test 脚本陷入无限发送 results 的死循环，无法退出。

**决策意图**：
- 第一步我修复了 `providers/openai_compatible.py` 中的解析与 `format_messages`，并修改了 `_handle_tool_calls` 签名的入参（由4个变为5个，增加 `reasoning_content`）。
- **根因分析**：发生 400 错误的真正原因是：在处理**连续工具调用**时，即在 `chat_logic_v2.py` 的 `send_tool_results_to_agent` 函数中，调用 API 获取响应后，如果发现模型发起了新的工具调用，之前代码只传递了 3 个参数给 `_handle_tool_calls`：`self._handle_tool_calls(None, tool_calls, new_payload)`。这不仅导致了 `takes 4 positional arguments but 5 were given` 的 TypeError，还意味着**第二轮往后所有的工具调用都丢掉了 `reasoning_content`**，从而被强校验格式的 Kimi 接口拒绝 (Error 400)。
- **连锁反应分析**：当 `send_tool_results_to_agent` 因为 `_handle_tool_calls` 参数数量报错或 API 400 报错时，为了让用户可以重试，系统会捕获异常并返回，**但并未退出 `tool_call_mode`**。此时测试脚本收到错误信息作为 `assistant` 消息后，立刻又收到了未改变的 `tool_calls` 状态，认为没有待执行的工具，于是再次发送 `send_results` 指令，从而引发了死循环。
- **解决方案**：在 `send_tool_results_to_agent` 的连续工具调用处理中，正确地解析出 `reasoning_content` 并将其传递给 `_handle_tool_calls` 函数：`return self._handle_tool_calls(None, tool_calls, new_payload, reasoning_content)`。

**验证依据**：
- 使用 `test_cli.py` 搭配 `Silicon_flow - moonshotai/Kimi-K2.5` 进行了完整端到端测试。该脚本能触发多轮连续的工具调用（获取时间+读取文件 -> 写入文件 -> 读取文件确认）。目前已不再出现 400 错误，测试脚本平稳执行完毕，并且文件 `test/test_write.txt` 内容被正确修改，确认核心冲突完美解决。
