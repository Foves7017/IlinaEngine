# 管理工具和技能。
import os
import re
import time
import json
import shutil
import inspect

from typing import Callable, get_type_hints
from pathlib import Path
from pydantic import create_model
from win10toast import ToastNotifier
from FovesConfig import ConfigLoader
from openai.types.chat import ChatCompletionFunctionToolParam
from openai.types.shared_params import FunctionDefinition

from .tree import Tree
from .type import IlinaToolDefinition, IlinaToolCall
from .utils import is_ignored
from .exceptions import ToolNotFoundError, IgnoredFile
from ._config_models import IlinaConfig, EngineConfig

USER_PROFILE_PATH = './configs/user_profile.json'

class InsideTools:
    """ 内置工具集合 """
    def __init__(self, tree: Tree) -> None:
        self.tree = tree
        self.toaser = ToastNotifier()

        self.tool_table: dict[str, IlinaToolDefinition] = {}
        
        self.add_tool(self.list_files)
        self.add_tool(self.read_file)
        self.add_tool(self.search_in_file)
        self.add_tool(self.search_in_dir)
        self.add_tool(self.replace_in_file)
        self.add_tool(self.write_to_file)
        self.add_tool(self.append_to_file)
        self.add_tool(self.get_datetime)
        self.add_tool(self.alert)
        self.add_tool(self.get_workspace_info)
        self.add_tool(self.get_user_profile)
        self.add_tool(self.add_user_profile)
        self.add_tool(self.delete_user_profile)
    
    def get_user_profile(self) -> str:
        """ 获取当前的用户印象 """
        try:
            total = '当前用户印象如下：\n'
            with open(USER_PROFILE_PATH, 'r', encoding='UTF8') as f:
                profile = json.load(f)
            for key in profile:
                total += f'  {key}: {profile[key]}\n'
            return total
        except Exception as e:
            return repr(e)
    
    def add_user_profile(self, key: str, value: str) -> str:
        """ 向当前用户印象中添加键值对，如果键已经存在，就修改键值对
        @param key (str): 键
        @param value (str): 值
        """
        try:
            with open(USER_PROFILE_PATH, 'r', encoding='UTF8') as f:
                profile = json.load(f)
        except FileNotFoundError:
            profile = {}
        except Exception as e:
            return repr(e)
        
        try:
            profile[key] = value

            with open(USER_PROFILE_PATH, 'w', encoding='UTF8') as f:
                json.dump(profile, f)
            
            return f'已更新：{key} = {value}'
        except Exception as e:
            return repr(e)
    
    def delete_user_profile(self, key: str) -> str:
        """ 删除用户印象中的键，删除成功会返回键的内容
        """ 
        try:
            with open(USER_PROFILE_PATH, 'r', encoding='UTF8') as f:
                profile = json.load(f)
        except FileNotFoundError:
            profile = {}
        except Exception as e:
            return repr(e)
        
        try:
            value = profile[key]
            del profile[key]

            with open(USER_PROFILE_PATH, 'w', encoding='UTF8') as f:
                json.dump(profile, f)
            
            return value
        except Exception as e:
            return repr(e)

    def get_datetime(self) -> str:
        """ 获取当前日期时间
        """
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

    def alert(self, text: str) -> str:
        """ 向用户发送一个弹窗通知，只在需要引起用户注意时或完成用户给你的任务时使用，日常对话中不要使用，但撒娇时可以使用。
        Args:
            text (str): 通知内容

        Returns:
            str: 发送成功
        """
        ret = self.toaser.show_toast(
            'ILINA',
            text,
            './configs/toast_icon.ico'
        )
        return f'发送成功, 弹窗返回 "{ret}"'

    def get_workspace_info(self) -> str:
        """ 获取工作区信息，包括路径、记忆、用户偏好等
        """
        total_info = f'工作路径：{str(self.tree.workpath)}\n\n'

        # 尝试加载工作区配置
        config_filename = self.tree.workpath / '.ilina' / '.ilinaconfig'
        if config_filename.exists():
            config = ConfigLoader(config_filename, IlinaConfig).readonly()

            total_info += f'工作区偏好：\n'
            total_info += f'1. open_after_finish 参数的倾向：' + ('True 不发送通知' if config.open_or_alarm else 'False 并发送通知') + '。编辑记忆文件不需要打开或发送通知。\n'
            total_info += '\n\n'

        # 尝试加载记忆
        memory_filename = self.tree.workpath / '.ilina' / 'ILINA_记忆.md'
        if memory_filename.exists():
            with open(memory_filename, 'r', encoding='UTF8') as f:
                content = f.read()
            
            total_info += f'记忆内容：\n{content}'
            total_info += f'需要在任务完成后修改 `.ilina/ILINA_记忆.md`\n\n'
        else:
            total_info += f'该工作区暂不存在记忆，需要在任务完成后创建到 `.ilina/ILINA_记忆.md`\n\n'
        
        return total_info

    def list_files(self, path: str='.') -> str:
        """ 列出文件夹的内容，可以指定相对路径
        @param path (str): 文件夹路径，相对于工作目录，默认为 '.'
        """
        content = f'{path} 的内容:\n'
        for name in os.listdir(self.tree.workpath / path):
            fullpath = self.tree.workpath / path / name

            try:
                self._check_ignore(fullpath)
            except IgnoredFile:
                continue

            if os.path.isfile(fullpath):
                content += '  文件：'
            else:
                content += '  文件夹：'
            content += name
            content += '\n'
        return content
    
    def read_file(self, filename: str, encoding: str='UTF8', start_chara: int|None=None, end_chara: int|None=None) -> str:
        """ 读取文件
        @param filename (str): 文件路径，相对于工作目录
        @param encoding (str): 文件编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        @param start_chara (int|None): 从第几个字符开始读取，默认为 None，表示从文件开头开始
        @param end_chara (int|None): 读取到第几个字符结束，默认为 None，表示读取到文件末尾

        针对 start_chara 和 end_chara 的说明：这两个参数会直接传递给 Python 的切片，具体为：f.read()[start_chara:end_chara]
        你也许可以利用这些特性。
        """
        try:
            filepath = self.tree.workpath / filename
            self._check_ignore(filepath)
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()[start_chara:end_chara]
        except Exception as e:
            return repr(e)
    
    def search_in_file(self, filename: str, pattern: str, encoding: str='UTF8') -> str:
        """ 在文件中正则匹配搜索，如果没有匹配到会返回空字符串。
        @param filename (str): 文件名，需要是相对于工作目录的相对路径
        @param pattern (str): 正则表达式
        @param encoding (str): 文件编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        """
        try:
            filepath = self.tree.workpath / filename
            self._check_ignore(filepath)
            ret = ''
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
                for m in re.finditer(pattern, content):
                    ret += f'在字符{m.start()}-{m.end()}处匹配到：{m.group()}\n'
            return ret
        except Exception as e:
            return repr(e)

    def search_in_dir(self, pattern: str, path: str='.', encoding: str='UTF8') -> str:
        """ 在文件夹中正则匹配搜索
        @param pattern (str): 正则表达式
        @param path (str): 文件夹路径，相对于工作目录，默认为 '.'
        @param encoding (str): 打开文件使用的编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        """
        total = ''
        for file in os.listdir(self.tree.workpath / path):
            filename = self.tree.workpath/path/file

            try:
                self._check_ignore(filename)
            except IgnoredFile:
                continue
            
            if filename.is_file():
                res = self.search_in_file(str(filename), pattern, encoding)
                if res:
                    total += f'{file} 中的搜索结果：\n{res}\n\n'
        return total

    def replace_in_file(self, pattern: str, repl: str, filename: str, encoding: str='UTF8', count: int=0, open_after_finish: bool=False) -> str:
        """ 在文件中正则替换
        @param pattern (str): 正则表达式
        @param repl (str): 替换内容
        @param filename (str): 文件名，需要是相对于工作目录的相对路径
        @param encoding (str): 文件编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        @param count (int): 替换次数，默认为 0，表示替换所有匹配项
        @param open_after_finish (bool): 替换完成后是否打开文件，默认为 False
        """
        try:
            filepath = self.tree.workpath / filename
            self._check_ignore(filepath)
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
            content = re.sub(pattern, repl, content, count)
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            if open_after_finish:
                os.startfile(filepath)
            return '替换完成'
        except Exception as e:
            return repr(e)
    
    def write_to_file(self, filename: str, content: str, encoding: str='UTF8', open_after_finish: bool=False) -> str:
        """ 写入文件，会创建新文件或覆盖磁盘上原有的文件，会自动创建文件夹
        @param filename (str): 文件名，需要是相对于工作目录的相对路径
        @param content (str): 写入内容
        @param encoding (str): 文件编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        @param open_after_finish (bool): 写入完成后是否打开文件，默认为 False
        """
        try:
            filepath = self.tree.workpath / filename
            self._check_ignore(filepath)
            filepath.parent.mkdir(exist_ok=True)
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            if open_after_finish:
                os.startfile(filepath)
            return '写入完成'
        except Exception as e:
            return repr(e)
    
    def append_to_file(self, filename: str, content: str, encoding: str='UTF8', open_after_finish: bool=False) -> str:
        """ 追加文件，会追加到现有文件的末尾
        @param filename (str): 文件名，需要是相对于工作目录的相对路径
        @param content (str): 写入内容
        @param encoding (str): 文件编码，默认为 'UTF8'，可以是 Python 支持的任何编码
        @param open_after_finish (bool): 写入完成后是否打开文件，默认为 False
        """
        try:
            filepath = self.tree.workpath / filename
            self._check_ignore(filepath)
            with open(filename, 'a', encoding=encoding) as f:
                f.write(content)
            if open_after_finish:
                os.startfile(filename)
            return '写入完成'
        except Exception as e:
            return repr(e)
    
    def add_tool(self, tool: Callable):
        self.tool_table[tool.__name__] = self._func_to_def(tool)

    def get_list_openai(self) -> list[ChatCompletionFunctionToolParam]:
        """ 返回可以传给OpenAI模型调用的列表 """
        total: list[ChatCompletionFunctionToolParam] = []
        for tool in self.tool_table.values():
            total.append(ChatCompletionFunctionToolParam(
                type='function',
                function=FunctionDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.arguments,
            )))
        return total
    

    def __contains__(self, item: str):
        return isinstance(item, str) and item in self.tool_table

    def call(self, tool_call: IlinaToolCall) -> str:
        if tool_call.name in self:
            func: Callable = getattr(self, tool_call.name)
            return func(**json.loads(tool_call.arguments))
        else:
            raise ToolNotFoundError(tool_call.name)

    def _func_to_def(self, func: Callable, description: str|None = None) -> IlinaToolDefinition:
        """
        把一个 Python 函数封装为工具定义
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

        return IlinaToolDefinition(
            name=func.__name__,
            description=desc or "",
            arguments=params_schema
        )

    def _check_ignore(self, path: Path):
        ignores = [*ConfigLoader('./configs/engine.json', EngineConfig).readonly().global_ignores]
        config_filename = self.tree.workpath / '.ilina' / '.ilinaconfig'
        if config_filename.exists():
            ignores.extend(ConfigLoader(config_filename, IlinaConfig).readonly().ignores)
        if is_ignored(path, ignores):
            raise IgnoredFile(path)