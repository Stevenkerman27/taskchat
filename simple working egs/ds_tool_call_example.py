"""
DeepSeek Tool Call 示例代码
演示如何使用DeepSeek的tool call功能
"""
import os
import json
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key=os.environ.get('DS_API_KEY'),
    base_url="https://api.deepseek.com"
)

def get_current_directory_files():
    """获取当前目录下的文件列表"""
    try:
        files = os.listdir('.')
        return json.dumps({"files": files, "count": len(files)})
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_weather(location: str):
    """模拟获取天气信息（示例工具）"""
    weather_data = {
        "Hangzhou, Zhejiang": "24℃, 晴朗",
        "Beijing": "18℃, 多云",
        "Shanghai": "22℃, 小雨",
        "Shenzhen": "28℃, 晴朗"
    }
    return json.dumps({
        "location": location,
        "weather": weather_data.get(location, "未知地区"),
        "temperature": "24℃" if location == "Hangzhou, Zhejiang" else "20℃"
    })

def calculate(expression: str):
    """计算器工具（示例）"""
    try:
        # 安全评估简单表达式
        allowed_chars = set('0123456789+-*/(). ')
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            return json.dumps({"expression": expression, "result": result})
        else:
            return json.dumps({"error": "表达式包含不安全字符"})
    except Exception as e:
        return json.dumps({"error": str(e)})

# 工具定义
tools = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出当前目录下的文件和文件夹",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名称，例如：Hangzhou, Zhejiang"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算数学表达式",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，例如：2+3*4"
                    }
                },
                "required": ["expression"]
            }
        }
    }
]

def send_messages(messages, tools=None):
    """发送消息到DeepSeek API"""
    kwargs = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False
    }
    
    if tools:
        kwargs["tools"] = tools
    
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message

def execute_tool_call(tool_call):
    """执行工具调用"""
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)
    
    if function_name == "list_directory":
        return get_current_directory_files()
    elif function_name == "get_weather":
        return get_weather(arguments.get("location", ""))
    elif function_name == "calculate":
        return calculate(arguments.get("expression", ""))
    else:
        return json.dumps({"error": f"未知工具: {function_name}"})

def run_tool_call_example():
    """运行tool call示例"""
    print("=== DeepSeek Tool Call 示例 ===")
    print("1. 列出当前目录")
    print("2. 计算表达式")
    print("3. 退出")
    
    while True:
        choice = input("\n请选择功能 (1-3): ").strip()
        
        if choice == "1":
            user_input = "列出当前目录下的文件"
        elif choice == "2":
            expr = input("请输入数学表达式: ").strip()
            user_input = f"计算 {expr}"
        elif choice == "3":
            print("退出示例程序")
            break
        else:
            print("无效选择")
            continue
        
        # 初始化消息
        messages = [{"role": "user", "content": user_input}]
        
        # 第一轮：发送用户消息
        print(f"\n用户: {user_input}")
        message = send_messages(messages, tools)
        
        # 检查是否有工具调用
        if hasattr(message, 'tool_calls') and message.tool_calls:
            print(f"模型决定调用工具: {len(message.tool_calls)}个")
            
            # 处理每个工具调用
            for tool_call in message.tool_calls:
                print(f"  调用工具: {tool_call.function.name}")
                print(f"  参数: {tool_call.function.arguments}")
                
                # 执行工具
                tool_result = execute_tool_call(tool_call)
                print(f"  工具结果: {tool_result}")
                
                # 添加工具调用消息
                messages.append(message)
                # 添加工具结果消息
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result
                })
            
            # 第二轮：发送工具结果给模型
            print("\n发送工具结果给模型...")
            message = send_messages(messages, tools)
            
            if hasattr(message, 'content') and message.content:
                print(f"模型回复: {message.content}")
        else:
            # 没有工具调用，直接显示回复
            if hasattr(message, 'content') and message.content:
                print(f"模型回复: {message.content}")

def run_single_example():
    """运行单个示例"""
    print("=== 单个工具调用示例 ===")
    
    # 示例1：列出目录
    print("\n示例1: 列出当前目录")
    messages = [{"role": "user", "content": "列出当前目录下的文件"}]
    message = send_messages(messages, tools)
    
    if hasattr(message, 'tool_calls') and message.tool_calls:
        tool_call = message.tool_calls[0]
        print(f"工具调用: {tool_call.function.name}")
        result = execute_tool_call(tool_call)
        print(f"工具结果: {result}")
        
        # 发送结果给模型
        messages.append(message)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result
        })
        
        final_message = send_messages(messages, tools)
        if hasattr(final_message, 'content') and final_message.content:
            print(f"最终回复: {final_message.content}")

if __name__ == "__main__":
    # 检查API密钥
    if not os.environ.get('DS_API_KEY'):
        print("错误: 请设置DS_API_KEY环境变量")
        print("示例: export DS_API_KEY='your-api-key'")
    else:
        # 运行单个示例
        run_single_example()
        
        # 询问是否运行交互式示例
        run_interactive = input("\n是否运行交互式示例? (y/n): ").strip().lower()
        if run_interactive == 'y':
            run_tool_call_example()