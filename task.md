1. 支持聊天记录的保存和读取，添加实际功能以及GUI中的按钮(已完成)

保存时，将上一次清空context后的所有和agent交互原内容均保存为文本文档，存在contexts文件夹中(已创建),保存函数需允许设置文件名，GUI按按钮时默认文件名为当前日期时间。

读取时允许浏览聊天记录文件并选择。只读取context，并把读取的context覆盖当前的context。注意在agent思维链中途禁止保存和读取。

2. 完善并添加tools, 如ls可进入当前工作目录下的文件夹，添加移动文件，读取文件，修改文件等的tool。使agent可以自由的操作工作目录下的文件。(已完成)

3. 添加git tools, 允许agent add, commit, push等(未完成)

4. 新建skills.py，编写总结开发记录的功能。调用此功能时，使用chat_logic_v2.py中的函数，向零上下文的agent发送合适的prompt，如“阅读progress文件夹中所有开发进度记录文档，总结成一份high-level的文档。包括核心功能的加入，加入的理由，加入的方法，加入时改动的系统架构等” 总结完成后，将所有旧progress记录移入progress/archive文件夹,新的文档即成为未来开发的历史参考。(未完成)