# 修复加载历史记录与工具架构校验 Bug (2026-03-26)

## 决策意图
本次开发主要修复了读取聊天记录时产生的两个关键错误：
1. **重复的系统指令**：`load_context_from_file` 先调用了 `clear_context`，后者不仅会重置状态，还会自动加载 `rules.md` 中的系统指令。如果存档 JSON 中也包含系统指令，直接将两者合并会导致历史上下文中出现重复的 System Role 消息。
   *修复方式*：在 `clear_context` 执行后，明确将 `self.messages` 置空，确保历史记录被纯粹地恢复，而不会和自动加载的规则发生堆叠。
2. **DeepSeek Strict 模式对 JSON Schema 的严格限制**：当读取历史记录后启用工具并生成 Payload 时，发生冲突：
   - 报错一 `unknown variant 'array'`：DeepSeek 不支持 OpenAPI 3.1 风格的 `type: ["array", "null"]` 或 `type: ["string", "null"]` 多态数组类型声明，而要求纯字符串类型定义（例如 `type: "array"`）。我们去掉了所有的多态类型。
   - 报错二 `Required properties must match all properties in the object`：当我们去掉多态类型并试图保留部分参数作为非 `required`（即可选参数）时，DeepSeek 的 `strict: True` (Structured Outputs) 机制又强制要求所有 properties 必须被声明为 required。
   由于它既要求所有的属性 required，又不支持声明 null 来表示可选，这就造成了逻辑死锁。
   *修复方式*：在 `chat_logic_v2.py` 的 `_create_tool_definition` 中，彻底移除了 `strict: True`。这使得模型回退到了常规的函数调用模式，不再强制进行严苛的结构化检查，完美兼容了可选参数的解析。

## 防御性记录
- **关于工具类型的防御机制**：曾以为 `strict: True` 和 `["array", "null"]` 是被所有主流大模型支持的最佳实践。但实际上由于各大厂商对 Structured Outputs / Strict 模式的实现各异，同时存在解析 Bug。未来的工具定义应当避免开启 `strict: True`，并使用标准的字符串 `type` 定义。
- **关于 API 兼容性验证脚本**：在 `test/test_load_history.py` 中编写了一个验证脚本。为了不依赖真实 API Token 并且防止网络波动影响测试稳定性，该脚本直接调用 `chat_logic.get_full_payload` 并在本地验证其生成的 Schema 结构。

## 验证依据
- **单元测试覆盖**：执行了 `python test/test_load_history.py`。
  1. 验证 `messages` 列表中仅包含一条 `role == "system"` 的消息，确认没有重复加载。
  2. 提取 `payload["tools"]` 中的 `parameters` Schema，断言其所有 `properties` 中的 `type` 字段必须为字符串，而不允许为 `list`。
  3. 通过移除 `strict: True`，杜绝了 `Required properties must match all properties in the object` 的报错触发。测试通过。
