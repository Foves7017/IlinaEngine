# 调用 API

from enum import Enum
from typing import Generator
from logging import getLogger
from dataclasses import dataclass
from FovesConfig import ConfigLoader


# from tools import Toolset
from .tree import Node
from .sync_mcp import MCPLoader
from ._config_models import EngineConfig
from .tools import InsideTools
from .type import  NodeEvent, NodeEventTypes
from ._ilina_message import IlinaMessage, IlinaToolCall
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionUserMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionFunctionToolParam,
    ChatCompletionMessageParam,
    ChatCompletionChunk,
    ChatCompletion,
)

class OpenAIClient:
    def __init__(self, is_main_model: bool, mcp_loader: MCPLoader, inside_tools: InsideTools):
        with ConfigLoader('./configs/engine.json', EngineConfig) as config:
            if is_main_model:
                modelcfg = config.main_model
            else:
                modelcfg = config.sub_model

        self.client = OpenAI(base_url=modelcfg.base_url, api_key=modelcfg.api_key)
        self.model = modelcfg.model_name
        self.inside_tools = inside_tools
        self.mcp_loader = mcp_loader
        self.log = getLogger(f"Model_{self.model}")
    
    def ilina_to_openai(self, ilina: IlinaMessage) -> ChatCompletionMessageParam|None:
        """ 将 IlinaMessage 转化为  ChatCompletionMessageParam, 会过滤掉 error 类型"""
        if ilina.role == 'assistant':
            tool_calls = []
            for tool_call in ilina.tool_calls:
                tool_calls.append(ChatCompletionMessageFunctionToolCallParam(
                    type='function',
                    id=tool_call.tool_call_id,
                    function={
                        'name': tool_call.name,
                        'arguments': tool_call.arguments
                    }
                ))

            if len(tool_calls) > 0:
                return ChatCompletionAssistantMessageParam(
                    role='assistant',
                    content=ilina.content,
                    tool_calls=tool_calls
                )
            else:
                return ChatCompletionAssistantMessageParam(
                    role='assistant',
                    content=ilina.content,
                )
        
        elif ilina.role == 'user':
            return ChatCompletionUserMessageParam(
                role='user',
                content=ilina.content
            )
        
        elif ilina.role == 'system':
            return ChatCompletionSystemMessageParam(
                role='system',
                content=ilina.content
            )
        
        elif ilina.role == 'tool':
            return ChatCompletionToolMessageParam(
                role='tool',
                content=ilina.content,
                tool_call_id=ilina.tool_call_id
            )
        
        elif ilina.role == 'error':
            return None

    def get_tools(self) -> list[ChatCompletionFunctionToolParam]:
        """ 返回 MCP 工具和内置工具 """
        mcp_tools = self.mcp_loader.get_list_openai()
        inside_tools = self.inside_tools.get_list_openai()
        return inside_tools + mcp_tools

    def chat(self, messages: list[IlinaMessage]) -> Generator[NodeEvent, None, None]:
        """ 调用模型，会首先用生成器返回流失输出结果，最后return合并的Node """
        new_messages: list[IlinaMessage] = []  # 存储本轮调用生成的消息
        stop_reason: str = ''  # 存储停止原因
        self.log.info('开始调用模型')
        while stop_reason != 'stop':
            # 发起请求
            self.log.info('发起 API 请求')
            try:
                # 首先将 messages 转换成 openai 格式
                openai_messages = []
                for item in map(self.ilina_to_openai, messages + new_messages):
                    if item is not None:
                        openai_messages.append(item)

                # 发起调用
                res = self.client.chat.completions.create(
                    messages=openai_messages,
                    model=self.model,
                    tools=self.get_tools(),
                    stream=True
                ) 
            except Exception as e:
                yield NodeEvent(Node(IlinaMessage(role='error', content=f'{e}')), NodeEventTypes.ERROR)
                return
            
            assistant_node = Node(IlinaMessage(role='assistant'))
            # 传递节点开始事件
            yield NodeEvent(assistant_node, NodeEventTypes.CREATED)

            # 逐帧解析
            tool_call_nodes: dict[str, Node] = {}  # 保存工具 ID 对应的节点
            for chunk in res:
                chunk: ChatCompletionChunk
                delta = chunk.choices[0].delta

                # 保存流式信息
                if delta.content:
                    assistant_node.message.content += delta.content
                    yield NodeEvent(assistant_node, NodeEventTypes.UPDATED)

                # 保存思考信息                
                reasoning_content_delta = ''
                try:
                    self.log.debug(delta)
                    if hasattr(delta, 'reasoning_content'):  # Deepseek：用 reasoning_content 输出思考流
                        reasoning_content_delta = delta.reasoning_content or '' # pyright: ignore[reportAttributeAccessIssue]
                    elif hasattr(delta, 'reasoning'):  # Ollama: 用 reasoning 输出思考流
                        reasoning_content_delta = delta.reasoning or '' # pyright: ignore[reportAttributeAccessIssue]
                except AttributeError:  # 如果获取不到，也设置成空
                    reasoning_content_delta = ''
                    
                assistant_node.message.reasoning_content += reasoning_content_delta
                yield NodeEvent(assistant_node, NodeEventTypes.UPDATED)
                
                # 保存工具调用
                if delta.tool_calls:  # 如果工具调用不为 None
                    for tool_call in delta.tool_calls:  # 对于工具调用列表中的每个工具
                        try:  # 尝试直接追加到现有索引处
                            if tool_call.id:  # 覆写 ID
                                assistant_node.message.tool_calls[tool_call.index].tool_call_id = tool_call.id

                            if tool_call.function:  # 更新 function
                                if tool_call.function.name:  # 覆写 name
                                    assistant_node.message.tool_calls[tool_call.index].name = tool_call.function.name
                                    if tool_call.id:
                                        tool_call_nodes[tool_call.id].message.tool_name = tool_call.function.name
                                if tool_call.function.arguments:  # 追加 arguments
                                    assistant_node.message.tool_calls[tool_call.index].arguments += tool_call.function.arguments
                            
                            yield NodeEvent(assistant_node, NodeEventTypes.UPDATED)

                        except IndexError:  # 不存在则新增
                            assert tool_call.id is not None
                            assert tool_call.function is not None
                            assert tool_call.function.name is not None
                            assert tool_call.function.arguments is not None
                            assistant_node.message.tool_calls.append(IlinaToolCall(
                                tool_call_id=tool_call.id,
                                name=tool_call.function.name,
                                arguments=tool_call.function.arguments
                            ))
                            tool_call_node = Node(IlinaMessage(role='tool', tool_call_id=tool_call.id, tool_name=tool_call.function.name))
                            tool_call_nodes[tool_call.id] = tool_call_node
                            yield NodeEvent(tool_call_node, NodeEventTypes.CREATED)
                            yield NodeEvent(assistant_node, NodeEventTypes.UPDATED)

            # 更新停止原因
            if chunk.choices[0].finish_reason:
                stop_reason = chunk.choices[0].finish_reason
            self.log.info(f'停止原因：{stop_reason}')

            # 添加助手信息
            new_messages.append(assistant_node.message)
            yield NodeEvent(assistant_node, NodeEventTypes.FINISNED)

            # 调用并添加工具信息
            # 返回流式传输的工具块
            for call in assistant_node.message.tool_calls:
                self.log.info(f'调用工具 {call.name}')
                if call.name in self.inside_tools:
                    result = self.inside_tools.call(call)
                else:
                    result = self.mcp_loader.call(call)
                self.log.info(f'工具返回 {result}')
                # 根据 ID 获取对应的节点并进行修改和发送
                tool_call_node = tool_call_nodes[call.tool_call_id]
                tool_call_node.message.content = result
                # 向新消息列表中添加工具消息
                new_messages.append(tool_call_node.message)
                yield NodeEvent(tool_call_node, NodeEventTypes.UPDATED)
                yield NodeEvent(tool_call_node, NodeEventTypes.FINISNED)

            self.log.debug(f'当前的new_messages:\n{'\n'.join([str(m) for m in new_messages])}')

    def once(self, sysprompt: str, user_input: str) -> str|None:
        """ 进行一次调用 """ 
        res: ChatCompletion = self.client.chat.completions.create(
            messages=[
                {'role': 'system', 'content': sysprompt},
                {'role': 'user', 'content': user_input}
            ],
            model=self.model,
        )
        return res.choices[0].message.content