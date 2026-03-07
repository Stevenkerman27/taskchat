"""
重构的ChatLogic类
使用策略模式适配多提供商和高级功能
"""
import os
import yaml
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
        self.messages: List[InternalMessage] = []
        self.options = ChatOptions()
        self.tools_config = self._load_tools_config()
        self._init_strategy()
        
        # 工具调用状态管理
        self.pending_tool_calls: List[Dict[str, Any]] = []
        self.tool_call_mode: bool = False
        self.last_user_input: str = ""
        self.last_payload: Dict[str, Any] = {}
    
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
        
        # 收集所有启用的工具
        all_tools = []
        
        # 从工具组添加工具
        tool_groups = self.tools_config.get('tool_groups', {})
        for group_name in enabled_groups:
            if group_name in tool_groups:
                group_tools = tool_groups[group_name].get('tools', [])
                for tool_name in group_tools:
                    if tool_name in self.tools_config.get('tools', {}):
                        tool_def = self._create_tool_definition(tool_name)
                        if tool_def:
                            all_tools.append(tool_def)
        
        # 添加单独启用的工具
        for tool_name in enabled_tools:
            if tool_name in self.tools_config.get('tools', {}):
                tool_def = self._create_tool_definition(tool_name)
                if tool_def:
                    all_tools.append(tool_def)
        
        # 设置工具选项
        if all_tools:
            self.options.tools = all_tools
    
    def _create_tool_definition(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """创建工具定义"""
        if tool_name not in self.tools_config.get('tools', {}):
            return None
        
        tool_info = self.tools_config['tools'][tool_name]
        return {
            "type": "function",
            "function": {
                "name": tool_info.get('name', tool_name),
                "description": tool_info.get('description', ''),
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
    
    def _handle_tool_calls(self, user_input: str, tool_calls: List[Any], original_payload: Dict[str, Any]) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """处理工具调用 - 现在只准备工具调用，不自动执行"""
        try:
            # 保存状态用于手动工具调用
            self.last_user_input = user_input
            self.last_payload = original_payload
            self.tool_call_mode = True
            self.pending_tool_calls = []
            
            # 添加用户消息到上下文
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
            
            return executed_tools
            
        except Exception as e:
            return [{"error": f"工具执行失败: {str(e)}"}]
    
    def send_tool_results_to_agent(self) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """将工具结果发送给agent获取最终答案"""
        try:
            # 检查是否所有工具都已执行
            if not all(tool_call["executed"] for tool_call in self.pending_tool_calls):
                return "请先执行所有待处理的工具调用", None, self.last_payload
            
            # 构建包含工具结果的payload进行第二轮调用
            formatted_messages = self.current_strategy.format_messages(self.messages)
            
            # 构建新的payload（不包含工具定义，因为已经调用过了）
            new_payload = self.last_payload.copy()
            new_payload["messages"] = formatted_messages
            if "tools" in new_payload:
                del new_payload["tools"]  # 移除工具定义，避免重复调用
            
            # 调用API获取最终答案
            response = self.current_strategy.call_api(new_payload)
            final_answer, reasoning_content = self.current_strategy.parse_response(response)
            
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
        
        # 移除最后一条助手消息（工具调用消息）
        if self.messages and self.messages[-1].role == "assistant":
            self.messages.pop()
        # 移除最后一条用户消息
        if self.messages and self.messages[-1].role == "user":
            self.messages.pop()
    
    def _create_assistant_message_with_tool_calls(self, tool_calls: List[Any]) -> InternalMessage:
        """创建包含tool_calls的助手消息"""
        from message_models import InternalMessage, MessagePart
        
        # 创建消息内容
        content = [MessagePart(type="text", content="[工具调用]")]
        
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
        for name, config in self.providers_configs.items():
            if config.api_key_env == self.current_strategy.config.api_key_env:
                return name
        return "unknown"
    
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
        
        return list(set(enabled_tools))  # 去重