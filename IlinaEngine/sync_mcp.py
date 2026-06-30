# sync_mcp.py
import json
import asyncio
import threading
import logging

from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai.types.chat import ChatCompletionFunctionToolParam
from openai.types.shared_params import FunctionDefinition
from FovesConfig import ConfigLoader

from .exceptions import MCPNotFoundError, ToolNotFoundError, ToolDisabledError
from .utils import ENGINE_CONFIG_PATH
from ._ilina_message import IlinaToolDefinition, IlinaToolCall
from ._config_models import EngineConfig
from FovesLog import LoggedTask

class SyncMcpClient:
    """
    同步 MCP 客户端 — 内部维护一个后台事件循环，对外暴露同步方法。
    可以直接嵌入同步的模型调用循环。
    """

    def __init__(self, name: str):
        self._loop: asyncio.AbstractEventLoop|None = None
        self._thread: threading.Thread|None = None
        self._session: ClientSession|None = None
        self._ready = threading.Event()
        self._error = threading.Event()
        self._ctx = None
        self.name = name
        self.log = logging.getLogger('MCP Client')
        logging.getLogger('mcp').setLevel(logging.DEBUG)

    # ── 连接 ──────────────────────────────────
    def connect(self, command: str, args: list[str], cwd: str, env: dict[str, str] = {}):
        """
        启动后台线程，连接 MCP Server。
        调用会阻塞直到握手完成。
        """

        async def _connect():
            env["PYTHONUNBUFFERED"] = "1" # 禁用 stdout 缓冲，确保 JSON-RPC 响应即时发送

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env,
                cwd=cwd
            )
            # 注意：不能用 async with，因为要跨调用保持连接
            self._ctx = stdio_client(server_params)
            read, write = await self._ctx.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
            self._ready.set()  # 通知主线程：好了

        # def _run_loop():
        #     self._loop = asyncio.new_event_loop()
        #     asyncio.set_event_loop(self._loop)
        #     self._loop.run_until_complete(_connect())
        #     # 连接完成后，事件循环继续跑，处理后续调用
        #     self._loop.run_forever()

        exc: Exception|None = None

        def _run_loop():
            nonlocal exc
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(_connect())
                self._loop.run_forever()

            except Exception as e:
                import traceback
                self.log.error(f"MCP启动失败: {repr(e)}\n{traceback.format_exc()}")
                self._error.set()
                exc = e
            finally:
                self._ready.set()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        # 从配置中读取 timeout
        timeout = ConfigLoader(ENGINE_CONFIG_PATH, EngineConfig).readonly().mcp_timeout
        if not self._ready.wait(timeout=timeout):
            self.log.error(f"MCP连接超时")
            raise TimeoutError("MCP连接超时")
        if self._error.is_set():
            self.log.error(f"MCP 初始化出错")
            self.log.error(f"{repr(exc)=}")
            if exc:
                raise exc
            else:
                raise RuntimeError('MCP 初始化出错')
    # ── 工具列表 ──────────────────────────────
    def list_tools(self) -> list[IlinaToolDefinition]:
        """同步获取工具列表"""
        async def _list():
            assert self._session is not None
            result = await self._session.list_tools()
            return [
                IlinaToolDefinition(
                    name=self.name + '_' + t.name,
                    description=t.description or '',
                    arguments=t.inputSchema
                ) for t in result.tools
            ]
        return self._run(_list())

    # ── 调用工具 ★ 你最常用的 ─────────────────
    def call_tool(self, name: str, arguments: dict) -> str:
        """
        同步调用 MCP 工具，返回文本结果。
        直接嵌入你的工具调用循环。
        """
        self.log.info(f'正在调用工具：{name}, args:\n{arguments}')
        # 去除 MCP 服务器名的前缀
        name = name[len(self.name) + 1:]
        async def _call():
            assert self._session is not None

            self.log.debug(f'调用工具')
            result = self._session.call_tool(name, arguments)
            self.log.debug(f'await 等待 result')
            result = await result
            # [2026/06/07] 无论如何都不要把上面的调用方式改成下面这种。会卡住。
            # result = await self._session.call_tool(name, arguments)
            self.log.debug(f'{result=}')

            # 优先结构化输出
            if result.structuredContent:
                return str(result.structuredContent)
            # 降级：拼接文本
            self.log.warning(f'降级了消息输出，使用拼接文本')
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text) # pyright: ignore[reportAttributeAccessIssue]
                
            self.log.debug(f'return={"\\n".join(parts) if parts else str(result.content)}')
            return "\n".join(parts) if parts else str(result.content)

        return self._run(_call())

    # ── 关闭 ──────────────────────────────────
    def close(self):
        """清理资源"""
        async def _close():
            if self._session:
                await self._session.__aexit__(None, None, None)
            if self._ctx:
                await self._ctx.__aexit__(None, None, None) # pyright: ignore[reportGeneralTypeIssues]

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)

    # ── 内部 ──────────────────────────────────
    def _run(self, coro):
        """把协程丢到后台事件循环里跑，阻塞等结果"""
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()  # 阻塞直到完成


class MCPLoader:
    ''' 负责管理和调用 MCP 工具 '''
    def __init__(self, workpath: Path):
        self.log = logging.getLogger(f'MCP Loader')
        self.log.setLevel(logging.INFO)
        # 保存警告消息的列表，应该在创建后被追加到engine的同名列表里
        self.warning_list: list[str] = []
        #  从配置中读取MCP工具
        self.clients: dict[str, SyncMcpClient] = {}
        self.disabled_tools: dict[str, list[str]] = {}
        config = ConfigLoader(ENGINE_CONFIG_PATH, EngineConfig).readonly()
        with LoggedTask('加载 MCP 服务', logger=self.log) as task:
            try:
                for mcp_name in config.mcps:
                    if mcp_name in config.mcp_ignored:
                        self.log.info(f'配置文件指定跳过了加载 {mcp_name}')
                        continue
                    try:
                        self.clients[mcp_name] = SyncMcpClient(mcp_name)
                        self.clients[mcp_name].connect(
                            command=config.mcps[mcp_name].command, 
                            args=config.mcps[mcp_name].args,
                            cwd=str(workpath),
                            env=config.mcps[mcp_name].env)
                        self.disabled_tools[mcp_name] = config.mcps[mcp_name].disabled_tools
                        task.checkpoint(f'已加载 {mcp_name}')
                    except Exception as e:
                        if mcp_name in self.clients:
                            del self.clients[mcp_name]
                        self.log.error(f'加载 MCP 服务 [{mcp_name}] 时出现错误: {repr(e)}, 已跳过加载')
                        self.warning_list.append(f'加载 MCP 服务 [{mcp_name}] 时出现错误: {repr(e)}, 已跳过加载')
            except TypeError:
                self.clients = {}
        
        log_string = '当前配置的 MCP 服务情况如下：\n'
        for mcp_name in self.clients:
            log_string += f'{mcp_name}:\n'
            for tool in self.clients[mcp_name].list_tools():
                log_string += f'  {tool.name}\n'
        self.log.debug(log_string)
    
    def get_list_openai(self) -> list[ChatCompletionFunctionToolParam]:
        """ 返回可以传给OpenAI模型调用的列表 """
        total: list[ChatCompletionFunctionToolParam] = []
        for client in self.clients.values():
            for tool in client.list_tools():
                if tool.name[len(client.name)+1:] in self.disabled_tools[client.name]:
                    continue
                total.append(ChatCompletionFunctionToolParam(
                    type='function',
                    function=FunctionDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.arguments,
                )))
        return total

    def call(self, call: IlinaToolCall) -> str:
        """ 调用MCP工具 """
        for client_name in self.clients:
            if call.name.startswith(client_name):
                if call.name[len(client_name)+1:] in self.disabled_tools[client_name]:
                    raise ToolDisabledError(call.name)
                return self.clients[client_name].call_tool(call.name, json.loads(call.arguments))
        raise ToolNotFoundError(call.name)
    
    def list_tools(self, mcp_name: str) -> list[str]:
        """ 列出某个 MCP 的所有工具
        这里应该返回不带 MCP 前缀的工具名
        """
        try:
            return [tooldef.name[len(mcp_name)+1:] for tooldef in self.clients[mcp_name].list_tools()]
        except KeyError:
            raise MCPNotFoundError(mcp_name)
    
    def list_mcps(self) -> list[str]:
        """ 列出加载了的所有MCP的名字
        """
        return list(self.clients.keys())