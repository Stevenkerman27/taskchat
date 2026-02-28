"""
统一消息格式接口
使用Pydantic模型定义内部统一的消息格式，支持多种消息类型和高级功能
"""
from typing import Literal, Optional, Union, List, Dict, Any
from pydantic import BaseModel, Field


class MessagePart(BaseModel):
    """消息部分基类，支持文本、工具调用、文件等类型"""
    type: Literal["text", "tool_call", "tool_result", "image", "reasoning"]
    content: Union[str, Dict[str, Any]]


class InternalMessage(BaseModel):
    """内部统一的消息格式"""
    role: Literal["user", "assistant", "system", "tool"]
    content: List[MessagePart]
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ChatOptions(BaseModel):
    """标准化聊天选项"""
    # 通用参数
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: bool = False
    
    # 标准化功能参数
    json_output: Optional[bool] = None
    reasoning: Optional[Union[str, bool]] = None  # "off", "low", "medium", "high", "minimal" or boolean
    
    # 提供商特定参数（透明处理）
    provider_specific: Dict[str, Any] = Field(default_factory=dict)
    
    # 旧版兼容
    tools: Optional[List[Dict[str, Any]]] = None  # 工具定义
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，过滤掉None值"""
        result = {}
        for key, value in self.model_dump().items():
            if value is not None:
                result[key] = value
        return result


class ProviderConfig(BaseModel):
    """提供商特定配置"""
    name: str
    api_key_env: str
    base_url: Optional[str] = None
    models: List[str]
    default_model: str
    features: Dict[str, Any] = Field(default_factory=dict)  # 功能支持配置
    defaults: Dict[str, Any] = Field(default_factory=dict)  # 默认参数值
    constraints: Dict[str, Any] = Field(default_factory=dict)  # 参数约束


def create_text_message(role: str, text: str, **kwargs) -> InternalMessage:
    """创建文本消息的便捷函数"""
    return InternalMessage(
        role=role,
        content=[MessagePart(type="text", content=text)],
        metadata=kwargs
    )


def convert_simple_messages(messages: List[Dict[str, str]]) -> List[InternalMessage]:
    """将简单的{role, content}格式消息转换为InternalMessage格式"""
    result = []
    for msg in messages:
        result.append(create_text_message(
            role=msg["role"],
            text=msg["content"]
        ))
    return result