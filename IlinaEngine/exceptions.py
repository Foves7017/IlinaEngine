# 自定义异常

from uuid import UUID
from pathlib import Path

class NodeNotFoundError(Exception):
    """未找到指定 UUID 所对应的节点"""

    def __init__(self, uuid: UUID):
        self.uuid = uuid
        super().__init__(f'未找到 UUID 为 {uuid} 的节点')

class ParentNotFoundError(Exception):
    """未找到指定 UUID 所对应节点的父节点"""

    def __init__(self, uuid: UUID):
        self.uuid = uuid
        super().__init__(f'未找到 UUID 为 {uuid} 的节点的父节点')

class ToolNotFoundError(Exception):
    """未找到指定的工具"""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f'未找到名为 {name} 的工具')

class IgnoredFile(Exception):
    """ 遇到了被忽略的文件 """
    
    def __init__(self, path: Path) -> None:
        super().__init__(f'文件 {path} 应该被忽略')