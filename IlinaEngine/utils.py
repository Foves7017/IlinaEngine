from pathlib import Path
from fnmatch import fnmatch

def is_ignored(path: Path, ignore_list: list[str]) -> bool:
    """
    判断文件或目录是否应被忽略。
    支持：
        *.ilinatree
        .git
        __pycache__
        .venv
        build
        dist
    """

    # 当前节点和所有父目录
    names = [path.name]
    names.extend(parent.name for parent in path.parents)

    for pattern in ignore_list:
        pattern = pattern.strip()

        if not pattern:
            continue

        for name in names:
            if fnmatch(name, pattern):
                return True

    return False