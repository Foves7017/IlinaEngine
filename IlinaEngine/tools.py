# 管理工具和技能。
import json
import inspect
from pydantic import create_model
from typing import Callable, get_type_hints
from ._ilina_message import IlinaMessage

def func_to_openai_tool(func, description: str|None = None):
    """
    把一个 Python 函数直接变成 OpenAI tools 列表中的一项。

    OpenAI tools 格式:
    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",
            "parameters": { ... JSON Schema ... }
        }
    }
    """
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    # 工具描述：显式传入 > docstring 第一段
    desc = description
    if desc is None and func.__doc__:
        desc = func.__doc__.split("\n\n")[0].strip()

    # 构建参数字段
    fields = {}
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        py_type = hints.get(name, str)
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[name] = (py_type, default)

    Model = create_model(f"{func.__name__}_params", **fields)
    params_schema = Model.model_json_schema()

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": desc or "",
            "parameters": params_schema,
        }
    }

class Toolset:
    def __init__(self):
        self.tool_functions: dict[str, Callable] = {}  # 键是工具名称，值是工具函数。
        self.tool_explains: dict[str, dict] = {}  # 键是工具名称，值是工具说明。
    
    def to_toollist(self) -> list[dict]:
        return list(self.tool_explains.values())
    
    def add_tool(self, func: Callable):
        tool_name = func.__name__
        self.tool_functions[tool_name] = func
        self.tool_explains[tool_name] = func_to_openai_tool(func)
    
    def call_tool(self, tools: list[list[str]]) -> list[IlinaMessage]:
        results = []
        for tool in tools:
            name, param, call_id = tool
            func = self.tool_functions[name]
            param_dict = json.loads(param)
            result = func(**param_dict)
            results.append(IlinaMessage(role='tool', content=result, tool_call_id=call_id))
        return results