"""
重构的ChatLogic类
使用策略模式适配多提供商和高级功能
"""
import os
import yaml
import datetime
from typing import List, Dict, Any, Optional, Tuple
from message_models import InternalMessage, ChatOptions, ProviderConfig, create_text_message, convert_simple_messages
from providers import get_provider_strategy, list_providers
import json


class ChatLogicV2:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.raw_config = self._load_config()
        self.providers_configs: Dict[str, ProviderConfig] = self._parse_provider_configs()
        self.current_strategy = None
        self.messages: List[InternalMessage] = [
            create_text_message("system", "你是一个强大的AI代码助手。当用户提出需要多步操作的任务时，请自主规划步骤并连续调用工具直到任务完全完成。不要在任务中途停止。如果前一个工具调用成功，请继续调用下一个工具，直到达到最终目标。")
        ]
        self.options = ChatOptions()
        self.tools_config = self._load_tools_config()
        self._init_strategy()
        
        # 工具调用状态管理
        self.pending_tool_calls: List[Dict[str, Any]] = []
        self.tool_call_mode: bool = False
        self.last_user_input: str = ""
        self.last_payload: Dict[str, Any] = {}
        
        # 聊天记录保存相关
        self.contexts_dir = "contexts"
        self._ensure_contexts_dir()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _load_tools_config(self) -> Dict[str, Any]:
        """加载工具配置文件"""
        try:
            with open("tools/tools.yaml", 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"警告: 无法加载工具配置文件: {e}")
            return {}

    def _parse_provider_configs(self) -> Dict[str, ProviderConfig]:
        """解析提供商配置"""
        configs = {}
        for name, data in self.raw_config.get('providers', {}).items():
            configs[name] = ProviderConfig(
                name=data.get('name', name),
                api_key_env=data.get('api_key_env', ''),
                base_url=data.get('base_url'),
                models=data.get('models', []),
                default_model=data.get('default_model', ''),
                features=data.get('features', {}),
                defaults=data.get('defaults', {}),
                constraints=data.get('constraints', {})
            )
        return configs
    
    def _init_strategy(self):
        """初始化默认策略"""
        default_provider_name = self.raw_config.get('default_provider', 'deepseek')
        if default_provider_name not in self.providers_configs:
            raise ValueError(f"默认提供商 '{default_provider_name}' 不在配置中")
        
        provider_config = self.providers_configs[default_provider_name]
        strategy_class = get_provider_strategy(default_provider_name)
        self.current_strategy = strategy_class(provider_config)
        self.current_provider_name = default_provider_name
        
        # 应用提供商默认选项
        self.options = self.current_strategy.get_default_options()
        
        # 加载工具配置到选项
        self._load_tools_to_options()
    
    def _load_tools_to_options(self):
        """加载工具配置到聊天选项"""
        if not self.tools_config:
            return
        
        # 获取启用的工具组
        enabled_groups = self.tools_config.get('defaults', {}).get('enabled_groups', [])
        enabled_tools = self.tools_config.get('defaults', {}).get('enabled_tools', [])
        
        # 收集所有启用的工具，使用集合去重
        all_tools_defs = []
        added_tool_names = set()
        
        def add_tool_by_name(tool_name):
            if tool_name in added_tool_names:
                return
            if tool_name in self.tools_config.get('tools', {}):
                tool_def = self._create_tool_definition(tool_name)
                if tool_def:
                    all_tools_defs.append(tool_def)
                    added_tool_names.add(tool_name)
        
        # 从工具组添加工具
        tool_groups = self.tools_config.get('tool_groups', {})
        for group_name in enabled_groups:
            if group_name in tool_groups:
                group_tools = tool_groups[group_name].get('tools', [])
                for tool_name in group_tools:
                    add_tool_by_name(tool_name)
        
        # 添加单独启用的工具
        for tool_name in enabled_tools:
            add_tool_by_name(tool_name)
        
        # 设置工具选项
        self.options.tools = all_tools_defs if all_tools_defs else None
    
    def _create_tool_definition(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """创建工具定义，遵循DeepSeek strict模式JSON Schema格式要求"""
        if tool_name not in self.tools_config.get('tools', {}):
            return None
        
        tool_info = self.tools_config['tools'][tool_name]
        return {
            "type": "function",
            "function": {
                "name": tool_info.get('name', tool_name),
                "description": tool_info.get('description', ''),
                "strict": True,  # 启用strict模式
                "parameters": tool_info.get('parameters', {})
            }
        }
    
    def set_provider(self, provider_name: str, model: Optional[str] = None):
        """切换提供商和模型"""
        if provider_name not in self.providers_configs:
            raise ValueError(f"提供商 '{provider_name}' 不在配置中")
        
        provider_config = self.providers_configs[provider_name]
        strategy_class = get_provider_strategy(provider_name)
        
        # 创建新的策略实例
        self.current_strategy = strategy_class(provider_config)
        self.current_provider_name = provider_name
        
        # 如果指定了模型，则切换到该模型
        if model:
            self.current_strategy.set_model(model)
        
        # 重新应用该提供商的默认选项（或根据需要调整）
        self.options = self.current_strategy.get_default_options()
        
        # 重新加载工具配置
        self._load_tools_to_options()
    
    def get_available_providers(self) -> List[str]:
        """获取可用的提供商标识列表"""
        return list(self.providers_configs.keys())
    
    def get_models_for_provider(self, provider_name: str) -> List[str]:
        """获取指定提供商支持的模型列表"""
        if provider_name in self.providers_configs:
            return self.providers_configs[provider_name].models
        return []
    
    def add_message(self, role: str, content: str, **kwargs):
        """添加消息到上下文"""
        message = create_text_message(role, content, **kwargs)
        self.messages.append(message)
    
    def clear_context(self):
        """清空上下文"""
        self.messages = []
    
    def set_option(self, key: str, value: Any):
        """设置聊天选项"""
        if hasattr(self.options, key):
            setattr(self.options, key, value)
        else:
            # 如果不是标准选项，放入provider_specific
            self.options.provider_specific[key] = value
    
    def get_default_options(self) -> ChatOptions:
        """获取当前提供商的默认选项"""
        return self.current_strategy.get_default_options()
    
    def get_option_constraints(self) -> Dict[str, Any]:
        """获取当前提供商的选项约束"""
        return self.current_strategy.get_option_constraints()
    
    def get_full_payload(self, user_input: str = "") -> Dict[str, Any]:
        """
        获取完整的API请求负载
        确保与GUI预览框中的内容完全一致
        """
        # 创建临时消息列表
        temp_messages = self.messages.copy()
        if user_input:
            temp_messages.append(create_text_message("user", user_input))
        
        # 规范化选项
        normalized_options = self.current_strategy.normalize_options(self.options)
        
        # 使用当前策略格式化消息
        formatted_messages = self.current_strategy.format_messages(temp_messages)
        
        # 构建API负载
        payload = self.current_strategy.build_api_payload(formatted_messages, normalized_options)
        
        return payload
    
    def chat(self, user_input: str) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """发送聊天请求，返回(最终答案, 思维链内容, payload)"""
        # 获取负载（确保与预览一致）
        payload = self.get_full_payload(user_input)
        
        try:
            # 调用API
            response = self.current_strategy.call_api(payload)
            
            # 解析响应（现在返回最终答案和思维链内容）
            final_answer, reasoning_content = self.current_strategy.parse_response(response)
            
            # 检查是否有工具调用
            if hasattr(response, 'choices') and len(response.choices) > 0:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls'):
                    tool_calls = choice.message.tool_calls
                    if tool_calls:
                        # 处理工具调用
                        return self._handle_tool_calls(user_input, tool_calls, payload)
            
            # 只有在API调用成功后才更新上下文
            self.add_message("user", user_input)
            self.add_message("assistant", final_answer)
            
            return final_answer, reasoning_content, payload
            
        except Exception as e:
            # API调用失败，返回错误信息但仍返回payload用于调试
            error_msg = f"Error: {str(e)}"
            return error_msg, None, payload
    
    def _handle_tool_calls(self, user_input: Optional[str], tool_calls: List[Any], original_payload: Dict[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """处理工具调用 - 现在只准备工具调用，不自动执行"""
        try:
            # 保存状态用于手动工具调用
            if user_input is not None:
                self.last_user_input = user_input
            self.last_payload = original_payload
            self.tool_call_mode = True
            self.pending_tool_calls = []
            
            # 添加用户消息到上下文
            if user_input is not None:
                self.add_message("user", user_input)
            
            # 创建包含tool_calls的助手消息
            assistant_message = self._create_assistant_message_with_tool_calls(tool_calls)
            self.messages.append(assistant_message)
            
            # 保存待处理的工具调用信息
            for tool_call in tool_calls:
                self.pending_tool_calls.append({
                    "id": tool_call.id,
                    "function_name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments),
                    "executed": False,
                    "result": None
                })
            
            # 返回工具调用信息，而不是自动执行
            tool_call_info = f"检测到 {len(tool_calls)} 个工具调用，请在GUI中手动执行。"
            return tool_call_info, None, original_payload
            
        except Exception as e:
            error_msg = f"工具调用处理失败: {str(e)}"
            return error_msg, None, original_payload
    
    def execute_pending_tools(self) -> List[Dict[str, Any]]:
        """执行所有待处理的工具调用"""
        try:
            from tools.tools_impl import execute_tool
            
            executed_tools = []
            for tool_call in self.pending_tool_calls:
                if not tool_call["executed"]:
                    function_name = tool_call["function_name"]
                    arguments = tool_call["arguments"]
                    
                    try:
                        # 执行工具
                        tool_result = execute_tool(function_name, arguments)
                        
                        # 更新工具调用状态
                        tool_call["executed"] = True
                        tool_call["result"] = tool_result
                        
                        # 添加工具结果消息到上下文
                        self.add_message("tool", tool_result, tool_call_id=tool_call["id"])
                        
                        executed_tools.append({
                            "function_name": function_name,
                            "arguments": arguments,
                            "result": tool_result
                        })
                    except Exception as tool_e:
                        error_msg = f"执行异常: {str(tool_e)}"
                        tool_call["executed"] = True
                        tool_call["result"] = error_msg
                        self.add_message("tool", error_msg, tool_call_id=tool_call["id"])
                        
                        executed_tools.append({
                            "function_name": function_name,
                            "arguments": arguments,
                            "error": error_msg
                        })
            
            return executed_tools
            
        except Exception as e:
            return [{"function_name": "系统", "error": f"工具执行环境失败: {str(e)}"}]
    
    def send_tool_results_to_agent(self) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """将工具结果发送给agent获取最终答案"""
        try:
            # 检查是否所有工具都已执行
            if not all(tool_call["executed"] for tool_call in self.pending_tool_calls):
                return "请先执行所有待处理的工具调用", None, self.last_payload
            
            # 构建包含工具结果的payload进行第二轮调用
            formatted_messages = self.current_strategy.format_messages(self.messages)
            
            # 构建新的payload
            new_payload = self.last_payload.copy()
            new_payload["messages"] = formatted_messages
            
            # 调用API获取最终答案
            response = self.current_strategy.call_api(new_payload)
            final_answer, reasoning_content = self.current_strategy.parse_response(response)
            
            # 检查是否有新的工具调用
            if hasattr(response, 'choices') and len(response.choices) > 0:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls'):
                    tool_calls = choice.message.tool_calls
                    if tool_calls:
                        # 处理新的工具调用，不传入user_input避免重复添加
                        return self._handle_tool_calls(None, tool_calls, new_payload)
            
            # 如果没有工具调用且返回了系统警告（因为模型截断），保留工具模式状态，避免默默退出
            if final_answer and "[系统警告" in final_answer:
                # 依然添加助手消息
                self.add_message("assistant", final_answer)
                return final_answer, reasoning_content, new_payload

            # 添加最终助手消息
            self.add_message("assistant", final_answer)
            
            # 重置工具调用状态
            self.tool_call_mode = False
            self.pending_tool_calls = []
            self.last_user_input = ""
            self.last_payload = {}
            
            return final_answer, reasoning_content, new_payload
            
        except Exception as e:
            error_msg = f"发送工具结果失败: {str(e)}"
            return error_msg, None, self.last_payload
    
    def get_pending_tool_calls(self) -> List[Dict[str, Any]]:
        """获取待处理的工具调用列表"""
        return self.pending_tool_calls.copy()
    
    def is_in_tool_call_mode(self) -> bool:
        """检查是否处于工具调用模式"""
        return self.tool_call_mode
    
    def cancel_tool_calls(self):
        """取消工具调用，恢复正常聊天模式"""
        self.tool_call_mode = False
        self.pending_tool_calls = []
        self.last_user_input = ""
        self.last_payload = {}
        
        # 回退上下文，撤销由于未完成的工具调用链引发的所有消息
        while self.messages:
            last_msg = self.messages[-1]
            if last_msg.role == "tool":
                self.messages.pop()
            elif last_msg.role == "assistant":
                metadata = last_msg.metadata or {}
                if "tool_calls" in metadata:
                    self.messages.pop()
                else:
                    break
            else:
                # 遇到 user 或 system 消息时停止回退
                break
    
    def _create_assistant_message_with_tool_calls(self, tool_calls: List[Any]) -> InternalMessage:
        """创建包含tool_calls的助手消息"""
        from message_models import InternalMessage, MessagePart
        
        # 创建消息内容
        content = [MessagePart(type="text", content="")]
        
        # 创建消息
        message = InternalMessage(
            role="assistant",
            content=content,
            metadata={
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    }
                    for tool_call in tool_calls
                ]
            }
        )
        
        return message
    
    def supports_feature(self, feature: str) -> bool:
        """检查当前提供商是否支持特定功能"""
        return self.current_strategy.supports_feature(feature)
    
    def get_current_provider(self) -> str:
        """获取当前提供商标识"""
        return getattr(self, 'current_provider_name', "unknown")
    
    def get_current_model(self) -> str:
        """获取当前模型名称"""
        return self.current_strategy.model
    
    def get_tools_config(self) -> Dict[str, Any]:
        """获取工具配置"""
        return self.tools_config
    
    def get_enabled_tools(self) -> List[str]:
        """获取启用的工具列表"""
        enabled_tools = []
        
        if not self.tools_config:
            return enabled_tools
        
        # 获取启用的工具组
        enabled_groups = self.tools_config.get('defaults', {}).get('enabled_groups', [])
        enabled_tools_list = self.tools_config.get('defaults', {}).get('enabled_tools', [])
        
        # 从工具组添加工具
        tool_groups = self.tools_config.get('tool_groups', {})
        for group_name in enabled_groups:
            if group_name in tool_groups:
                group_tools = tool_groups[group_name].get('tools', [])
                enabled_tools.extend(group_tools)
        
        # 添加单独启用的工具
        enabled_tools.extend(enabled_tools_list)
        
        return sorted(list(set(enabled_tools)))  # 去重并排序，确保确定性顺序（利于缓存命中）
    
    def set_enabled_tool_groups(self, enabled_groups: List[str]) -> None:
        """
        设置启用的工具组
        
        Args:
            enabled_groups: 要启用的工具组名称列表
        """
        if not self.tools_config:
            return
        
        # 更新配置中的默认工具组
        defaults = self.tools_config.get('defaults', {})
        defaults['enabled_groups'] = enabled_groups
        
        # 重新加载工具配置到选项
        self._load_tools_to_options()
    
    def get_available_providers(self) -> List[Dict[str, Any]]:
        """获取所有可用的提供商和模型"""
        providers_info = []
        for name, config in self.providers_configs.items():
            providers_info.append({
                "id": name,
                "name": config.name,
                "models": config.models,
                "default_model": config.default_model,
                "is_current": name == self.current_provider_name
            })
        return providers_info

    def get_available_tool_groups(self) -> Dict[str, Any]:
        """获取所有可用的工具组和当前状态"""
        if not self.tools_config:
            return {"groups": {}, "enabled": []}
        
        groups = self.tools_config.get('tool_groups', {})
        enabled = self.tools_config.get('defaults', {}).get('enabled_groups', [])
        return {"groups": groups, "enabled": enabled}

    def get_current_options_dict(self) -> Dict[str, Any]:
        """获取当前配置项的字典表示（排除复杂对象）"""
        return {
            "temperature": self.options.temperature,
            "max_tokens": self.options.max_tokens,
            "top_p": self.options.top_p,
            "stream": self.options.stream,
            "json_output": self.options.json_output,
            "reasoning": self.options.reasoning,
            "provider_specific": self.options.provider_specific
        }

    def _ensure_contexts_dir(self):
        """确保contexts目录存在"""
        if not os.path.exists(self.contexts_dir):
            os.makedirs(self.contexts_dir)
    
    def is_in_reasoning_mode(self) -> bool:
        """
        检查是否处于思维链或工具调用等不完整的中间状态
        
        Returns:
            bool: 如果处于不完整状态则返回True
        """
        # 检查是否处于工具调用模式
        if self.tool_call_mode:
            return True
        
        # 检查是否有未完成的工具调用
        if self.pending_tool_calls and not all(tool_call["executed"] for tool_call in self.pending_tool_calls):
            return True
        
        return False
    
    def save_context_to_file(self, filename: str) -> bool:
        """
        保存当前聊天上下文到文件
        
        Args:
            filename: 文件名（不需要扩展名）
            
        Returns:
            bool: 保存是否成功
        """
        try:
            # 检查是否处于思维链模式
            if self.is_in_reasoning_mode():
                raise ValueError("无法在思维链中途保存聊天记录")
            
            # 确保文件名有.json扩展名
            if not filename.endswith('.json'):
                filename = f"{filename}.json"
                
            # 防御路径穿越攻击
            filename = os.path.basename(filename)
            
            filepath = os.path.join(self.contexts_dir, filename)
            
            # 准备保存的数据
            save_data = {
                "metadata": {
                    "saved_at": datetime.datetime.now().isoformat(),
                    "provider": self.get_current_provider(),
                    "model": self.get_current_model(),
                    "message_count": len(self.messages),
                    "tool_call_mode": self.tool_call_mode,
                    "pending_tools_count": len(self.pending_tool_calls)
                },
                "messages": []
            }
            
            # 序列化消息 - 确保格式正确
            for msg in self.messages:
                # 将InternalMessage转换为可序列化的字典
                # 使用model_dump()将MessagePart对象转换为字典
                msg_dict = {
                    "role": msg.role,
                    "content": [part.model_dump() for part in msg.content],
                    "metadata": msg.metadata
                }
                save_data["messages"].append(msg_dict)
            
            # 验证JSON格式正确性
            json_str = json.dumps(save_data, ensure_ascii=False, indent=2)
            
            # 验证JSON格式
            try:
                json.loads(json_str)  # 验证JSON格式正确
            except json.JSONDecodeError as e:
                print(f"JSON格式验证失败: {e}")
                return False
            
            # 原子写入：先写入临时文件，然后重命名为目标文件
            import tempfile
            temp_fd, temp_path = tempfile.mkstemp(dir=self.contexts_dir, suffix='.tmp')
            try:
                # 使用os.fdopen打开文件描述符
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                    # 确保数据已写入磁盘
                    f.flush()
                    os.fsync(f.fileno())
                # 重命名临时文件为目标文件（原子操作）
                os.replace(temp_path, filepath)
            except Exception as e:
                # 清理临时文件
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise e
            
            return True
            
        except Exception:
            raise
    
    def load_context_from_file(self, filename: str) -> bool:
        """
        从文件加载聊天上下文
        
        Args:
            filename: 文件名（需要完整路径或相对路径）
            
        Returns:
            bool: 加载是否成功
        """
        try:
            # 检查是否处于思维链模式
            if self.is_in_reasoning_mode():
                raise ValueError("无法在思维链中途加载聊天记录")
            
            # 确保文件路径正确
            if not os.path.isabs(filename):
                filepath = os.path.join(self.contexts_dir, filename)
            else:
                filepath = filename
            
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"文件不存在: {filepath}")
            
            # 读取文件并验证JSON格式
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    save_data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                # 尝试读取文件内容以提供更多信息
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                print(f"文件内容（前500字符）: {content[:500]}")
                raise ValueError(f"JSON格式错误: {e}")
            
            # 验证数据格式
            if "metadata" not in save_data or "messages" not in save_data:
                raise ValueError("无效的聊天记录文件格式")
            
            # 验证消息格式
            for i, msg_dict in enumerate(save_data["messages"]):
                if "role" not in msg_dict or "content" not in msg_dict:
                    raise ValueError(f"消息格式错误（索引 {i}）: 缺少必要字段")
                
                # 验证content格式
                content = msg_dict["content"]
                if not isinstance(content, list):
                    raise ValueError(f"消息格式错误（索引 {i}）: content必须是列表")
                
                for j, part in enumerate(content):
                    if not isinstance(part, dict) or "type" not in part or "content" not in part:
                        raise ValueError(f"消息格式错误（索引 {i}, 部分 {j}）: 消息部分格式不正确")
            
            # 清空当前上下文
            self.clear_context()
            
            # 恢复消息
            for msg_dict in save_data["messages"]:
                # 从字典恢复InternalMessage
                message = InternalMessage(
                    role=msg_dict["role"],
                    content=msg_dict["content"],
                    metadata=msg_dict.get("metadata", {})
                )
                self.messages.append(message)
            
            # 恢复工具调用状态（如果存在）
            metadata = save_data["metadata"]
            if metadata.get("tool_call_mode", False):
                self.tool_call_mode = True
                # 注意：pending_tool_calls无法从文件恢复，需要重新调用
            
            print(f"已加载聊天记录: {metadata.get('message_count', 0)} 条消息")
            return True
            
        except Exception:
            raise
    
    def list_saved_contexts(self) -> List[Dict[str, Any]]:
        """
        列出所有保存的聊天记录文件
        
        Returns:
            List[Dict[str, Any]]: 文件信息列表
        """
        try:
            self._ensure_contexts_dir()
            
            contexts = []
            for filename in os.listdir(self.contexts_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.contexts_dir, filename)
                    try:
                        # 读取元数据
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        metadata = data.get("metadata", {})
                        contexts.append({
                            "filename": filename,
                            "filepath": filepath,
                            "saved_at": metadata.get("saved_at", "未知"),
                            "provider": metadata.get("provider", "未知"),
                            "model": metadata.get("model", "未知"),
                            "message_count": metadata.get("message_count", 0),
                            "size_kb": os.path.getsize(filepath) / 1024
                        })
                    except Exception as e:
                        # 跳过无法读取的文件
                        print(f"无法读取文件 {filename}: {e}")
                        continue
            
            # 按保存时间排序（最新的在前）
            contexts.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
            return contexts
            
        except Exception as e:
            print(f"列出聊天记录失败: {e}")
            return []
