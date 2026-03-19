"""
OpenAI兼容策略
适配DeepSeek等OpenAI兼容的API
"""
import os
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI

from . import ProviderStrategy, register_provider
from message_models import InternalMessage, ChatOptions, create_text_message, ProviderConfig


class OpenAICompatibleStrategy(ProviderStrategy):
    """OpenAI兼容策略"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=config.base_url if config.base_url and config.base_url != "N/A" else None
        )
    
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
        options = super().normalize_options(options)
        
        # OpenAI兼容API通常只有enabled/disabled reasoning
        reasoning_config = self.config.features.get("reasoning", {})
        if reasoning_config.get("type") == "boolean":
            if options.reasoning in ["low", "medium", "high", "minimal", "on", True]:
                options.reasoning = True
            elif options.reasoning in ["off", False]:
                options.reasoning = False
        
        return options

    def format_messages(self, messages: List[InternalMessage]) -> List[Dict[str, Any]]:
        """将内部消息格式转换为OpenAI格式"""
        formatted = []
        for msg in messages:
            # 处理文本消息
            text_content = ""
            for part in msg.content:
                if part.type == "text":
                    text_content += part.content
                # 其他类型消息暂不处理
            
            # 构建基础消息
            formatted_msg = {
                "role": msg.role,
                "content": text_content if text_content else ""
            }
            
            # 处理tool消息
            if msg.role == "tool":
                tool_call_id = msg.metadata.get("tool_call_id")
                if tool_call_id:
                    formatted_msg["tool_call_id"] = tool_call_id
            
            # 处理包含tool_calls的assistant消息
            elif msg.role == "assistant" and "tool_calls" in msg.metadata:
                tool_calls = msg.metadata["tool_calls"]
                if tool_calls:
                    formatted_msg["tool_calls"] = tool_calls
                    # 如果content为空，可以设置为None或空字符串
                    if not formatted_msg["content"]:
                        formatted_msg["content"] = None
            
            formatted.append(formatted_msg)
        return formatted
    
    def build_api_payload(
        self, 
        formatted_messages: List[Dict[str, str]], 
        options: ChatOptions
    ) -> Dict[str, Any]:
        """构建API请求负载"""
        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": options.stream,
        }
        
        # 添加可选参数
        if options.temperature is not None:
            payload["temperature"] = options.temperature
        
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
            
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        
        # JSON输出模式
        if options.json_output:
            payload["response_format"] = {"type": "json_object"}
        
        # 工具调用
        if options.tools:
            payload["tools"] = options.tools
            
        # 思维链 (DeepSeek specific)
        if options.reasoning and options.reasoning is True:
            # DeepSeek R1 开启思维链（如果不是reasoner模型，或者需要显式开启）
            # 用户提示需要 extra_body={"thinking": {"type": "enabled"}}
            payload["extra_body"] = {"thinking": {"type": "enabled"}}
        
        return payload
    
    def call_api(self, payload: Dict[str, Any]) -> Any:
        """调用OpenAI兼容API"""
        try:
            response = self.client.chat.completions.create(**payload)
            return response
        except Exception as e:
            raise Exception(f"OpenAI API调用失败: {str(e)}")
    
    def parse_response(self, api_response: Any) -> Tuple[str, Optional[str]]:
        """解析API响应，返回(最终答案, 思维链内容)"""
        reasoning_content = None
        final_answer = ""
        
        if hasattr(api_response, 'choices') and len(api_response.choices) > 0:
            choice = api_response.choices[0]
            finish_reason = getattr(choice, 'finish_reason', None)
            
            if hasattr(choice, 'message'):
                message = choice.message
                
                # 提取思维链内容（如果存在）
                # 注意：当不开启思维链时，reasoning_content属性可能不存在
                if hasattr(message, 'reasoning_content'):
                    if message.reasoning_content:
                        reasoning_content = message.reasoning_content
                    # 如果reasoning_content存在但为空，保持None
                
                # 提取最终答案
                if hasattr(message, 'content') and message.content:
                    final_answer = message.content
                elif hasattr(message, 'tool_calls') and message.tool_calls:
                    # 处理工具调用
                    tool_calls = message.tool_calls
                    final_answer = f"[工具调用] {len(tool_calls)}个工具调用"
                else:
                    # Content为空且没有tool_calls
                    if finish_reason in ['length', 'content_filter']:
                        final_answer = f"[系统警告: 模型生成异常终止 (finish_reason: {finish_reason})，可能被截断或触发安全风控]"
                    else:
                        final_answer = ""
        elif hasattr(api_response, 'text'):
            final_answer = api_response.text
        else:
            final_answer = str(api_response)
        
        return final_answer, reasoning_content


# 注册提供商
register_provider("deepseek", OpenAICompatibleStrategy)
register_provider("openai", OpenAICompatibleStrategy)
register_provider("Silicon_flow", OpenAICompatibleStrategy)
