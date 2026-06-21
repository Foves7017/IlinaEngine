from ._ilina_message import IlinaMessage, IlinaToolCall, IlinaMessageRoles, IlinaToolDefinition
from .tree import Node

from enum import Enum
from dataclasses import dataclass

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
