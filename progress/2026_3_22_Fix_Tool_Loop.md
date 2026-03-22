# 修复测试脚本陷入工具调用死循环的严重Bug

## 决策意图
本次修复解决了一个多重叠加导致的严重死循环Bug。在自动化执行测试（或正常使用命令行发送带有连续工具调用的任务）时，系统会在工具全部执行完毕后陷入无限重试循环，并不断抛出 Kimi (Moonshot API) 的 `400 reasoning_content missing` 错误。

核心修复点如下：
1. **彻底解决本地状态覆盖问题：** `chat_logic_v2.py` 中的 `send_tool_results_to_agent` 在成功或安全阻断而结束一轮工具调用时，会将 `self.tool_call_mode = False`，但**遗漏了调用 `self._save_state()`**。由于 `chat_cli_v2.py` 在推送状态时会调用 `is_in_tool_call_mode()`，该函数内部又调用了 `_load_state()`，直接导致 `tool_call_mode` 被从旧的本地文件中**错误恢复为 True**，并不断地通过 CLI 接口对外广播虚假的“待执行工具列表”。增加 `_save_state()` 后彻底根除了虚假事件。
2. **满足 Kimi API 的严格校验：** 当我们在 OpenAI 兼容层中组装包含工具调用的助手消息时，如果没有提供合法的 `reasoning_content`，对于开启了 thinking 模式的 Kimi 模型而言会被视为格式错误（Error code 20015）。原代码试图传入空字符串 `""` 填补该字段，但实际被 Kimi API 判定为非法。现在通过强制传入非空占位符 `"（工具调用暂无思考过程）"` 来满足其校验。
3. **增加测试脚本的防死锁健壮性：** `test_cli.py` 此前对 `tool_calls` 消息采取了盲目信任并自动重试的策略。现在加入了最大重试阈值，并且在开头加入 `/clear` 确保上下文残留不会污染测试。

## 防御性记录
- **关于 Kimi API 的失败尝试**：尝试完全从 payload 中删除 `reasoning_content` 键、或将其赋值为 `None`，依然会被报错拦截；赋值为空字符串 `""` 同样无济于事。Kimi API 严格要求开启 thinking 时，所有带有 `tool_calls` 的 assistant 消息必须包含非空字符串的 `reasoning_content`。
- **关于状态覆盖问题**：问题的核心在于“单一事实来源”模式的副作用：当在内存中修改了关键状态却不及时写回 JSON 文件时，下一个只读操作（由于封装了 `_load_state` 来确保实时同步）将会无意中覆写内存中的正确状态。今后所有改变控制流变量的操作，必须确保在结束时立刻刷入硬盘。

## 验证依据
- 启动 `test_cli.py` 的测试脚本模拟 `test_write.txt` 的读写流程。
- 验证不再触发 Kimi 的 `400 reasoning_content is missing` 报错。
- 确认在输出最终结果后，程序不会再循环陷入空工具执行逻辑，脚本可正常退出，测试通过。
