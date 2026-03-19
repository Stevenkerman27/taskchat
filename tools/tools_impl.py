"""
重构后的工具实现模块
使用反射实现动态工具分发器
"""
import os
import json
import subprocess
import datetime
import inspect
from typing import Dict, Any, Optional, Callable, List
import socket
import time


class ToolRegistry:
    """
    工具注册表
    使用反射实现动态工具发现和调用
    """
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_signatures: Dict[str, inspect.Signature] = {}
    
    def register(self, name: str, func: Callable) -> None:
        """
        注册工具函数
        
        Args:
            name: 工具名称
            func: 工具函数
        """
        # 验证函数签名
        signature = inspect.signature(func)
        self.tools[name] = func
        self.tool_signatures[name] = signature
    
    def register_module(self, module) -> None:
        """
        注册模块中的所有工具函数
        
        Args:
            module: Python模块对象
        """
        for name, obj in inspect.getmembers(module):
            # 只注册函数，排除内置函数和私有函数
            if (inspect.isfunction(obj) and 
                not name.startswith('_') and 
                obj.__module__ == module.__name__):
                self.register(name, obj)
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """
        获取工具函数
        
        Args:
            name: 工具名称
            
        Returns:
            工具函数或None
        """
        return self.tools.get(name)
    
    def get_tool_signature(self, name: str) -> Optional[inspect.Signature]:
        """
        获取工具函数签名
        
        Args:
            name: 工具名称
            
        Returns:
            函数签名或None
        """
        return self.tool_signatures.get(name)
    
    def validate_arguments(self, name: str, arguments: Dict[str, Any]) -> bool:
        """
        验证参数是否符合函数签名
        
        Args:
            name: 工具名称
            arguments: 参数字典
            
        Returns:
            是否验证通过
        """
        if name not in self.tool_signatures:
            return False
        
        signature = self.tool_signatures[name]
        try:
            # 绑定参数以验证
            signature.bind(**arguments)
            return True
        except TypeError:
            return False
    
    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        执行工具函数
        
        Args:
            name: 工具名称
            arguments: 参数字典
            
        Returns:
            JSON字符串格式的工具结果
        """
        try:
            if name not in self.tools:
                return json.dumps({
                    "error": f"未知工具: {name}",
                    "available_tools": list(self.tools.keys()),
                    "timestamp": datetime.datetime.now().isoformat()
                })
            
            # 验证参数
            if not self.validate_arguments(name, arguments):
                # 尝试获取函数签名信息
                signature = self.tool_signatures[name]
                params = list(signature.parameters.keys())
                return json.dumps({
                    "error": f"参数验证失败",
                    "tool": name,
                    "expected_parameters": params,
                    "provided_arguments": list(arguments.keys()),
                    "timestamp": datetime.datetime.now().isoformat()
                })
            
            # 执行工具函数
            func = self.tools[name]
            result = func(**arguments)
            
            # 确保结果是JSON字符串
            if isinstance(result, str):
                # 尝试解析以确保是有效的JSON
                try:
                    json.loads(result)
                    return result
                except json.JSONDecodeError:
                    # 如果不是JSON，包装成JSON
                    return json.dumps({
                        "result": result,
                        "timestamp": datetime.datetime.now().isoformat()
                    })
            else:
                # 非字符串结果，转换为JSON
                return json.dumps({
                    "result": result,
                    "timestamp": datetime.datetime.now().isoformat()
                })
                
        except Exception as e:
            return json.dumps({
                "error": f"工具执行失败: {str(e)}",
                "tool": name,
                "arguments": arguments,
                "timestamp": datetime.datetime.now().isoformat()
            })
    
    def list_tools(self) -> List[str]:
        """
        列出所有已注册的工具
        
        Returns:
            工具名称列表
        """
        return list(self.tools.keys())


# 创建全局工具注册表实例
_tool_registry = ToolRegistry()

def list_directory(path: str = ".") -> str:
    """
    列出指定目录下的文件和文件夹
    
    Args:
        path: 目录路径（相对路径），默认为当前目录
        
    Returns:
        JSON字符串格式的文件列表
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        target_path = os.path.abspath(os.path.join(current_dir, path))
        
        # 检查路径是否在当前工作目录内
        if not target_path.startswith(current_dir):
            return json.dumps({
                "error": f"访问路径超出允许范围: {path}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查路径是否存在
        if not os.path.exists(target_path):
            return json.dumps({
                "error": f"路径不存在: {path}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查是否为目录
        if not os.path.isdir(target_path):
            return json.dumps({
                "error": f"路径不是目录: {path}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 列出目录内容
        files = os.listdir(target_path)
        
        # 获取文件信息
        file_details = []
        for file in files:
            file_path = os.path.join(target_path, file)
            try:
                stat = os.stat(file_path)
                file_details.append({
                    "name": file,
                    "size": stat.st_size,
                    "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_dir": os.path.isdir(file_path),
                    "permissions": oct(stat.st_mode)[-3:] if hasattr(stat, 'st_mode') else "unknown"
                })
            except Exception as e:
                file_details.append({
                    "name": file,
                    "error": str(e)
                })
        
        result = {
            "current_directory": current_dir,
            "target_directory": target_path,
            "relative_path": path,
            "files": file_details,
            "count": len(files),
            "timestamp": datetime.datetime.now().isoformat()
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "timestamp": datetime.datetime.now().isoformat()})

def get_current_time() -> str:
    """
    获取当前日期和时间
    
    Returns:
        JSON字符串格式的时间信息
    """
    now = datetime.datetime.now()
    result = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "datetime": now.isoformat(),
        "timestamp": now.timestamp(),
        "timezone": time.tzname[0] if time.daylight == 0 else time.tzname[1],
        "day_of_week": now.strftime("%A"),
        "week_number": now.isocalendar()[1]
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

def ping(host: str) -> str:
    """
    测试网络连接
    
    Args:
        host: 主机名或IP地址
        
    Returns:
        JSON字符串格式的ping结果
    """
    try:
        # 参数化ping命令（跨平台）
        param = '-n' if os.name == 'nt' else '-c'
        count = '2'  # 发送2个包
        
        # 构建命令
        command = ['ping', param, count, host]
        
        # 执行ping命令
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10  # 10秒超时
        )
        
        # 解析结果
        success = result.returncode == 0
        
        response = {
            "host": host,
            "success": success,
            "return_code": result.returncode,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        if success:
            # 提取响应时间（简单解析）
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'time=' in line.lower() or '时间=' in line:
                    response["response_time"] = line
                    break
            response["output"] = result.stdout[:500]  # 限制输出长度
        else:
            response["error"] = result.stderr or "Ping失败"
            response["output"] = result.stdout[:500]
        
        return json.dumps(response, ensure_ascii=False, indent=2)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "host": host,
            "error": "Ping超时",
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return json.dumps({
            "host": host,
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        })


def move_file(source: str, destination: str) -> str:
    """
    移动或重命名文件/目录
    
    Args:
        source: 源文件/目录路径（相对路径）
        destination: 目标文件/目录路径（相对路径）
        
    Returns:
        JSON字符串格式的操作结果
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        source_path = os.path.abspath(os.path.join(current_dir, source))
        dest_path = os.path.abspath(os.path.join(current_dir, destination))
        
        # 检查路径是否在当前工作目录内
        if not source_path.startswith(current_dir):
            return json.dumps({
                "error": f"源路径超出允许范围: {source}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        if not dest_path.startswith(current_dir):
            return json.dumps({
                "error": f"目标路径超出允许范围: {destination}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查源文件/目录是否存在
        if not os.path.exists(source_path):
            return json.dumps({
                "error": f"源文件/目录不存在: {source}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查目标路径是否已存在
        if os.path.exists(dest_path):
            return json.dumps({
                "error": f"目标路径已存在: {destination}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 执行移动/重命名操作
        os.rename(source_path, dest_path)
        
        result = {
            "operation": "move/rename",
            "source": source,
            "destination": destination,
            "source_path": source_path,
            "destination_path": dest_path,
            "success": True,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"移动文件失败: {str(e)}",
            "source": source,
            "destination": destination,
            "timestamp": datetime.datetime.now().isoformat()
        })


def read_file_content(filepath: str) -> str:
    """
    读取指定文件的文本内容
    
    Args:
        filepath: 文件路径（相对路径）
        
    Returns:
        JSON字符串格式的文件内容
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        abs_filepath = os.path.abspath(os.path.join(current_dir, filepath))
        
        # 检查路径是否在当前工作目录内
        if not abs_filepath.startswith(current_dir):
            return json.dumps({
                "error": f"文件路径超出允许范围: {filepath}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查文件是否存在
        if not os.path.exists(abs_filepath):
            return json.dumps({
                "error": f"文件不存在: {filepath}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查是否为文件
        if not os.path.isfile(abs_filepath):
            return json.dumps({
                "error": f"路径不是文件: {filepath}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查文件大小（限制读取大文件）
        file_size = os.path.getsize(abs_filepath)
        MAX_FILE_SIZE = 1024 * 1024  # 1MB限制
        
        if file_size > MAX_FILE_SIZE:
            return json.dumps({
                "error": f"文件过大: {file_size}字节 > {MAX_FILE_SIZE}字节限制",
                "filepath": filepath,
                "file_size": file_size,
                "max_allowed": MAX_FILE_SIZE,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 读取文件内容
        with open(abs_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 获取文件信息
        stat = os.stat(abs_filepath)
        
        result = {
            "filepath": filepath,
            "absolute_path": abs_filepath,
            "content": content,
            "size": file_size,
            "encoding": "utf-8",
            "lines": len(content.splitlines()),
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except UnicodeDecodeError:
        return json.dumps({
            "error": f"文件不是UTF-8文本格式: {filepath}",
            "filepath": filepath,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return json.dumps({
            "error": f"读取文件失败: {str(e)}",
            "filepath": filepath,
            "timestamp": datetime.datetime.now().isoformat()
        })


def write_file_content(filepath: str, content: str) -> str:
    """
    写入或修改文件内容
    
    Args:
        filepath: 文件路径（相对路径）
        content: 要写入的内容
        
    Returns:
        JSON字符串格式的操作结果
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        abs_filepath = os.path.abspath(os.path.join(current_dir, filepath))
        
        # 检查路径是否在当前工作目录内
        if not abs_filepath.startswith(current_dir):
            return json.dumps({
                "error": f"文件路径超出允许范围: {filepath}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查是否为目录（如果路径已存在）
        if os.path.exists(abs_filepath) and os.path.isdir(abs_filepath):
            return json.dumps({
                "error": f"路径是目录，不是文件: {filepath}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查父目录是否存在
        parent_dir = os.path.dirname(abs_filepath)
        if not os.path.exists(parent_dir):
            return json.dumps({
                "error": f"父目录不存在: {os.path.dirname(filepath)}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 写入文件内容
        with open(abs_filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 获取文件信息
        file_size = len(content.encode('utf-8'))
        
        # 检查文件是否为新创建
        file_existed = os.path.exists(abs_filepath)
        
        result = {
            "operation": "write",
            "filepath": filepath,
            "absolute_path": abs_filepath,
            "content_length": len(content),
            "size_bytes": file_size,
            "lines": len(content.splitlines()),
            "created": not file_existed,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"写入文件失败: {str(e)}",
            "filepath": filepath,
            "timestamp": datetime.datetime.now().isoformat()
        })

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    执行指定工具（重构版本，使用动态工具分发器）
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        
    Returns:
        JSON字符串格式的工具结果
    """
    return _tool_registry.execute(tool_name, arguments)


# 注册工具函数（在模块加载时自动执行）
_tool_registry.register("list_directory", list_directory)
_tool_registry.register("get_current_time", get_current_time)
_tool_registry.register("ping", ping)
_tool_registry.register("move_file", move_file)
_tool_registry.register("read_file_content", read_file_content)
_tool_registry.register("write_file_content", write_file_content)


def get_tool_registry() -> ToolRegistry:
    """
    获取全局工具注册表实例
    
    Returns:
        工具注册表实例
    """
    return _tool_registry


def register_custom_tool(name: str, func: Callable) -> None:
    """
    注册自定义工具函数
    
    Args:
        name: 工具名称
        func: 工具函数
    """
    _tool_registry.register(name, func)


def list_available_tools() -> List[str]:
    """
    列出所有可用的工具
    
    Returns:
        工具名称列表
    """
    return _tool_registry.list_tools()


def load_tools_config(config_path: str = "tools.yaml") -> Dict[str, Any]:
    """
    加载工具配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        工具配置字典
    """
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        # 返回默认配置
        return {
            "error": f"加载配置文件失败: {str(e)}",
            "default_tools": ["list_directory", "get_current_time", "ping"]
        }

if __name__ == "__main__":
    # 测试重构后的工具系统
    print("=== 重构后的工具实现测试 ===")
    
    # 测试工具注册表
    print("\n1. 测试工具注册表:")
    print(f"已注册工具: {_tool_registry.list_tools()}")
    
    # 测试list_directory
    print("\n2. 测试list_directory:")
    result = execute_tool("list_directory", {})
    print(result[:200] + "..." if len(result) > 200 else result)
    
    # 测试get_current_time
    print("\n3. 测试get_current_time:")
    result = execute_tool("get_current_time", {})
    print(result)
    
    # 测试ping
    print("\n4. 测试ping:")
    result = execute_tool("ping", {"host": "localhost"})
    print(result[:300] + "..." if len(result) > 300 else result)
    
    # 测试参数验证
    print("\n5. 测试参数验证:")
    result = execute_tool("list_directory", {"wrong_param": "test"})
    print(result)
    
    # 测试未知工具
    print("\n6. 测试未知工具:")
    result = execute_tool("unknown_tool", {})
    print(result)
    
    # 测试新API函数
    print("\n7. 测试新API函数:")
    print(f"可用工具列表: {list_available_tools()}")
    
    print("\n=== 测试完成 ===")
