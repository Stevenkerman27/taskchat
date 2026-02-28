"""
重构的ChatLogic类
使用策略模式适配多提供商和高级功能
"""
import os
import yaml
from typing import List, Dict, Any, Optional, Tuple
from message_models import InternalMessage, ChatOptions, ProviderConfig, create_text_message, convert_simple_messages
from providers import get_provider_strategy, list_providers


class ChatLogicV2:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.raw_config = self._load_config()
        self.providers_configs: Dict[str, ProviderConfig] = self._parse_provider_configs()
        self.current_strategy = None
        self.messages: List[InternalMessage] = []
        self.options = ChatOptions()
        self._init_strategy()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

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
    
    def chat(self, user_input: str) -> Tuple[str, Dict[str, Any]]:
        """发送聊天请求"""
        # 获取负载（确保与预览一致）
        payload = self.get_full_payload(user_input)
        
        try:
            # 调用API
            response = self.current_strategy.call_api(payload)
            
            # 解析响应
            assistant_response = self.current_strategy.parse_response(response)
            
            # 只有在API调用成功后才更新上下文
            self.add_message("user", user_input)
            self.add_message("assistant", assistant_response)
            
            return assistant_response, payload
            
        except Exception as e:
            # API调用失败，返回错误信息但仍返回payload用于调试
            error_msg = f"Error: {str(e)}"
            return error_msg, payload
    
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
