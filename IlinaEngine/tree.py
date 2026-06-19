import os
import json
import copy
import time
import logging
from uuid import UUID, uuid4
from typing import TypedDict, Required, get_type_hints, Generator
from pathlib import Path
from pydantic import ValidationError
from FovesLog import LoggedTask
from FovesConfig import ConfigLoader

from .sysprompt import load_default_sysprompt
from ._ilina_message import IlinaMessage
from ._config_models import IlinaConfig

class Node:
    def __init__(self, 
                 message: IlinaMessage,
                 uuid: UUID|None = None,
                 pointer: UUID|None = None,
                 children: list["Node"]|None = None,
                 ):
        
        self.message: IlinaMessage = copy.deepcopy(message)
        self.uuid: UUID = uuid or uuid4()
        self.pointer: UUID|None = pointer or None
        self.children: list[Node] = copy.deepcopy(children) or []
    
    def _get_pointed_child(self) -> "Node|None":
        """ 返回指向的节点 """
        for child in self.children:
            if child.uuid == self.pointer:
                return child
        return None

    def _get_leaves(self) -> list["Node"]:
        """ 返回所有的叶子节点 """
        if len(self.children) == 0:
            return [self]
        else:
            leaves = []
            for child in self.children:
                leaves += child._get_leaves()
            return leaves

    def _insert(self, new_node: "Node", uuid: UUID) -> bool:
        """ 在 uuid 的节点新增一个子节点 new_node，会自动向下搜索。如果没有找到，就会返回 False"""
        if self.uuid == uuid:
            self.children.append(new_node)
            self.pointer = new_node.uuid
            return True
        else:
            for child in self.children:
                if child._insert(new_node, uuid):
                    return True
            return False
    
    def _set_pointer(self, uuid: UUID) -> bool:
        """ 设置指针到某个 UUID 的节点，会自动向下搜索。如果没有找到，就会返回 False，会自动设置整个链路的指针 """
        if self.uuid == uuid:
            return True
        else:
            for child in self.children:
                if child._set_pointer(uuid):
                    self.pointer = child.uuid
                    return True
            return False
    
    def _delete(self, uuid: UUID) -> bool:
        """ 删除某个 UUID 的节点，会自动向下搜索。如果没有找到，就会返回 False """
        length = len(self.children)
        self.children = list(filter(lambda child: child.uuid != uuid, self.children))
        # 移动指针
        if self.pointer not in self.children:
            if len(self.children) == 0:
                self.pointer = None
            else:
                self.pointer = self.children[0].uuid

        if len(self.children) < length:
            return True
        else:
            for child in self.children:
                if child._delete(uuid):
                    return True
            return False
        
    def _get_parent(self, uuid: UUID) -> UUID|None:
        """ 返回指定节点的父节点的 UUID，None 表示未找到 """
        for child in self.children:
            if child.uuid == uuid:
                return self.uuid
            else:
                result = child._get_parent(uuid)
                if result:
                    return result
    
    def _get_now(self) -> 'Node':
        """ 返回当前指向的最深的节点 """
        for child in self.children:
            if child.uuid == self.pointer:
                return child._get_now()
        return self
    
    def walk(self) -> Generator["Node", None, None]:
        yield self
        for child in self.children:
            yield from child.walk()

    def __hash__(self) -> int:
        return hash(self.uuid)
    
    def __eq__(self, value: object) -> bool:
        return (isinstance(value, Node) and self.uuid == value.uuid)

    def __str__(self) -> str:
        s = f'[{self.message.role}]: {self.message.content}\n'
        for child in self.children:
            if child.uuid == self.pointer:
                s += str(child)
        return s

    def __repr__(self) -> str:
        role = self.message.role
        content = self.message.content
        if isinstance(content, list):
            content = "[...]"
        preview = str(content)[:20].replace('\n', '\\n') + ("..." if len(str(content)) > 20 else "")
        result = f'Node [{role}] {preview}  ({str(self.uuid)})'
        if not self.children:
            return result
        for i, child in enumerate(self.children):
            is_last = (i == len(self.children) - 1)
            is_pointer = (child.uuid == self.pointer)
            branch = '└── ' if is_last else '├── '
            indent = '    ' if is_last else '│   '
            marker = '▶ ' if is_pointer else ''
            child_lines = repr(child).split('\n')
            result += '\n' + branch + marker + child_lines[0]
            for line in child_lines[1:]:
                result += '\n' + indent + line
        return result  
    
    def _to_message_list(self) -> tuple[list[UUID], list[IlinaMessage]]:
        """ 将现在的列表转化为可以传递给 AI 的消息列表 """
        uuids = [self.uuid]
        messages = [self.message]
        for child in self.children:
            if child.uuid == self.pointer:
                new_uuid, new_messages = child._to_message_list()
                uuids += new_uuid
                messages += new_messages
        return (uuids, messages)

    def _to_list(self) -> list['Node']:
        """ 获取当前所指向的节点链 """
        s: list[Node] = [self]
        for child in self.children:
            if child.uuid == self.pointer:
                s += child._to_list()
        return s

def node_json_dump(obj):
    if isinstance(obj, Node):
        return {
            "message": obj.message.model_dump(),
            "uuid": str(obj.uuid),
            "pointer": str(obj.pointer) if obj.pointer else None,
            "children": [node_json_dump(child) for child in obj.children],
        }
    else:
        return obj

def node_json_load(obj):
    if isinstance(obj, dict):
        if "message" in obj:
            return Node(
                message=IlinaMessage(**obj["message"]),  
                uuid=UUID(obj["uuid"]),
                pointer=UUID(obj["pointer"]) if obj["pointer"] else None,
                children=[node_json_load(child) for child in obj["children"]], # pyright: ignore[reportArgumentType]
            )
        else:
            return obj
    else:
        return obj

class SaveData(TypedDict):  # 这是保存的文件里面的内容
    create_time: Required[int|float]
    root_node: Required[Node]

class Tree:
    """ 对话树，会同步到文件 """
    def __init__(self, full_path: str|Path):  # 创建新的树，或者从文件加载树。
        self.log = logging.getLogger(f'对话树')
        self.log.setLevel(logging.INFO)
        if isinstance(full_path, str):
            full_path = Path(full_path)
        self._update_paths(full_path)
        self.uuid_to_node_table: dict[UUID, Node] = {}
        self._load()
    
    def _update_paths(self, new_path: Path): 
        """ 修改树中的各种路径 """
        self.full_path: Path = new_path
        self.workpath: Path = new_path.parent
        self.file_name: str = new_path.stem

    @property
    def name(self) -> str:
        return self.file_name

    @name.setter
    def name(self, value: str):
        new_path = self.full_path.with_stem(value)
        if self.full_path.is_file():
            self.full_path.rename(new_path)
        self._update_paths(new_path)
        self._save()
    
    @property
    def root_node(self) -> Node:
        return self.save_data["root_node"]

    def insert(self, new_node: "Node", uuid: UUID) -> bool:
        """ 会同步更新 UUID 到节点映射表的 insert
        不要直接调用根节点的 _insert
        """
        if self.root_node._insert(new_node, uuid):
            self.uuid_to_node_table[new_node.uuid] = new_node
            return True
        else:
            return False
    
    def delete(self, uuid: UUID) -> bool:
        """ 会同步更新 UUID 到节点映射表的删除
        不要直接调用根节点的 _delete
        如果没找到返回 False
        
        """
        if self.root_node._delete(uuid):
            del self.uuid_to_node_table[uuid]
            return True
        else:
            return False

    @property
    def now_node(self) -> Node:
        """ 获取当前指向的叶子节点 """
        return self.root_node._get_now()

    def set_pointer(self, uuid: UUID) -> bool:
        """ 设置pointer """
        return self.root_node._set_pointer(uuid)

    def _save(self) -> None:
        """ 将 save_data 同步到文件 """
        with LoggedTask('将树写入到文件', logger=self.log):
            os.makedirs(self.full_path.parent, exist_ok=True)
            with open(self.full_path, 'w', encoding='utf-8') as f:
                json.dump(self.save_data, f, default=node_json_dump, indent=4, ensure_ascii=False)
    
    def _get_default_save_data(self) -> SaveData:
        self._load_floder_config()
        config_name = self.full_path.parent / '.ilinaconfig'
        if config_name.exists() and config_name.is_file():
            config = ConfigLoader(config_name, IlinaConfig).readonly() # 只读
        else:
            config = IlinaConfig()
        return SaveData(  # 创建初始信息
                    create_time=time.time(),
                    root_node=Node(message=load_default_sysprompt(
                        replace_dict={
                            'workpath': str(self.workpath),
                            'open_or_alarm': '打开那个文件且不发送通知' if config.open_or_alarm else '不打开那个文件而是发送通知'
                        })))

    def _load(self) -> None:
        """ 从文件同步 save_data """
        with LoggedTask('从文件加载节点树', logger=self.log) as task:
            try:
                with open(self.full_path, 'r', encoding='utf-8') as f:
                    data: SaveData = json.load(f, object_hook=node_json_load)
                    if data == {}:
                        self.save_data: SaveData = self._get_default_save_data()
                        self._save()
                        return
            except FileNotFoundError:  # 如果文件不存在，就用现有信息保存
                self.save_data: SaveData = self._get_default_save_data()
                self._save()
                return
            except json.JSONDecodeError:
                with open(self.full_path, 'r', encoding='utf-8') as f:
                    if f.read().strip() == '':
                        self.save_data: SaveData = self._get_default_save_data()
                        self._save()
                        return
                raise ValueError(f'文件 "{self.full_path}" 的格式错误：不是有效的 JSON')
            except ValidationError:
                raise ValueError(f'文件 "{self.full_path}" 的格式错误：不是有效的 JSON')
            task.checkpoint(f'读取完成')
            
            # 进行格式检查
            hints = get_type_hints(SaveData)
            for key in hints.keys():
                try:
                    if not isinstance(data[key], hints[key]):
                        raise ValueError(f'文件"{self.full_path}"的格式错误："{key}" 的类型应为 "{hints[key]}", 却找到了 "{type(data[key])}"')
                except KeyError:
                    raise ValueError(f'文件"{self.full_path}"的格式错误：缺少键 "{key}"')
            self.save_data = data
            task.checkpoint(f'格式检查完成')

            # 产生节点映射表
            for node in self.root_node.walk():
                self.uuid_to_node_table[node.uuid] = node
            task.checkpoint(f'节点映射表编写完成')

            self._load_floder_config()
    
    def _load_floder_config(self):
        with LoggedTask('查找并加载工作区配置', logger=self.log) as task:
            config_name = self.full_path.parent / '.ilinaconfig'
            if config_name.exists() and config_name.is_file():
                with ConfigLoader(config_name, IlinaConfig) as config:
                    if config.workpath:
                        self.workpath = Path(config.workpath)
                        self.log.info(f'将工作目录更新为：{self.workpath}')
            else:
                self.log.info(f'工作区配置未找到')
    
    def __enter__(self) -> "Tree":
        self._load()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self.log.debug(f'预备保存的对话树：\n{repr(self.save_data["root_node"])}')
        self._save()