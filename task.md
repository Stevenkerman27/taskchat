1. 支持聊天记录的保存和读取，添加实际功能以及GUI中的按钮(已完成)

保存时，将上一次清空context后的所有和agent交互原内容均保存为文本文档，存在contexts文件夹中(已创建),保存函数需允许设置文件名，GUI按按钮时默认文件名为当前日期时间。

读取时允许浏览聊天记录文件并选择。只读取context，并把读取的context覆盖当前的context。注意在agent思维链中途禁止保存和读取。

2. 完善并添加tools, 如ls可进入当前工作目录下的文件夹，添加移动文件，读取文件，修改文件等的tool。使agent可以自由的操作工作目录下的文件。(已完成)

3. 检查代码中潜在的bug和漏洞。从专业软件工程师的角度尝试优化代码结构，使代码更精简，更具有扩展性，更易修改，更易理解(已完成)

4. 我希望把代码变成CLI驱动的工具，即GUI只是指令拼接器，用户可以直接输入指令。目前的代码运行逻辑是怎么样的？这么修改是否可以让程序更有扩展性？(已完成)

5. 完善CLI-GUI,。我希望把GUI做成CLI的辅助输入器。在启动GUI时同步启动CLI界面，在GUI中点击按钮等同于在CLI中发送指令，这样用户可以使用按钮操作，高级用户可以直接在CLI中打命令。在开始修改前分析是否可行(已完成)

6. 修复工具调用模式下的状态管理bug。在GUI中发送工具结果后，如果发生错误或模型截断，不再出现“无反应”且按钮可以反复点击的问题。通过确保始终向界面发出响应消息并重置截断状态解决。(已完成)

7. bug修复。bug1, 使用GUI时有时会在显示reasoning content后显示CLI bridge disconnected, CLI中显示包含content的完整答案。bug2, 使用kimi模型时如果包括工具调用就会报错，显示"Assistant: 发送工具结果失败: OpenAI API调用失败: Error code: 400 - {'code': 20015, 'message': 'thinking is enabled but reasoning_content is missing in assistant tool call message at index 4', 'data': None}" 请分析原因并修复。请注意有的模型不支持enable_thinking选项，这可能只是意味着这些模型没法开关思维，并不是不具备思维链(已完成)

8. 添加attach系统指令的功能。将rules.md(如存在)中的内容作为系统指令加入context，而不是硬编码。如无rules.md就无系统指令(已完成)