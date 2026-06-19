# 自定义异常

from uuid import UUID

class NodeNotFoundError(Exception):
    """ 未找到指定 UUID 所对应的节点 """
    def __init__(self, uuid: UUID, *args: object) -> None:
        message = f'未找到 UUID 为 {uuid} 的节点'
        super().__init__(message, *args)
        self.message = message
    
    def __str__(self):
        return self.message

class ParentNotFoundError(Exception):
    """ 未找到指定 UUID 所对应的父节点 """
    def __init__(self, uuid: UUID, *args: object) -> None:
        message = f'未找到 UUID 为 {uuid} 的节点的父节点'
        super().__init__(message, *args)
        self.message = message
    
    def __str__(self):
        return self.message