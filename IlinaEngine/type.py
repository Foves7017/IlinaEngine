from ._ilina_message import IlinaMessage, IlinaToolCall, IlinaMessageRoles, IlinaToolDefinition
from .tree import Node

from enum import Enum
from dataclasses import dataclass, field

class NodeEventTypes(str, Enum):
    CREATED = 'CREATED'
    UPDATED = 'UPDATED'
    FINISNED = 'FINISHED'
    ERROR = 'ERROR'

@dataclass
class NodeEvent:
    """ 节点发生变化的事件 """
    node: Node
    _type: NodeEventTypes

@dataclass
class ToolInfo:
    """ 工具情况对象 """
    name: str  # MCP 名，如果是内置工具组就是 inside
    is_ignored: bool  # 是否被禁用
    tools: list[str]  # 所有工具名，无论工具是否被禁用，如果被禁用这里就是空
    disabled_tools: list[str] = field(default_factory=list)  # 被禁用了的工具名