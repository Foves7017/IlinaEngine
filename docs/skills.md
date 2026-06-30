# Skills — 技能系统

Skills 是 IlinaEngine 的可扩展技能模块，允许通过 Markdown 文件向 AI 注入专业提示词（类似 Custom GPT 的 Instructions）。每个 Skill 是一个独立的 `.md` 文件，加载后其完整内容会被注入到对话上下文中。

---

## Skill 文件结构

每个 Skill 文件是一个 Markdown 文件，**必须以 YAML front matter 开头**，用于声明元数据：

```markdown
---
name: my-skill
description: 一个示例 Skill，用于演示
---

# 这里是 Skill 的正文内容

可以包含任意的 Markdown 内容，包括：
- 指令
- 示例
- 代码块
- 表格

这些内容在加载后会被完整地提供给 AI。
```

### Front Matter 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | **必填。** Skill 的唯一标识名称，加载时通过此名称查找 |
| `description` | `str` | **必填。** Skill 的简要描述，会在 `get_workspace_info` 中展示给 AI |

---

## Skill 存放位置

Skill 文件可以从两个位置加载：

### 1. 全局 Skills 目录

路径为 `<IlinaEngine 数据目录>/skills/`，即 `app_dir()/'skills'`。

此处的 Skills 对所有工作区生效，适合存放通用技能。

### 2. 工作区 Skills 目录

路径为 `<工作区>/.ilina/skills/`，即 `workpath/'.ilina'/'skills'`。

此处的 Skills 仅对当前工作区生效，适合存放与特定项目相关的技能。

> **优先级**：两个位置的 Skills 都会被加载。如果存在同名 Skill，后加载的会覆盖先加载的（工作区 Skills 后于全局 Skills 加载）。

---

## 加载 Skill

### AI 工具调用

AI 可以通过调用 `load_skill` 工具来加载一个 Skill：

```
load_skill(name="my-skill")
```

- 参数 `name`：要加载的 Skill 的名称（对应 front matter 中的 `name`）
- 返回值：该 Skill 的完整 Markdown 内容
- 如果找不到指定名称的 Skill，返回 `未找到名为 xxx 的 Skill`

### 在 `get_workspace_info` 中展示

调用 `get_workspace_info` 时，返回的工作区信息末尾会包含所有可用 Skill 的列表：

```markdown
## 可用的 Skill
### my-skill
一个示例 Skill，用于演示

### another-skill
另一个 Skill 的描述
```

AI 可以据此获知当前有哪些 Skill 可用，并在需要时调用 `load_skill` 加载。

---

## 加载时机

Skill 在 `InsideTools` 初始化时（即引擎启动时）自动扫描并加载元数据：

1. 扫描全局 Skills 目录 (`app_dir()/'skills'`) 下的所有 `.md` 文件
2. 扫描工作区 Skills 目录 (`<workpath>/.ilina/skills/`) 下的所有 `.md` 文件
3. 解析每个文件的 YAML front matter，提取 `name` 和 `description`
4. 解析失败的 Skill 会被跳过，并记录到警告列表中

---

## 错误处理

如果某个 Skill 文件的 front matter 解析失败：
- 该 Skill 会被跳过，不会被加载
- 错误信息会记录在 `SkillLoader.warning_list` 中
- 可通过 `InsideTools._warning_list` 访问这些警告

---

## 与 MCP 的区别

| 特性 | Skills | MCP |
|------|--------|-----|
| 本质 | 静态提示词注入 | 动态工具调用 |
| 格式 | Markdown 文件 | Python/可执行程序 |
| 加载方式 | `load_skill` 工具 | MCP 协议自动加载 |
| 用途 | 注入领域知识、行为指令 | 提供外部工具能力 |
| 存放位置 | `skills/` 或 `.ilina/skills/` | 配置文件指定 |
