# 2026-03-27 完善 CLI 全流程测试脚本

## 决策意图
为了验证系统的鲁棒性，特别是在 Task 20（工具列表记录）完成后，需要一个自动化的脚本来覆盖所有核心工具（文件操作、Glob/Grep、Shell）和跨 Provider（Kimi, DeepSeek）的切换逻辑。由于原先的 `test_cli.py` 过于简单，本次开发将其重构为一个基于 JSON 模式的自动化“机器人”，模拟真实用户的完整会话路径。

## 关键变动
- **CLITestBot 类**: 封装了 `chat_cli_v2.py --json` 的启动、输入输出流读取和超时处理。
- **全流程覆盖**: 
  - Phase 1: 验证 `write_file`, `read_file`, `replace` 的原子性和正确性。
  - Phase 2: 验证 `/save` 和 `/load` 是否能正确持久化会话状态并恢复上下文。
  - Phase 3: 验证 `glob` 和 `grep_search` 在实际文件系统中的搜索能力。
  - Phase 4: 验证 `/tools` 命令切换工具组的能力，并测试 `run_shell_command`。
  - Phase 5: 验证跨 Provider 切换（DeepSeek）及对应的工具调用。
- **独立分析**: 脚本结束后会读取生成的 `session-*.json` 文件，验证 `metadata` 中是否包含 `enabled_tools`（Task 20 要求）以及所有工具调用的记录。

## 防御性记录
- **环境隔离**: 测试过程中使用了独立的 `myml` 环境，避免了本地依赖冲突（如 `openai` 缺失问题）。
- **非阻塞读取**: 使用多线程 `Queue` 读取 stdout，防止子进程缓冲区满导致主进程挂起。
- **超时保护**: 每个 Phase 设定了 120s 的超时阈值，防止模型进入无限重试循环时测试脚本卡死。

## 验证依据
- **自动化运行**: `D:\Software\anaconda\envs\myml\python.exe test/test_cli.py` 成功跑通所有核心逻辑。
- **JSON 校验**: 最终生成的 session 文件显示 `write_file: 1`, `replace: 1`, `read_file: 1`, `glob: 1`, `grep_search: 1`, `run_shell_command: 2`, `ls: 1`。
- **Metadata 验证**: User Message 均包含 `enabled_tools` 列表，证明调试元数据记录功能生效。
