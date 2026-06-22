# 所有配置项

## 默认系统提示
键|值类型|默认值
---|---|---
`default_system_prompt_template`|str|`当前工作目录为 {{workpath}}，当你编辑文件之后，你应该{{open_or_alarm}}`

此处可以填写一段文本作为默认系统提示，也可以传入一个文件名。

系统首先会尝试读取文件内容作为系统提示，如果失败，就将字符串视作系统提示本身用来初始化对话树。

在系统提示中，支持一些关键词替换，当前支持的关键词可以在此处查询：
[系统提示词替换](./docs/system_prompt_replace.md)

## 主模型和副模型配置
### 模型配置的基本结构
键|值类型|默认值
---|---|---
`base_url`|str|`http://localhost:11434/v1/`
`api_key`|str|`sk-xxx`
`model_name`|str|`qwen3-vl:4b`
目前采用 OpenAI API 作为调用方式，`model_name` 为使用的模型名。
### 模型配置

需要指定两个模型，主模型 `main_model` 和辅助模型 `sub_model`。

主模型是进行回答和工作的模型，而辅助模型则进行总结、生成标题等工作。

建议辅助模型选用较便宜的模型或本地模型。

## MCP 配置
键|值类型|默认值
---|---|---
`mcps`|list|[]

这是一个列表，保存所有可用的 MCP 服务，列表项定义如下：

键|值类型|
--|------|
`command`|str
`args`|list[str]

目前只支持 stdio 方式调用 MCP。

mcp 配置示例如下：
```JSON
"mcps": {
    "FovesList": {
      "command": "D:/Find-A-Way-VII/FovesList/.venv/Scripts/pythonw.exe",
      "args": [
        "D:/Find-A-Way-VII/FovesList/mcp_stdio.py"
      ]
    },
    "IlinaMCP": {
      "command": "D:/Find-A-Way-VII/ILINA/MCP/.venv/Scripts/pythonw.exe",
      "args": [
        "D:/Find-A-Way-VII/ILINA/MCP/main.py"
      ]
    }
  }
```