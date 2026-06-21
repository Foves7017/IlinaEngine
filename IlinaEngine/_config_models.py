from pydantic import BaseModel

class IlinaConfig(BaseModel):
    """ 文件夹下的 .ilinaconfig 内的数据模型 """
    workpath: str|None = None
    open_or_alarm: bool = False  # 如果是 True 倾向于打开文件，如果是 False 倾向于发送通知
    ignores: list[str] = []

class MCPConfig(BaseModel):
    command: str
    args: list[str]

class ModelConfig(BaseModel):
    base_url: str
    api_key: str
    model_name: str

class EngineConfig(BaseModel):
    """ 模型配置 """
    main_model: ModelConfig = ModelConfig(
        base_url='http://localhost:11434/v1/', 
        api_key='sk-xxx', 
        model_name='qwen3-vl:4b'
    )

    sub_model: ModelConfig = ModelConfig(
        base_url='http://localhost:11434/v1/', 
        api_key='sk-xxx', 
        model_name='qwen3-vl:4b'
    )

    mcps: dict[str, MCPConfig] = {}
    default_system_prompt_template: str = '当前工作目录为 {{workpath}}，当你编辑文件之后，你应该{{open_or_alarm}}'
    global_ignores: list[str] = ['.venv', '*.ilinatree', '.git', '.obsidian']
    toast_icon_abs_path: str|None = None