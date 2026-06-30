# 管理 Skills
import re
import yaml
import logging
from pathlib import Path
from .utils import app_dir
from typing import TypedDict
from FovesLog import LoggedTask

class MetaData(TypedDict):
    name: str
    description: str

class SkillLoader:
    def __init__(self, workpath: Path) -> None:
        self.workpath = workpath
        self.log = logging.getLogger('Skill Loader')
        self.metadatas: dict[Path, MetaData] = {}

        markdown_paths: list[Path] = []
        self.warning_list = []

        # 加载所有的skill
        self.log.debug(f'{app_dir()/'skills'} 的存在性：{(app_dir()/'skills').exists()}')
        if (app_dir()/'skills').exists():
            markdown_paths.extend((app_dir()/'skills').rglob('*.md'))
        self.log.debug(f'{workpath/'.ilina'/'skills'} 的存在性：{(workpath/'.ilina'/'skills').exists()}')
        if (self.workpath/'.ilina'/'skills').exists():
            markdown_paths.extend((self.workpath/'.ilina'/'skills').rglob('*.md'))
        self.log.debug(f'找到的所有markdown路径：{'\n'.join(str(path.absolute()) for path in markdown_paths)}')
        
        # 提取所有的属性信息
        with LoggedTask('加载 Skill', logger=self.log) as task:
            for markdown_path in markdown_paths:
                try:
                    with open(markdown_path, 'r', encoding='UTF8') as f:
                        metadata_str: str = re.findall(r'---([\s\S]*?)---', f.read())[0].strip()
                        metadata: MetaData = yaml.safe_load(metadata_str)
                        self.metadatas[markdown_path] = metadata
                    task.checkpoint(f'{metadata["name"]} 加载完成')
                except Exception as e:
                    self.log.error(f'加载 Skill [{markdown_path}] 时出现错误: {repr(e)}, 已跳过加载')
                    self.warning_list.append(f'加载 Skill [{markdown_path}] 时出现错误: {repr(e)}, 已跳过加载')

    def load_skill(self, name: str) -> str:
        """ 加载一个 Skill
        @param name (str): 要加载的 Skill 的名字
        """
        try:
            for path in self.metadatas:
                if self.metadatas[path]['name'] == name:
                    with open(path, 'r', encoding='UTF8') as f:
                        return f.read()
            return f'未找到名为 {name} 的Skill'
        except Exception as e:
            return repr(e)