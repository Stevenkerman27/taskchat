# DeepSeek Tool Call 功能集成

## 目标
集成DeepSeek的tool call功能到现有聊天系统中，通过配置文件管理工具，实现自动工具调用和结果处理。

## 已完成工作

### 1. 示例代码文件
- **文件**: `simple working egs/ds_tool_call_example.py`
- **内容**: 完整的DeepSeek tool call示例，包含：
  - 工具定义（list_directory, get_weather, calculate）
  - 工具执行函数
  - 完整的调用流程演示
  - 交互式测试界面

### 2. 工具配置文件
- **文件**: `tools.yaml`
- **内容**: 工具管理系统配置，包含：
  - 预定义工具库
  - 工具组配置
  - 默认工具配置
  - 工具实现映射
  - 注意事项和流程说明

### 3. 工具实现模块
- **文件**: `tools_impl.py`
- **内容**: 所有工具的实际实现，包含：
  - `list_directory()`: 列出当前目录文件
  - `get_current_time()`: 获取当前时间
  - `calculate()`: 计算数学表达式（安全评估）
  - `ping()`: 测试网络连接
  - `execute_tool()`: 统一工具执行接口
  - `load_tools_config()`: 加载配置文件

## 核心功能设计

### 工具调用流程
1. **用户输入** → 模型决定调用工具
2. **系统执行工具** → 获取JSON格式结果
3. **结果自动填充**到输入框（配置控制）
4. **用户点击发送** → 发送工具结果给模型
5. **模型生成最终回复**

### 配置关键参数
```yaml
result_handling:
  auto_fill_input: true      # 自动用工具返回值填充输入框
  ignore_user_input: true    # 忽略用户输入，使用工具结果
  require_send_click: true   # 需要点击发送按钮才发送
```

### 安全考虑
1. **计算器工具**: 使用字符白名单和安全评估
2. **系统工具**: 谨慎使用，添加权限控制
3. **网络工具**: 超时限制和输出限制

## 下一步计划

### 阶段一：基础集成（当前）
- [x] 创建示例代码和文档
- [x] 实现工具配置系统
- [x] 完成工具实现模块
- [ ] 集成到现有聊天逻辑
- [ ] 更新GUI支持工具调用

### 阶段二：完整功能
- [ ] 在ChatLogicV2中添加工具支持
- [ ] 在chat_gui_v2.py中添加工具管理界面
- [ ] 实现工具调用状态显示
- [ ] 添加工具调用历史记录

### 阶段三：高级特性
- [ ] 支持多轮工具调用
- [ ] 集成思考模式下的工具调用
- [ ] 添加工具调用可视化
- [ ] 实现工具调用模板

## 技术要点

### 1. DeepSeek API兼容性
- 完全兼容OpenAI tool call API
- 支持思考模式（reasoning mode）
- 正确处理reasoning_content

### 2. 配置文件驱动
- 工具定义集中管理
- 支持工具组和类别
- 可扩展的工具实现映射

### 3. 安全设计
- 输入验证和过滤
- 执行超时控制
- 错误处理和日志记录

## 使用示例

### 测试工具调用
```bash
# 设置API密钥
export DS_API_KEY=your-api-key

# 运行示例
python simple\ working\ egs/ds_tool_call_example.py
```

### 配置文件管理
```python
from tools_impl import load_tools_config, execute_tool

# 加载配置
config = load_tools_config("tools.yaml")

# 执行工具
result = execute_tool("list_directory", {})
```

## 注意事项

1. **API密钥**: 需要设置DS_API_KEY环境变量
2. **工具权限**: 系统工具可能需要额外权限
3. **网络连接**: 需要稳定的网络连接
4. **错误处理**: 工具调用失败时的优雅降级

## 参考文档
- DeepSeek官方API文档: https://api-docs.deepseek.com
- OpenAI tool call规范
- 项目现有架构文档