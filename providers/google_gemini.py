"""
Google Gemini策略
适配Google Gemini API
"""
from typing import List, Dict, Any, Optional
from google import genai

from . import ProviderStrategy, register_provider
from message_models import InternalMessage, ChatOptions, create_text_message, ProviderConfig


class GoogleGeminiStrategy(ProviderStrategy):
    """Google Gemini策略"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = genai.Client(api_key=self.api_key)
    
    def supports_feature(self, feature: str) -> bool:
        """检查是否支持特定功能"""
        # 从配置中检查
        if feature in self.config.features:
            return True
            
        supported_features = {
            "temperature": True,
            "json_output": True,
            "tools": True,
            "streaming": True,
        }
        return supported_features.get(feature, False)
    
    def normalize_options(self, options: ChatOptions) -> ChatOptions:
        """规范化选项"""
        # Google推荐温度为1.0
        if options.temperature is None:
            options.temperature = self.config.defaults.get("temperature", 1.0)
            
        # 如果是布尔值，映射到默认级别或OFF
        if isinstance(options.reasoning, bool):
            if options.reasoning:
                options.reasoning = self.config.features.get("reasoning", {}).get("default", "MEDIUM")
            else:
                options.reasoning = "OFF"
                
        # "on" 映射到默认级别
        if options.reasoning == "on":
            options.reasoning = self.config.features.get("reasoning", {}).get("default", "MEDIUM")
        
        # 确保大写 (SMALL, MEDIUM, LARGE, OFF)
        if isinstance(options.reasoning, str):
            options.reasoning = options.reasoning.upper()
            
        return options

    def format_messages(self, messages: List[InternalMessage]) -> List[Dict[str, Any]]:
        """将内部消息格式转换为Gemini格式"""
        formatted = []
        for msg in messages:
            # Gemini使用不同的角色映射
            gemini_role = "user" if msg.role == "user" else "model"
            
            # 构建parts
            parts = []
            for part in msg.content:
                if part.type == "text":
                    parts.append({"text": part.content})
                # 其他类型消息暂不处理
            
            if parts:
                formatted.append({
                    "role": gemini_role,
                    "parts": parts
                })
        return formatted
    
    def build_api_payload(
        self, 
        formatted_messages: List[Dict[str, Any]], 
        options: ChatOptions
    ) -> Dict[str, Any]:
        """构建API请求负载"""
        # 导入types模块
        from google.genai import types
        
        # 构建config字典
        config_kwargs = {}
        
        if options.temperature is not None:
            config_kwargs["temperature"] = options.temperature
        
        if options.max_tokens is not None:
            config_kwargs["max_output_tokens"] = options.max_tokens
        
        if options.top_p is not None:
            config_kwargs["top_p"] = options.top_p
        
        # JSON输出模式
        if options.json_output:
            config_kwargs["response_mime_type"] = "application/json"
        
        # 思维链配置 - 使用thinking_config而不是reasoning_effort
        if options.reasoning and options.reasoning != "OFF":
            # 映射reasoning值到thinking_level
            reasoning_map = {
                "SMALL": "LOW",
                "MEDIUM": "MEDIUM", 
                "LARGE": "HIGH"
            }
            thinking_level = reasoning_map.get(options.reasoning, options.reasoning)
            # 创建ThinkingConfig对象，然后转换为字典
            thinking_config = types.ThinkingConfig(
                thinking_level=thinking_level
            )
            # 将ThinkingConfig对象转换为字典
            config_kwargs["thinking_config"] = {
                "thinking_level": thinking_config.thinking_level
            }
            
        # 工具配置
        if options.tools:
            config_kwargs["tools"] = options.tools

        return {
            "model": self.model,
            "contents": formatted_messages,
            "config": config_kwargs  # 使用字典而不是GenerateContentConfig对象
        }
    
    def call_api(self, payload: Dict[str, Any]) -> Any:
        """调用Gemini API"""
        try:
            # 提取参数
            model = payload.get("model")
            contents = payload.get("contents")
            config = payload.get("config")
            
            # 调用Gemini API
            # config参数直接传入字典，SDK内部会验证是否符合 GenerateContentConfig
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return response
        except Exception as e:
            # 捕获异常并包含payload信息以便调试
            raise Exception(f"Gemini API调用失败: {str(e)}")
    
    def parse_response(self, api_response: Any) -> str:
        """解析API响应"""
        if hasattr(api_response, 'text'):
            return api_response.text
        elif hasattr(api_response, 'candidates') and len(api_response.candidates) > 0:
            candidate = api_response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                parts = candidate.content.parts
                if parts and hasattr(parts[0], 'text'):
                    return parts[0].text
        
        return str(api_response)


# 注册提供商
register_provider("google", GoogleGeminiStrategy)
