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
import pathspec


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

def ls(path: str = ".", ignore: List[str] = None, respect_git_ignore: bool = True) -> str:
    """
    列出指定目录下的文件和文件夹
    
    Args:
        path: 目录路径（相对路径），默认为当前目录
        ignore: 要忽略的 Glob 模式列表
        respect_git_ignore: 是否尊重 .gitignore 规则，默认为 true
        
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
        
        # 准备过滤规则
        patterns = []
        if respect_git_ignore:
            gitignore_path = os.path.join(current_dir, '.gitignore')
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
        
        if ignore:
            patterns.extend([p.strip() for p in ignore if p.strip()])
        
        # 默认忽略 .git 目录
        if not any(p.strip() == '.git/' or p.strip() == '.git' for p in patterns):
            patterns.append('.git/')
            
        spec = pathspec.PathSpec.from_lines('gitwildmatch', patterns) if patterns else None
        
        # 列出目录内容
        files = os.listdir(target_path)
        
        # 获取文件信息
        file_details = []
        for file in files:
            file_path_full = os.path.join(target_path, file)
            rel_path = os.path.relpath(file_path_full, current_dir)
            
            # 处理目录的斜杠以匹配 pathspec
            match_path = rel_path.replace(os.sep, '/')
            if os.path.isdir(file_path_full) and not match_path.endswith('/'):
                match_path += '/'
            
            # 过滤
            if spec and spec.match_file(match_path):
                continue
                
            try:
                stat = os.stat(file_path_full)
                file_details.append({
                    "name": file,
                    "size": stat.st_size,
                    "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "is_dir": os.path.isdir(file_path_full),
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
            "count": len(file_details),
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


def read_file(file_path: str, offset: int = 0, limit: Optional[int] = None) -> str:
    """
    读取指定文件的文本内容
    
    Args:
        file_path: 文件路径（相对路径）
        offset: 开始行号 (0-indexed)
        limit: 读取的最大行数
        
    Returns:
        JSON字符串格式的文件内容
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        abs_filepath = os.path.abspath(os.path.join(current_dir, file_path))
        
        # 检查路径是否在当前工作目录内
        if not abs_filepath.startswith(current_dir):
            return json.dumps({
                "error": f"文件路径超出允许范围: {file_path}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查文件是否存在
        if not os.path.exists(abs_filepath):
            return json.dumps({
                "error": f"文件不存在: {file_path}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查是否为文件
        if not os.path.isfile(abs_filepath):
            return json.dumps({
                "error": f"路径不是文件: {file_path}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查文件大小（限制读取大文件）
        file_size = os.path.getsize(abs_filepath)
        MAX_FILE_SIZE = 1024 * 1024  # 1MB限制
        
        if file_size > MAX_FILE_SIZE and offset == 0 and limit is None:
            return json.dumps({
                "error": f"文件过大: {file_size}字节 > {MAX_FILE_SIZE}字节限制。请使用 offset 和 limit 分块读取。",
                "filepath": file_path,
                "file_size": file_size,
                "max_allowed": MAX_FILE_SIZE,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 读取文件内容
        with open(abs_filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        start = max(0, offset)
        end = total_lines
        if limit is not None:
            end = min(total_lines, start + limit)
        
        content = "".join(lines[start:end])
        
        # 获取文件信息
        stat = os.stat(abs_filepath)
        
        result = {
            "file_path": file_path,
            "absolute_path": abs_filepath,
            "content": content,
            "size": file_size,
            "encoding": "utf-8",
            "total_lines": total_lines,
            "offset": start,
            "limit": limit,
            "read_lines": len(content.splitlines()),
            "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except UnicodeDecodeError:
        return json.dumps({
            "error": f"文件不是UTF-8文本格式: {file_path}",
            "filepath": file_path,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return json.dumps({
            "error": f"读取文件失败: {str(e)}",
            "filepath": file_path,
            "timestamp": datetime.datetime.now().isoformat()
        })


def write_file(file_path: str, content: str) -> str:
    """
    写入或修改文件内容
    
    Args:
        file_path: 文件路径（相对路径）
        content: 要写入的内容
        
    Returns:
        JSON字符串格式的操作结果
    """
    try:
        # 安全验证：确保路径在当前工作目录内
        current_dir = os.path.abspath('.')
        abs_filepath = os.path.abspath(os.path.join(current_dir, file_path))
        
        # 检查路径是否在当前工作目录内
        if not abs_filepath.startswith(current_dir):
            return json.dumps({
                "error": f"文件路径超出允许范围: {file_path}",
                "allowed_directory": current_dir,
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查是否为目录（如果路径已存在）
        if os.path.exists(abs_filepath) and os.path.isdir(abs_filepath):
            return json.dumps({
                "error": f"路径是目录，不是文件: {file_path}",
                "timestamp": datetime.datetime.now().isoformat()
            })
        
        # 检查父目录是否存在
        parent_dir = os.path.dirname(abs_filepath)
        if not os.path.exists(parent_dir):
            # 自动创建父目录
            os.makedirs(parent_dir, exist_ok=True)
        
        # 写入文件内容
        with open(abs_filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 获取文件信息
        file_size = len(content.encode('utf-8'))
        
        # 检查文件是否为新创建
        file_existed = os.path.exists(abs_filepath)
        
        result = {
            "operation": "write",
            "file_path": file_path,
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
            "filepath": file_path,
            "timestamp": datetime.datetime.now().isoformat()
        })

def replace(file_path: str, old_string: str, new_string: str, allow_multiple: bool = False, instruction: str = None) -> str:
    """
    替换文件中的文本。默认要求 old_string 唯一，除非 allow_multiple 为 true。
    
    Args:
        file_path: 文件路径 (相对路径)
        old_string: 要查找并替换的精确字符串
        new_string: 要替换为的新字符串
        allow_multiple: 是否允许替换多个匹配项，默认为 false
        instruction: 对此次修改的简要描述 (可选)
        
    Returns:
        JSON字符串格式的操作结果
    """
    try:
        # 安全验证
        current_dir = os.path.abspath('.')
        abs_path = os.path.abspath(os.path.join(current_dir, file_path))
        
        if not abs_path.startswith(current_dir):
            return json.dumps({"error": f"访问越界: {file_path}"})
            
        if not os.path.exists(abs_path):
            return json.dumps({"error": f"文件不存在: {file_path}"})
            
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        count = content.count(old_string)
        if count == 0:
            return json.dumps({"error": f"未找到指定的 old_string", "file_path": file_path})
        if count > 1 and not allow_multiple:
            return json.dumps({"error": f"在文件中找到 {count} 处匹配，请提供更多上下文以确保唯一性，或设置 allow_multiple=True", "file_path": file_path})
            
        new_content = content.replace(old_string, new_string)
        
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return json.dumps({
            "success": True,
            "file_path": file_path,
            "replacements": count,
            "instruction": instruction,
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return json.dumps({"error": str(e), "file_path": file_path})

def glob_tool(pattern: str, path: str = ".", case_sensitive: bool = False, respect_git_ignore: bool = True) -> str:
    """
    根据 glob 模式查找工作区中的文件。
    """
    try:
        import pathlib
        
        current_dir = os.path.abspath('.')
        search_dir = os.path.abspath(os.path.join(current_dir, path))
        
        if not search_dir.startswith(current_dir):
            return json.dumps({"error": f"访问路径超出允许范围: {path}"})
            
        if not os.path.exists(search_dir):
            return json.dumps({"error": f"搜索目录不存在: {path}"})

        # 构建 gitignore 过滤
        spec = None
        if respect_git_ignore:
            gitignore_path = os.path.join(current_dir, '.gitignore')
            patterns = ['.git/']
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
            import pathspec
            spec = pathspec.PathSpec.from_lines('gitwildmatch', patterns)

        base_path = pathlib.Path(search_dir)
        matched_files = []
        
        try:
            paths = list(base_path.glob(pattern))
        except Exception as e:
            return json.dumps({"error": f"Glob matching error: {str(e)}"})

        for p in paths:
            if not p.is_file():
                continue
                
            try:
                rel_to_current = os.path.relpath(p, current_dir).replace('\\', '/')
            except ValueError:
                continue
                
            if spec and spec.match_file(rel_to_current):
                continue
                
            matched_files.append(p)

        # 按修改时间排序，最新的在前
        matched_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not matched_files:
            return f'Found 0 file(s) matching "{pattern}" within {path}'
            
        file_list_str = "\n".join(os.path.relpath(p, current_dir).replace('\\', '/') for p in matched_files)
        return f'Found {len(matched_files)} file(s) matching "{pattern}" within {path}, sorted by modification time (newest first):\n{file_list_str}'
        
    except Exception as e:
        return json.dumps({"error": str(e)})

def grep_search(pattern: str, path: str = ".", include: str = None) -> str:
    """
    在指定目录的文件中搜索正则表达式模式。
    """
    try:
        import re
        import pathlib
        
        current_dir = os.path.abspath('.')
        search_dir = os.path.abspath(os.path.join(current_dir, path))
        
        if not search_dir.startswith(current_dir):
            return json.dumps({"error": f"访问路径超出允许范围: {path}"})
            
        if not os.path.exists(search_dir):
            return json.dumps({"error": f"搜索目录不存在: {path}"})

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return json.dumps({"error": f"无效的正则表达式: {pattern}, 错误: {str(e)}"})

        # 构建 gitignore 过滤
        gitignore_path = os.path.join(current_dir, '.gitignore')
        ignore_patterns = ['.git/', 'node_modules/', '__pycache__/', '*.pyc']
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                ignore_patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
        import pathspec
        spec = pathspec.PathSpec.from_lines('gitwildmatch', ignore_patterns)

        base_path = pathlib.Path(search_dir)
        
        # 收集文件
        files_to_search = []
        if include:
            paths_iter = base_path.glob(include) if '/' in include else base_path.rglob(include)
        else:
            paths_iter = base_path.rglob('*')
            
        for p in paths_iter:
            if not p.is_file():
                continue
            
            try:
                rel_to_current = os.path.relpath(p, current_dir).replace('\\', '/')
            except ValueError:
                continue
                
            if spec.match_file(rel_to_current):
                continue
                
            files_to_search.append(p)

        matches = {}
        total_matches = 0
        
        for p in files_to_search:
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            rel_path = os.path.relpath(p, current_dir).replace('\\', '/')
                            if rel_path not in matches:
                                matches[rel_path] = []
                            matches[rel_path].append((i, line.rstrip('\n\r')))
                            total_matches += 1
            except UnicodeDecodeError:
                continue # 忽略二进制或非 UTF-8 文件
            except Exception:
                continue

        filter_str = f' (filter: "{include}")' if include else ''
        if total_matches == 0:
            return f'Found 0 matches for pattern "{pattern}" in path "{path}"{filter_str}'
            
        # 格式化输出
        output = []
        output.append(f'Found {total_matches} matches for pattern "{pattern}" in path "{path}"{filter_str}:')
        
        for file_path, lines in matches.items():
            output.append('---')
            output.append(f'File: {file_path}')
            for line_num, line_content in lines:
                output.append(f'L{line_num}: {line_content}')
        output.append('---')
        
        return '\n'.join(output)
        
    except Exception as e:
        return json.dumps({"error": str(e)})

def run_shell_command(command: str, description: str = None, dir_path: str = ".", is_background: bool = False) -> str:
    """
    在当前系统的 shell 中执行给定的命令。
    Windows 系统将使用 powershell.exe -NoProfile -Command 执行。
    
    Args:
        command: 要执行的确切命令
        description: 对用户的简短描述 (可选)
        dir_path: 命令执行的工作目录，默认为当前目录
        is_background: 是否作为后台进程运行
        
    Returns:
        包含标准输出、标准错误和退出码等信息的 JSON 字符串
    """
    try:
        current_dir = os.path.abspath('.')
        exec_dir = os.path.abspath(os.path.join(current_dir, dir_path))
        
        if not exec_dir.startswith(current_dir):
            return json.dumps({"error": f"执行目录越界: {dir_path}"})
            
        if not os.path.exists(exec_dir):
            return json.dumps({"error": f"执行目录不存在: {dir_path}"})

        env = os.environ.copy()
        env['GEMINI_CLI'] = '1'

        if os.name == 'nt':
            cmd_wrapper = ["powershell.exe", "-NoProfile", "-Command", command]
        else:
            cmd_wrapper = ["bash", "-c", command]

        if is_background:
            if os.name == 'nt':
                process = subprocess.Popen(
                    cmd_wrapper, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    cwd=exec_dir, 
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                process = subprocess.Popen(
                    cmd_wrapper, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    cwd=exec_dir, 
                    env=env,
                    preexec_fn=os.setpgrp
                )
            return json.dumps({
                "Command": command,
                "Directory": exec_dir,
                "Stdout": "(background process started)",
                "Stderr": "",
                "Background PIDs": [process.pid],
                "timestamp": datetime.datetime.now().isoformat()
            }, ensure_ascii=False)
            
        else:
            result = subprocess.run(
                cmd_wrapper, 
                capture_output=True, 
                text=True, 
                timeout=120, 
                cwd=exec_dir, 
                env=env,
                encoding='utf-8',
                errors='replace',
                stdin=subprocess.DEVNULL
            )

            stdout = result.stdout
            if len(stdout) > 10000:
                stdout = stdout[:2000] + "\n...[truncated]...\n" + stdout[-8000:]
                
            stderr = result.stderr
            if len(stderr) > 10000:
                stderr = stderr[:2000] + "\n...[truncated]...\n" + stderr[-8000:]
                
            return json.dumps({
                "Command": command,
                "Directory": exec_dir,
                "Stdout": stdout,
                "Stderr": stderr,
                "Exit Code": result.returncode,
                "timestamp": datetime.datetime.now().isoformat()
            }, ensure_ascii=False)
            
    except subprocess.TimeoutExpired as e:
        return json.dumps({
            "Command": command,
            "Error": f"Command timed out after {e.timeout}s",
            "timestamp": datetime.datetime.now().isoformat()
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "Command": command,
            "Error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }, ensure_ascii=False)

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


def get_time() -> str:
    """获取当前日期 and 时间 (别名)"""
    return get_current_time()

# 注册工具函数（在模块加载时自动执行）
_tool_registry.register("ls", ls)
_tool_registry.register("get_current_time", get_current_time)
_tool_registry.register("get_time", get_time)
_tool_registry.register("ping", ping)
_tool_registry.register("move_file", move_file)
_tool_registry.register("read_file", read_file)
_tool_registry.register("write_file", write_file)
_tool_registry.register("replace", replace)
_tool_registry.register("glob", glob_tool)
_tool_registry.register("grep_search", grep_search)
_tool_registry.register("run_shell_command", run_shell_command)


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
            "default_tools": ["ls", "get_current_time", "ping"]
        }

if __name__ == "__main__":
    # 测试重构后的工具系统
    print("=== 重构后的工具实现测试 ===")
    
    # 测试工具注册表
    print("\n1. 测试工具注册表:")
    print(f"已注册工具: {_tool_registry.list_tools()}")
    
    # 测试ls
    print("\n2. 测试ls:")
    result = execute_tool("ls", {})
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
    result = execute_tool("ls", {"wrong_param": "test"})
    print(result)
    
    # 测试未知工具
    print("\n6. 测试未知工具:")
    result = execute_tool("unknown_tool", {})
    print(result)
    
    # 测试新API函数
    print("\n7. 测试新API函数:")
    print(f"可用工具列表: {list_available_tools()}")
    
    print("\n=== 测试完成 ===")
