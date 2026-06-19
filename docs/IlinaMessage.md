# IlinaMessage — 消息协议层

IlinaMessage 是 FovesCLI 对话系统的**统一消息协议**，基于 [Pydantic `BaseModel`](https://docs.pydantic.dev/)，负责在所有组件间传递、序列化与反序列化对话消息。

---

# 核心类

## 1. `IlinaMessage` — 对话消息

```python
class IlinaMessage(BaseModel):
    role: Literal['user', 'assistant', 'system', 'tool', 'error']
    content: str = ''
    reasoning_content: str = ''  # 仅 role='assistant' 时使用
    tool_calls: list[IlinaToolCall] = [] # 仅 role='assistant' 时使用
    tool_call_id: str = ''  # 仅 role='tool' 时使用
    tool_name: str = ''  # 保存工具名，仅在 tool 中使用
```

### 字段约定

| 字段                  | `user` | `assistant` | `system` | `tool`      | `error` |
| ------------------- | ------ | ----------- | -------- | ----------- | ------- |
| `content`           | ✅ 用户输入 | ✅ 助手文本回复    | ✅ 系统提示   | ✅ 工具返回结果    | ✅ 错误信息  |
| `reasoning_content` | —      | ✅ 思考链（可为空）  | —        | —           | —       |
| `tool_calls`        | —      | ✅ 工具调用列表    | —        | —           | —       |
| `tool_call_id`      | —      | —           | —        | ✅ 关联的工具调用ID | —       |
| `tool_name`         | —      | —           | —        | ✅ 关联的工具名称   | —       |

### role = `error`

> 这一种角色实际上并不是 AI 调用的东西，它是用来通知各位："这次 AI 调用发生错误了"的。

- `engine.invoke()` 中，当 API 请求抛出异常时，产生一个 `role='error'` 的节点
- `OpenAIClient.ilina_to_openai()` 将其过滤掉（返回 `None`），**不会**发送给 API
- engine 收到 `NodeEventTypes.ERROR` 后立刻 `yield` 然后 `return`，**不再继续本轮调用**

---

## 2. `IlinaToolCall` — 工具调用

```python
class IlinaToolCall(BaseModel):
    name: str = ''
    arguments: str = ''       # JSON 字符串，原封不动保存 AI 的输出
    tool_call_id: str = ''
```

- `arguments` 初始化为 `''`（空字符串），流式传输时逐步拼接。**绝对不能**初始化为 `'{}'`：OpenAI 流式返回的第一个 delta 本身就带 `{`，若初值是 `'{}'`，拼接结果会变成 `'{}{...}'`，`json.loads` 直接炸裂。
- 执行时由 `json.loads(call.arguments)` 反序列化为 `dict` 传给 MCP 工具
- 在 `call_openai.py` 的流式循环中通过 `tool_call.index` 定位并增量更新

---

## 3. `IlinaToolDefinition` — MCP 工具定义

```python
class IlinaToolDefinition(BaseModel):
    name: str                       # 工具名称（含 MCP 服务器名前缀）
    description: str                # 工具说明
    arguments: dict[str, object]    # 参数的 JSON Schema
```

---
# 流式构建语义

`IlinaMessage` 的所有字段都有**合理默认值**，这使得在 `OpenAIClient.chat()` 中可以安全地对空节点进行增量构建：

```python
assistant_node = Node(IlinaMessage(role='assistant'))
# content:           ''       → 逐步 += delta.content
# reasoning_content: ''       → 逐步 += delta.reasoning_content
# tool_calls:        []       → 按 index 定位并 append / 覆写
```

这也是为什么流式循环中累加空字符串也是安全的——字段永远有初值，不存在 `NoneType + str` 的风险。

---

# 序列化

树结构通过 `node_json_dump` / `node_json_load` 实现 JSON 持久化：

```python
# 序列化
IlinaMessage.model_dump()   →   dict

# 反序列化
IlinaMessage(**data)        →   IlinaMessage
```

节点本身不直接序列化，而是由 `tree.py` 中的 `node_json_dump()` 统一处理，将 `Node.message` 通过 `.model_dump()` 转换，加载时用 `IlinaMessage(**obj["message"])` 重建。

---

# 与 OpenAI 格式的转换

`OpenAIClient.ilina_to_openai()` 是协议边界，负责将 IlinaMessage 映射为 OpenAI SDK 原生类型：

| `IlinaMessage.role` | 映射目标 |
|---|---|
| `user` | `ChatCompletionUserMessageParam` |
| `assistant` | `ChatCompletionAssistantMessageParam`（含 `tool_calls` 转换） |
| `system` | `ChatCompletionSystemMessageParam` |
| `tool` | `ChatCompletionToolMessageParam`（含 `tool_call_id`） |
| `error` | **丢弃**（返回 `None`） |

---
