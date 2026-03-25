import time
import threading
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.panel import Panel

# 初始化 rich Console
# 强制开启颜色渲染以生成 ANSI 码，限制颜色系统为 256 以获得最佳的跨平台和 prompt_toolkit 兼容性
console = Console(force_terminal=True, color_system="256")

def safe_print(renderable):
    """
    核心机制：
    1. 用 rich 的 capture 机制，拦截本来要打印到屏幕的内容。
    2. 获取带有底层 ANSI 转义码（类似 \x1b[31m）的原始字符串。
    3. 将原始字符串包装为 prompt_toolkit 认识的 ANSI 对象，由其统一输出。
    """
    with console.capture() as capture:
        console.print(renderable)
    
    # 获取捕获的文本。因为 rich 的 print 自带换行，所以用 end="" 防止输出空行
    ansi_text = capture.get()
    print_formatted_text(ANSI(ansi_text), end="")


def background_task():
    """模拟后台 Socket 接收数据或大模型推理输出"""
    counter = 1
    while True:
        time.sleep(3)
        
        # 测试 1: 普通带颜色的文本
        safe_print(f"[bold green]➜ 后台消息 {counter}：解析正常[/bold green]")
        
        # 测试 2: 复杂的 Rich 组件 (Panel)
        safe_print(Panel(
            f"这是复杂组件测试\n当前计数: {counter}", 
            title="System Event", 
            border_style="cyan"
        ))
        
        counter += 1


def main():
    print("测试开始（方案2：统一使用 prompt_toolkit 渲染管线）。")
    print("后台每 3 秒会打印带颜色的文本和面板。")
    print("请输入任意文字测试输入框是否会被干扰。输入 'exit' 退出。")
    print("-" * 50)
    
    session = PromptSession()
    
    # 启动后台输出线程
    bg_thread = threading.Thread(target=background_task, daemon=True)
    bg_thread.start()
    
    # 主线程输入循环
    while True:
        try:
            # 劫持 stdout，保护底部的输入提示符
            with patch_stdout():
                text = session.prompt("> ")
                
            if text.strip().lower() == 'exit':
                break
                
            safe_print(f"[yellow]你刚刚输入了: {text}[/yellow]")
            
        except KeyboardInterrupt:
            continue
        except EOFError:
            break

if __name__ == "__main__":
    main()