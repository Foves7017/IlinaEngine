# 负责处理系统提示相关的内容
import os
from FovesConfig import ConfigLoader
from ._config_models import AIConfig
from ._ilina_message import IlinaMessage

def load_default_sysprompt(replace_dict: dict[str, str]) -> IlinaMessage:
    """ 警告：尽量减少向系统提示里放置的东西。 """
    with ConfigLoader('./configs/ai.json', AIConfig) as config:
        if os.path.exists(config.default_system_prompt_template):
            with open(config.default_system_prompt_template, 'r', encoding='utf-8') as f:
                prompt = f.read()
        else:
            prompt = config.default_system_prompt_template
    
    for key in replace_dict:
        prompt = prompt.replace('{{'+ key +'}}', replace_dict[key])

    return IlinaMessage(role='system', content=prompt)