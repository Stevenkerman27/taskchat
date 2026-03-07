#!/usr/bin/env python
"""
演示动态工具分发器的使用
展示如何扩展工具系统而无需修改核心代码
"""
import json
import tools_impl


def demonstrate_basic_tools():
    """演示基本工具的使用"""
    print("=== 基本工具演示 ===")
    
    # 列出可用工具
    print(f"1. 可用工具: {tools_impl.list_available_tools()}")
    
    # 使用现有工具
    print("\n2. 使用现有工具:")
    
    # 列出目录
    result = tools_impl.execute_tool("list_directory", {})
    data = json.loads(result)
    print(f"   list_directory: 找到 {data.get('count', 0)} 个文件/目录")
    
    # 获取当前时间
    result = tools_impl.execute_tool("get_current_time", {})
    data = json.loads(result)
    print(f"   get_current_time: {data.get('date')} {data.get('time')}")
    
    # 计算表达式
    result = tools_impl.execute_tool("calculate", {"expression": "2+3*4"})
    data = json.loads(result)
    print(f"   calculate(2+3*4): {data.get('result')}")


def demonstrate_tool_registration():
    """演示工具注册功能"""
    print("\n=== 工具注册演示 ===")
    
    # 定义新工具
    def get_system_info() -> str:
        """获取系统信息"""
        import platform
        import sys
        
        info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "timestamp": "2026-03-07T13:00:00"
        }
        return json.dumps(info, ensure_ascii=False, indent=2)
    
    def format_text(text: str, style: str = "normal") -> str:
        """格式化文本"""
        styles = {
            "normal": text,
            "upper": text.upper(),
            "lower": text.lower(),
            "title": text.title(),
            "reverse": text[::-1]
        }
        
        result = {
            "original": text,
            "formatted": styles.get(style, text),
            "style": style,
            "length": len(text),
            "timestamp": "2026-03-07T13:00:00"
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    # 注册新工具
    print("1. 注册新工具...")
    tools_impl.register_custom_tool("get_system_info", get_system_info)
    tools_impl.register_custom_tool("format_text", format_text)
    
    print(f"2. 更新后的可用工具: {tools_impl.list_available_tools()}")
    
    # 使用新工具
    print("\n3. 使用新工具:")
    
    # 获取系统信息
    result = tools_impl.execute_tool("get_system_info", {})
    data = json.loads(result)
    print(f"   get_system_info: {data.get('system')} {data.get('release')}")
    
    # 格式化文本
    result = tools_impl.execute_tool("format_text", {
        "text": "Hello, Dynamic Tools!",
        "style": "upper"
    })
    data = json.loads(result)
    print(f"   format_text: {data.get('formatted')}")
    
    # 测试参数验证
    print("\n4. 测试参数验证:")
    result = tools_impl.execute_tool("format_text", {"wrong_param": "test"})
    data = json.loads(result)
    print(f"   错误参数: {data.get('error')}")
    print(f"   期望参数: {data.get('expected_parameters')}")


def demonstrate_reflection_features():
    """演示反射功能"""
    print("\n=== 反射功能演示 ===")
    
    # 获取工具注册表
    registry = tools_impl.get_tool_registry()
    
    print("1. 工具签名信息:")
    for tool_name in registry.list_tools():
        signature = registry.get_tool_signature(tool_name)
        if signature:
            params = list(signature.parameters.keys())
            print(f"   {tool_name}: {params}")
    
    print("\n2. 动态工具发现:")
    # 模拟动态模块加载
    import types
    
    # 创建动态模块
    dynamic_module = types.ModuleType("dynamic_tools")
    
    # 添加动态函数
    def dynamic_multiply(a: float, b: float) -> str:
        """动态乘法工具"""
        result = {
            "operation": "multiply",
            "a": a,
            "b": b,
            "result": a * b,
            "timestamp": "2026-03-07T13:00:00"
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    # 注册动态模块的函数
    registry.register("multiply", dynamic_multiply)
    
    print(f"   添加动态工具后的可用工具: {registry.list_tools()}")
    
    # 使用动态工具
    result = tools_impl.execute_tool("multiply", {"a": 5, "b": 7})
    data = json.loads(result)
    print(f"   multiply(5, 7): {data.get('result')}")


def demonstrate_backward_compatibility():
    """演示向后兼容性"""
    print("\n=== 向后兼容性演示 ===")
    
    print("1. 原有接口测试:")
    # 原有的 execute_tool 接口应该仍然工作
    result = tools_impl.execute_tool("calculate", {"expression": "10/2"})
    data = json.loads(result)
    print(f"   calculate(10/2): {data.get('result')}")
    
    print("\n2. 配置文件加载测试:")
    config = tools_impl.load_tools_config("tools.yaml")
    if "tools" in config:
        print(f"   从配置文件加载了 {len(config['tools'])} 个工具定义")
    
    print("\n3. 错误处理兼容性:")
    # 测试未知工具的错误处理
    result = tools_impl.execute_tool("non_existent_tool", {})
    data = json.loads(result)
    print(f"   未知工具错误: {data.get('error')}")
    print(f"   可用工具列表: {data.get('available_tools', [])}")


def main():
    """主函数"""
    print("动态工具分发器演示")
    print("=" * 50)
    
    demonstrate_basic_tools()
    demonstrate_tool_registration()
    demonstrate_reflection_features()
    demonstrate_backward_compatibility()
    
    print("\n" + "=" * 50)
    print("演示完成！")
    print(f"最终可用工具数量: {len(tools_impl.list_available_tools())}")
    print(f"工具列表: {tools_impl.list_available_tools()}")


if __name__ == "__main__":
    main()