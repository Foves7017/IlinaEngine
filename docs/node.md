# Node
node 是对话树的节点，提供了一系列方法来操作树。
但**非常不建议**直接调用这些方法，更好的方式是通过 Engine 提供的操作来安全地操作树。
## Node 的属性

`Node.message: IlinaMessage`：存储[消息](IlinaMessage.md)
`Node.uuid: UUID`：存储节点的 UUID，用于区分节点
`Node.pointer: UUID|None`：存储这个节点当前的活动子节点是哪一个
`Node.children: list[Node]`：存储该节点的子节点
## 节点事件
```Python
@dataclass
class NodeEvent:
    """ 节点发生变化的事件 """
    node: Node
    _type: NodeEventTypes
```
Node 是所变化的节点，包括了更新后的属性，而 UUID 则保持始终不变。
`_type` 属性标志了本事件的类型，包括如下几种
```Python
class NodeEventTypes(str, Enum):
    CREATED = 'CREATED'  # 创建节点
    UPDATED = 'UPDATED'  # 节点消息发生变化
    FINISNED = 'FINISHED'  # 节点流式传输完毕
    ERROR = 'ERROR'  # 出现错误
```