# 引擎层
import logging
from uuid import UUID
from typing import Generator

from FovesLog import LoggedTask
from .tree import Tree, Node
from .call_openai import *
from ._ilina_message import IlinaMessage
from .exceptions import *
from .tools import InsideTools

class Engine:
    def __init__(self, filename: str) -> None:
        self.log = logging.getLogger('对话引擎')
        self.log.setLevel(logging.INFO)

        with LoggedTask('初始化', logger=self.log) as task:
            self.tree = Tree(filename)
            task.checkpoint(f'建立文件树')
            self.instde_tools = InsideTools(self.tree)
            task.checkpoint(f'建立内置工具组')
            self.mcp_loader = MCPLoader()
            task.checkpoint(f'建立MCP工具')
            self.main_model = OpenAIClient(True, self.mcp_loader, self.instde_tools)
    
    @property
    def workpath(self) -> str:
        """ 获取工作目录 """
        return str(self.tree.workpath)

    @property
    def name(self) -> str:
        """ 获取树的名字 """
        return self.tree.name
    
    @name.setter
    def name(self, value: str):
        self.tree.name = value
    
    def set_name(self, new_name: str):
        """ 设置名字的函数版本，适用于某些无法使用属性赋值的情况
        
        说的就是你, lambda 语句
        """
        self.name = new_name
    
    @property
    def message_list(self) -> tuple[list[UUID], list[IlinaMessage]]:
        """ 获取当前的消息链 """
        return self.tree.root_node._to_message_list()

    @property
    def readonly_root_node(self) -> Node:
        """ 获取根节点。注意：只应该用来获取树结构 """
        return self.tree.root_node

    @property
    def readonly_leaves(self) -> list[Node]:
        """ 获取所有叶子节点。注意：只应该用来获取树结构 """
        return self.tree.root_node._get_leaves()

    @property
    def readonly_now_node(self) -> UUID:
        """ 获取当前最新节点的 UUID """
        return self.tree.root_node._get_now().uuid

    def get_message_by_uuid(self, uuid: UUID) -> IlinaMessage:
        """ 通过 UUID 获取消息内容 """
        return self.tree.uuid_to_node_table[uuid].message

    def get_parent(self, uuid: UUID) -> UUID:
        """ 获取某个节点的父节点。对于根节点和其他找不到父节点的节点会报错 """
        parent = self.tree.root_node._get_parent(uuid)
        if parent:
            return parent
        else:
            raise ParentNotFoundError(uuid)

    def edit_node(self, target: UUID, new_message: IlinaMessage) -> UUID:
        """ 修改节点内容，不会实际修改，而是作为父节点的新子节点插入，会返回新节点的 UUID
            如果是修改系统节点，就直接修改
        """

        if target == self.tree.root_node.uuid:
            with self.tree as tree:
                tree.root_node.message = new_message
            return target
        else:
            new_node = Node(new_message)
            with self.tree as tree:
                tree.insert(new_node, self.get_parent(target))
            return new_node.uuid

    def invoke(self, start_from: UUID|None=None) -> Generator[NodeEvent, bool, None]:
        """ 将当前的对话发送给主模型，并获取其回复，默认从最新分支开始
            并会自动将 NodeFinished 事件的节点添加到节点树中
            如果指定了 start_from，会从那里截断并插入节点。
            如果 start_from 不在当前分支，会首先切换过去。
        """
        self.log.info(f'调用 AI')

        # 如果未指定 start_from，就设置到当前的末尾
        if start_from is None:
            start_from = self.readonly_now_node

        # 如果不在当前分支，就切换过去
        uuids, messages = self.message_list
        if start_from not in uuids:
            self.move_to_node(start_from)
            uuids, messages = self.message_list

        # 如果节点类型是 assistant，就获从其父节点出截断，否则从节点处截断
        if self.get_message_by_uuid(start_from).role == 'assistant':
            messages = messages[:uuids.index(start_from)]
            append_point_uuid = self.get_parent(start_from)
        else:
            messages = messages[:uuids.index(start_from) + 1]
            append_point_uuid = start_from

        # 调用并进行处理
        for event in self.main_model.chat(messages):
            stop: bool|None = yield event

            if event._type == NodeEventTypes.ERROR:
                stop = True
            elif event._type == NodeEventTypes.FINISNED:
                with self.tree as tree:
                    tree.insert(event.node, append_point_uuid)
                    append_point_uuid = event.node.uuid
            
            if stop:
                return
    
    def send(self, message: IlinaMessage) -> UUID:
        """ 将消息插入到当前节点之后，会返回新节点的 UUID """
        self.log.info(f'插入用户消息...')
        new_node = Node(message)
        with self.tree as tree:
            if not tree.insert(new_node, tree.now_node.uuid):
                raise NodeNotFoundError(tree.now_node.uuid)
        return new_node.uuid

    
    def move_to_node(self, uuid: UUID):
        """ 将指针设置到指定 UUID 所在分支的末尾 """
        self.log.info(f'移动指针到 {uuid}')
        with self.tree as tree:
            if not tree.set_pointer(uuid):
                raise NodeNotFoundError(uuid)

    
    def delete_node(self, uuid: UUID):
        """ 删除指定 UUID 的节点 """
        self.log.info(f'删除节点： {uuid}')
        with self.tree as root_node:
            if not root_node.delete(uuid):
                raise NodeNotFoundError(uuid)