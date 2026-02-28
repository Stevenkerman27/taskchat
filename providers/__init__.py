"""
提供商策略接口和注册
使用策略模式封装不同LLM提供商的API差异
"""
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type
from message_models import InternalMessage, ChatOptions, ProviderConfig


class ProviderStrategy(ABC):
    """提供商策略基类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.model = config.default_model
        
        # 获取API密钥
        self.api_key = os.getenv(config.api_key_env)
        if not self.api_key:
             # 有些提供商可能不需要API密钥（如本地Ollama），或在别处处理
             pass
             
    @property
    def provider_name(self) -> str:
        """提供商名称"""
        return self.config.name
    
    @property
    def supported_models(self) -> List[str]:
        """支持的模型列表"""
        return self.config.models
    
    def get_default_options(self) -> ChatOptions:
        """获取提供商推荐的默认选项"""
        return ChatOptions(
            temperature=self.config.defaults.get("temperature"),
            max_tokens=self.config.defaults.get("max_tokens"),
            reasoning=self.config.features.get("reasoning", {}).get("default")
        )
    
    def get_option_constraints(self) -> Dict[str, Any]:
        """获取选项约束（如温度范围、reasoning级别）"""
        return {
            "temperature_range": self.config.constraints.get("temperature_range", [0.0, 2.0]),
            "reasoning": self.config.features.get("reasoning", {})
        }
    
    def normalize_options(self, options: ChatOptions) -> ChatOptions:
        """规范化选项，应用提供商建议（如Google温度1.0）"""
        # 基类实现默认的规范化逻辑，如有需要，在子类中覆盖
        if options.temperature is None:
            options.temperature = self.config.defaults.get("temperature", 0.7)
        return options

    def set_model(self, model: str):
        """切换模型"""
        if model in self.config.models:
            self.model = model
        else:
            raise ValueError(f"模型 '{model}' 不被支持")
    
    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """检查是否支持特定功能"""
        pass
    
    @abstractmethod
    def format_messages(self, messages: List[InternalMessage]) -> Any:
        """将内部消息格式转换为提供商特定格式"""
        pass
    
    @abstractmethod
    def build_api_payload(
        self, 
        formatted_messages: Any, 
        options: ChatOptions
    ) -> Dict[str, Any]:
        """构建API请求负载"""
        pass
    
    @abstractmethod
    def call_api(self, payload: Dict[str, Any]) -> Any:
        """调用提供商API"""
        pass
    
    @abstractmethod
    def parse_response(self, api_response: Any) -> str:
        """解析API响应"""
        pass


# 提供商注册表
STRATEGY_REGISTRY: Dict[str, Type[ProviderStrategy]] = {}


def register_provider(name: str, strategy_class: Type[ProviderStrategy]):
    """注册提供商策略类"""
    STRATEGY_REGISTRY[name] = strategy_class


def get_provider_strategy(name: str) -> Type[ProviderStrategy]:
    """获取提供商策略类"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Provider '{name}' not found. Available: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]


def list_providers() -> List[str]:
    """列出所有注册的提供商"""
    return list(STRATEGY_REGISTRY.keys())


# 导入具体策略类以触发注册
try:
    from .openai_compatible import OpenAICompatibleStrategy
    from .google_gemini import GoogleGeminiStrategy
except ImportError as e:
    print(f"Warning: Failed to import provider strategies: {e}")
