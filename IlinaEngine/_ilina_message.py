# Ilina Message
from typing import Literal
from pydantic import BaseModel

class IlinaToolDefinition(BaseModel):
    """ 工具定义 """
    name: str  # 工具名称
    description: str  # 工具说明
    arguments: dict[str, object]  # 参数的 JSON Schema

class IlinaToolCall(BaseModel):
    """ 工具调用 """
    name: str = ''
    arguments: str = ''
    tool_call_id: str = ''

type IlinaMessageRoles = Literal['user', 'assistant', 'system', 'tool', 'error']

class IlinaMessage(BaseModel):
    """ 对话消息 """
    role: IlinaMessageRoles
    content: str = ''
    reasoning_content: str = ''  # 仅在 assistant 中使用
    tool_calls: list[IlinaToolCall] = []  # 仅在 assistant 中使用
    tool_call_id: str = ''  # 仅在 tool 中使用
    tool_name: str = ''  # 保存工具名，仅在 tool 中使用
    # tool_readable_content: str = ''  # 返回一个人类可读的消息，如果指定了这一项，那么渲染时建议用这个替换content
