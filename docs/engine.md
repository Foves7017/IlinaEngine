# 当前引擎提供的所有接口
在本文档中，我们使用如下的对话树举例：
```text
System
└─▶	User
	└─▶ Assistant
	    ├── User A
	    │   └─▶ Assistant A
	    │
	    └▶ User B
	        └▶ Assistant B
```
## 初始化引擎
你可以通过如下的代码初始化对话引擎：
```Python
from IlinaEngine import Engine
engine = Engine('test.ilinatree')
```
引擎需要传入一个文件名，并且会实时将对话树保存到这个文件中。
`.ilinatree`本质上是一个 JSON 文件，但但为了便于识别和管理，我们建议使用 `.ilinatree` 作为扩展名。
## 属性
### 工作目录
`Engine.workpath: str`
会返回当前的工作目录。
### 文件名
`Engine.name: str`
`Engine.set_name(new_name: str)`
会返回当前的对话名，也就是文件名。如果修改这个值，会同步修改磁盘上的文件名。
`set_name` 函数是为了某些情况下不便于使用赋值语句而准备的，以下两种方式完全一样：
```Python
engine.name = 'new_name'
engine.set_name('new_name')
```
### 消息链
`Engine.message_list: tuple[list[UUID], list[IlinaMessage]]
会返回当前活跃的[消息](IlinaMessage.md)链，例如本例中会返回：
```
System
User
Assistant
User B
Assistant B
```
### 根节点
`Engine.readonly_root_node: Node`
会返回整个对话树的根节点，一般是系统[消息](IlinaMessage.md)。
注意：改变这个节点不会影响到磁盘上的对话树，并且所有更改会被丢弃。
### 叶子节点
`Engine.readonly_leaves: list[Node]`
会返回整个对话树的所有叶子节点。
注意：改变这些节点不会影响到磁盘上的对话树，并且所有更改会被丢弃。
### 获取最新节点的 UUID
`Engine.readonly_now_node：UUID`
获取当前[消息](IlinaMessage.md)链末尾的节点的 UUID，在本例中是 `Assistant B`
注意：改变它不会影响到磁盘上的对话树，并且所有更改会被丢弃。
## 方法
### 通过 UUID 获取消息内容
`Engine.get_message_by_uuid(self, uuid: UUID) -> IlinaMessage`
会返回给定 UUID 对应的[消息](IlinaMessage.md)内容
### 获取父节点
`Engine.get_parent(self, uuid: UUID) -> UUID`
获取某个节点的父节点。对于根节点和其他找不到父节点的节点会报错
### 修改节点（新建分支）
`Engine.edit_node(self, target: UUID, new_message: IlinaMessage) -> UUID`
修改节点内容，但不会实际修改，而是作为父节点的新子节点插入，会返回新节点的 UUID
在本例中，例如修改 `Assistant A` 的内容，会保留 `Assistant A` 分支的[消息](IlinaMessage.md)，并新建一个 `Assistant A1` 分支：
```text
System
└─▶	User
	└─▶ Assistant
	    ├── User A
	    │   ├── Assistant A
	    │   └─▶ Assistant A1
	    │
	    └▶ User B
	        └▶ Assistant B
```
### 调用主模型回复
`Engine.invoke(self, start_from: UUID|None=None) -> Generator[NodeEvent, bool, None]`
将当前的对话发送给主模型，并获取其回复，默认从最新分支开始，并会自动将新产生的节点添加到节点树中。
如果指定了 start_from，会从那里截断并插入节点。如果 start_from 不在当前分支，会首先切换过去，指定 start_from 实际上是实现了任意的 “从此处重新生成” 功能
只要遍历返回的生成器就可以获取流式传输的内容，这里我们使用了 `NodeEvent` 来统一[消息](IlinaMessage.md)格式，关于 `NodeEvent` 的更多信息请查看[这里](./node.md)。
如果要终止流式生成，可以向生成器发送 `True` 值来停止。但请注意，在 Python 中，`send()` 会造成一次迭代，为了避免丢失事件，请注意收集返回值。
### 发送消息
`Engine.send(self, message: IlinaMessage) -> UUID`
将[消息](IlinaMessage.md)插入到当前节点之后，会返回新节点的 UUID。
这对应着传统对话中的“发送”，通常用来追加用户[消息](IlinaMessage.md)，例如如果在本例中，send 一个 User 节点，会成为如下这样：
```text
System
└─▶	User
	└─▶ Assistant
	    ├── User A
	    │   └─▶ Assistant A
	    │
	    └▶ User B
	        └▶ Assistant B
				└▶ User C
```
### 移动指针
`Engine.move_to_node(self, uuid: UUID)`
将指针设置到指定 UUID 所在分支的末尾。
调用此方法可以实现在节点树不同分支的切换。
### 删除分支
`Engine.delete_node(self, uuid: UUID)`
删除指定节点。
注意：会连同该节点所具有的分支也一并删除，且没有确认，调用此函数时需要小心。
### 获取工具信息
`Engine.get_tool_info() -> list[ToolInfo]`
获取当前所有工具的详细信息，返回一个 [`ToolInfo`](type.md) 列表。每个 `ToolInfo` 包含：
- `name`：MCP 名称，如果是内置工具组则为 `"inside"`
- `is_ignored`：该 MCP 是否被禁用（未加载）
- `tools`：该 MCP 下的所有工具名列表（若 MCP 被禁用则为空）
- `disabled_tools`：该 MCP 下被单独禁用的工具名列表

此方法可用于检查当前有哪些 MCP 已加载、哪些工具处于可用状态。
### 设置 MCP 禁用状态
`Engine.mcp_set_disable(mcp_name: str, disable: bool)`
设置某个 MCP 是否禁用。`disable` 为 `True` 时禁用该 MCP，为 `False` 时启用。
注意：此方法只修改配置文件，需要调用 [`reload_mcp`](#重新加载-mcp-服务) 才能生效。
### 设置工具禁用状态
`Engine.tool_set_disable(mcp_name: str, tool_name: str, disable: bool)`
设置某个 MCP 下的特定工具是否禁用。`disable` 为 `True` 时禁用该工具，为 `False` 时启用。

如果要设置内置工具的禁用状态，`mcp_name` 应传入 `"inside"`。

注意：此方法只修改配置文件，需要调用 [`reload_mcp`](#重新加载-mcp-服务) 才能生效。如果修改的是内置工具，则此方法内部会立即重建内置工具组，无需额外调用 `reload_mcp`。
### 重新加载 MCP 服务
`Engine.reload_mcp()`
重新加载所有 MCP 服务和内部工具，并刷新主模型的工具列表。

通常在调用 [`mcp_set_disable`](#设置-mcp-禁用状态) 或 [`tool_set_disable`](#设置工具禁用状态) 后调用此方法，使配置变更生效。此方法会：
1. 重新构建内置工具组
2. 重新扫描并加载所有 MCP 服务
3. 将新的工具列表同步给主模型