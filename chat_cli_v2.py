import sys
import json
import argparse
import traceback
import socket
import threading
import queue
import shlex
from typing import Callable, Dict, List, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from chat_logic_v2 import ChatLogicV2

console = Console()

class CommandManager:
    def __init__(self):
        self.commands: Dict[str, Dict[str, Any]] = {}
        
    def cmd(self, name: str, aliases: List[str] = None, help_text: str = ""):
        def decorator(func: Callable):
            cmd_info = {"func": func, "help": help_text}
            self.commands[name] = cmd_info
            if aliases:
                for alias in aliases:
                    self.commands[alias] = cmd_info
            return func
        return decorator

    def dispatch(self, input_line: str, context: Any) -> bool:
        """
        Dispatches the command. Returns True if a command was handled, False otherwise.
        """
        if not input_line.startswith('/'):
            return False
            
        parts = shlex.split(input_line)
        if not parts:
            return False
            
        cmd_name = parts[0]
        args = parts[1:]
        
        if cmd_name in self.commands:
            try:
                self.commands[cmd_name]["func"](context, *args)
            except Exception as e:
                context.emit("error", {"message": f"Command execution error: {str(e)}\n{traceback.format_exc()}"})
            return True
        else:
            context.emit("error", {"message": f"Unknown command: {cmd_name}. Type /help for available commands."})
            return True
            
    def get_help_text(self) -> str:
        help_lines = ["Available Commands:"]
        seen = set()
        for name, info in self.commands.items():
            if info["func"] not in seen:
                help_lines.append(f"  {name.ljust(15)} - {info['help']}")
                seen.add(info["func"])
        return "\n".join(help_lines)

class ChatCLI:
    def __init__(self, json_mode=False, port=None):
        self.json_mode = json_mode
        self.port = port
        self.clients = []
        self.cmd_queue = queue.Queue()
        self.running = True
        self.is_multiline = False
        
        self.cmd_manager = CommandManager()
        self._register_commands()
        
        try:
            self.logic = ChatLogicV2()
        except Exception as e:
            self.emit("error", {"message": f"Initialization Error: {str(e)}"})
            sys.exit(1)
            
        if self.port:
            self.start_socket_server()

    def _register_commands(self):
        @self.cmd_manager.cmd("/help", help_text="Show this help message")
        def _help(cli, *args):
            if not cli.json_mode:
                console.print(cli.cmd_manager.get_help_text())
            else:
                cli.emit("sys", cli.cmd_manager.get_help_text())

        @self.cmd_manager.cmd("/exit", aliases=["/quit"], help_text="Exit the application")
        def _exit(cli, *args):
            sys.exit(0)

        @self.cmd_manager.cmd("/chat", help_text="Send a message to the assistant")
        def _chat(cli, *args):
            msg = " ".join(args)
            cli.do_chat(msg)

        @self.cmd_manager.cmd("/provider", help_text="Switch provider and optionally model")
        def _provider(cli, *args):
            available = cli.logic.get_available_providers()
            if not args:
                cli.emit("sys", "Available Providers:")
                for i, p in enumerate(available, 1):
                    status = "[ACTIVE]" if p['is_current'] else ""
                    cli.emit("sys", f"  {i}. {p['id']} ({p['name']}) {status}")
                    cli.emit("sys", f"     Models: {', '.join(p['models'])}")
                cli.emit("sys", "Use '/provider <name_or_index> [model]' to switch.")
                return

            provider_input = args[0]
            model = args[1] if len(args) > 1 else None
            
            if provider_input.isdigit():
                idx = int(provider_input) - 1
                if 0 <= idx < len(available):
                    provider_input = available[idx]['id']
                else:
                    cli.emit("error", {"message": f"Invalid provider index: {idx+1}"})
                    return

            try:
                cli.logic.set_provider(provider_input, model)
                cli.emit("sys", f"Switched to {provider_input} - {cli.logic.get_current_model()}")
                cli.emit_state()
            except Exception as e:
                cli.emit("error", {"message": str(e)})

        @self.cmd_manager.cmd("/option", help_text="Set a chat option (e.g. /option temperature 0.5)")
        def _option(cli, *args):
            current_options = cli.logic.get_current_options_dict()
            if not args:
                cli.emit("sys", "Current Chat Options:")
                for i, (k, v) in enumerate(current_options.items(), 1):
                    cli.emit("sys", f"  {i}. {k} = {v}")
                cli.emit("sys", "Use '/option <key_or_index> <value>' to set.")
                return

            if len(args) >= 2:
                key_input = args[0]
                val_str = args[1]
                
                if key_input.isdigit():
                    idx = int(key_input) - 1
                    keys = list(current_options.keys())
                    if 0 <= idx < len(keys):
                        key_input = keys[idx]
                    else:
                        cli.emit("error", {"message": f"Invalid option index: {idx+1}"})
                        return

                try:
                    if val_str.lower() == "true": val = True
                    elif val_str.lower() == "false": val = False
                    else:
                        try: val = int(val_str)
                        except ValueError:
                            try: val = float(val_str)
                            except ValueError: val = val_str
                    cli.logic.set_option(key_input, val)
                    cli.emit("sys", f"Set option {key_input} = {val}")
                    cli.emit_state()
                except Exception as e:
                    cli.emit("error", {"message": str(e)})
            else:
                cli.emit("sys", "Usage: /option <key_or_index> <value>")

        @self.cmd_manager.cmd("/tools", help_text="Enable tool groups (comma separated)")
        def _tools(cli, *args):
            tool_info = cli.logic.get_available_tool_groups()
            all_groups = list(tool_info['groups'].keys())
            
            if not args:
                cli.emit("sys", "Available Tool Groups:")
                for i, group_name in enumerate(all_groups, 1):
                    status = "[ACTIVE]" if group_name in tool_info['enabled'] else ""
                    tools = tool_info['groups'][group_name].get('tools', [])
                    desc = tool_info['groups'][group_name].get('description', '')
                    cli.emit("sys", f"  {i}. {group_name} ({desc}) {status}")
                    cli.emit("sys", f"     Tools: {', '.join(tools)}")
                cli.emit("sys", "Use '/tools <name_or_index1,index2...>' to enable.")
                return

            args_str = " ".join(args)
            inputs = [i.strip() for i in args_str.split(",") if i.strip()]
            final_groups = []
            for item in inputs:
                if item.isdigit():
                    idx = int(item) - 1
                    if 0 <= idx < len(all_groups):
                        final_groups.append(all_groups[idx])
                    else:
                        cli.emit("error", {"message": f"Invalid tool group index: {idx+1}"})
                else:
                    final_groups.append(item)
            
            cli.logic.set_enabled_tool_groups(final_groups)
            enabled_tools = cli.logic.get_enabled_tools()
            cli.emit("sys", f"Enabled tool groups updated. Active tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
            cli.emit_state()

        @self.cmd_manager.cmd("/execute", help_text="Execute pending tool calls")
        def _execute(cli, *args):
            cli.do_execute()

        @self.cmd_manager.cmd("/send_results", help_text="Send tool results back to the assistant")
        def _send_results(cli, *args):
            cli.do_send_results()

        @self.cmd_manager.cmd("/cancel_tools", help_text="Cancel pending tool calls")
        def _cancel_tools(cli, *args):
            cli.logic.cancel_tool_calls()
            cli.emit("sys", "Tool calls cancelled.")
            cli.emit_state()

        @self.cmd_manager.cmd("/new", aliases=["/clear"], help_text="Start a new blank session")
        def _new(cli, *args):
            cli.logic.clear_context()
            cli.emit("sys", "New session started.")
            cli.emit_state()

        @self.cmd_manager.cmd("/save", help_text="Save current chat to a file")
        def _save(cli, *args):
            if not args:
                cli.emit("error", {"message": "Usage: /save <filename>"})
                return
            filename = args[0]
            try:
                cli.logic.save_context_to_file(filename)
                cli.emit("sys", f"Chat saved to {filename}")
            except Exception as e:
                cli.emit("error", {"message": str(e)})

        @self.cmd_manager.cmd("/load", help_text="Load a chat from a file")
        def _load(cli, *args):
            if not args:
                cli.emit("error", {"message": "Usage: /load <filename>"})
                return
            filename = args[0]
            try:
                cli.logic.load_context_from_file(filename)
                cli.emit("sys", f"Chat loaded from {filename}")
                cli.emit_state()
            except Exception as e:
                cli.emit("error", {"message": str(e)})

        @self.cmd_manager.cmd("/state", help_text="Show current system state")
        def _state(cli, *args):
            cli.emit_state()
            if not cli.json_mode:
                state = cli._get_state_dict()
                console.print(f"State: {json.dumps(state, indent=2, ensure_ascii=False)}")
                
        @self.cmd_manager.cmd("/multiline", help_text="Toggle multiline input mode")
        def _multiline(cli, *args):
            cli.is_multiline = not cli.is_multiline
            status = "ON" if cli.is_multiline else "OFF"
            if not cli.json_mode:
                console.print(f"[bold magenta]Multiline mode {status}[/bold magenta]. (Press Esc+Enter to submit in multiline mode)")
            else:
                cli.emit("sys", f"Multiline mode {status}")

    def start_socket_server(self):
        """启动后台 Socket 服务器，供 GUI 连接"""
        def server_thread():
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server_socket.bind(('localhost', self.port))
                server_socket.listen(5)
            except Exception as e:
                print(f"[BRIDGE] Failed to bind port {self.port}: {e}")
                return

            while self.running:
                try:
                    server_socket.settimeout(1.0)
                    client_sock, addr = server_socket.accept()
                    self.clients.append(client_sock)
                    threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
            server_socket.close()

        threading.Thread(target=server_thread, daemon=True).start()

    def handle_client(self, client_sock):
        """处理来自 GUI 的连接"""
        try:
            with client_sock.makefile('r', encoding='utf-8') as f:
                while self.running:
                    line = f.readline()
                    if not line: break
                    if not line.strip(): continue
                    try:
                        cmd_data = json.loads(line)
                        self.cmd_queue.put(("json", cmd_data))
                    except json.JSONDecodeError:
                        # 兼容直接发送字符串
                        self.cmd_queue.put(("text", line.strip()))
        except Exception:
            pass
        finally:
            if client_sock in self.clients:
                self.clients.remove(client_sock)
            client_sock.close()

    def emit(self, msg_type, content, silent_console=False, **kwargs):
        # 广播给所有 Socket 客户端 (始终是 JSON)
        data = {"type": msg_type, "content": content}
        data.update(kwargs)
        json_payload = json.dumps(data, ensure_ascii=False) + "\n"
        
        for client in self.clients[:]:
            try:
                client.sendall(json_payload.encode('utf-8'))
            except Exception:
                self.clients.remove(client)

        # 本地终端输出 (如果不是静默模式)
        if silent_console:
            return

        if self.json_mode:
            print(json_payload.strip(), flush=True)
        else:
            if msg_type == "error":
                msg = content.get("message", content) if isinstance(content, dict) else content
                console.print(f"[bold red]ERROR:[/bold red] {msg}")
            elif msg_type == "sys":
                console.print(f"[dim cyan]SYSTEM:[/dim cyan] {content}")
            elif msg_type == "assistant":
                console.print("\n[bold green]Assistant:[/bold green]")
                console.print(content)
                console.print()
            elif msg_type == "user":
                console.print(f"\n[bold blue]You:[/bold blue] {content}\n")
            elif msg_type == "payload":
                model = content.get("model", "unknown")
                temp = content.get("temperature", "N/A")
                max_tokens = content.get("max_tokens", "N/A")
                tools_count = len(content.get("tools", []))
                
                reasoning = content.get("reasoning_content_generation")
                if reasoning is None:
                    reasoning = self.logic.options.provider_specific.get("reasoning", "off")
                
                console.print(f"[dim]PAYLOAD | Model: {model} | Temp: {temp} | Max: {max_tokens} | Tools: {tools_count} | Reasoning: {reasoning}[/dim]")
            elif msg_type == "reasoning":
                console.print(Panel(content, title="Reasoning", border_style="dim", style="dim italic"))
            elif msg_type == "tool_calls":
                json_str = json.dumps(content, indent=2, ensure_ascii=False)
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                console.print(Panel(syntax, title="Tool Calls", border_style="yellow"))
            elif msg_type == "tool_result":
                json_str = json.dumps(content, indent=2, ensure_ascii=False)
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                console.print(Panel(syntax, title="Tool Result", border_style="blue"))
            elif msg_type == "state":
                pass 
            elif msg_type == "contexts_list":
                pass

    def run(self):
        self.emit("sys", f"System initialized. {self.logic.get_current_provider()} - {self.logic.get_current_model()}")
        self.emit_state()

        # 启动 Stdin 读取线程
        def stdin_thread():
            if self.json_mode:
                while self.running:
                    try:
                        line = sys.stdin.readline()
                        if not line:
                            self.cmd_queue.put(("json", {"cmd": "exit"}))
                            break
                        line = line.strip()
                        if line:
                            try:
                                cmd_data = json.loads(line)
                                self.cmd_queue.put(("json", cmd_data))
                            except json.JSONDecodeError:
                                self.cmd_queue.put(("text", line))
                    except EOFError:
                        break
                    except Exception:
                        break
            else:
                session = PromptSession(history=FileHistory('.chat_history'))
                while self.running:
                    try:
                        line = session.prompt("> ", multiline=self.is_multiline)
                        if not line.strip(): 
                            continue
                        self.cmd_queue.put(("text", line.strip()))
                    except EOFError:
                        self.cmd_queue.put(("json", {"cmd": "exit"}))
                        break
                    except KeyboardInterrupt:
                        continue
                    except Exception as e:
                        break
        
        threading.Thread(target=stdin_thread, daemon=True).start()

        # 主循环处理队列
        while self.running:
            try:
                msg_type, data = self.cmd_queue.get(timeout=1.0)
                if msg_type == "json":
                    self.process_json_command(data)
                else:
                    self.process_text_command(data)
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.emit("error", {"message": f"Loop Error: {str(e)}\n{traceback.format_exc()}"})
        
        self.running = False

    def process_json_command(self, data):
        cmd = data.get("cmd")
        args = data.get("args", {})
        
        try:
            if cmd == "exit":
                sys.exit(0)
            elif cmd == "chat":
                self.do_chat(args.get("msg", ""))
            elif cmd == "get_payload":
                try:
                    payload = self.logic.get_full_payload(args.get("msg", ""))
                    self.emit("payload", payload, silent_console=True)
                except Exception:
                    pass
            elif cmd == "provider":
                self.logic.set_provider(args.get("provider"), args.get("model"))
                self.emit("sys", f"Switched to {self.logic.get_current_provider()} - {self.logic.get_current_model()}")
                self.emit_state()
            elif cmd == "option":
                self.logic.set_option(args.get("key"), args.get("value"))
                self.emit("sys", f"Set option {args.get('key')} = {args.get('value')}")
                self.emit_state()
            elif cmd == "tools":
                self.logic.set_enabled_tool_groups(args.get("groups", []))
                enabled_tools = self.logic.get_enabled_tools()
                self.emit("sys", f"Enabled tool groups updated. Active tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
                self.emit_state()
            elif cmd == "execute":
                self.do_execute()
            elif cmd == "send_results":
                self.do_send_results()
            elif cmd == "cancel_tools":
                self.logic.cancel_tool_calls()
                self.emit("sys", "Tool calls cancelled.")
                self.emit_state()
            elif cmd == "new" or cmd == "clear":
                self.logic.clear_context()
                self.emit("sys", "New session started.")
                self.emit_state()
            elif cmd == "save":
                self.logic.save_context_to_file(args.get("filename"))
                self.emit("sys", f"Chat saved to {args.get('filename')}")
            elif cmd == "list_contexts":
                contexts = self.logic.list_saved_contexts()
                self.emit("contexts_list", contexts)
            elif cmd == "load":
                self.logic.load_context_from_file(args.get("filename"))
                self.emit("sys", f"Chat loaded from {args.get('filename')}")
                self.emit_state()
                
                # Emit history so UI can redraw
                messages_preview = []
                for msg in self.logic.messages:
                    content_str = ""
                    try:
                        if isinstance(msg.content, list) and len(msg.content) > 0:
                            first_part = msg.content[0]
                            if hasattr(first_part, 'content'):
                                content_str = str(first_part.content)
                            elif isinstance(first_part, dict) and 'content' in first_part:
                                content_str = str(first_part['content'])
                            else:
                                content_str = str(first_part)
                        else:
                            content_str = str(msg.content)
                    except:
                        content_str = "[内容获取错误]"
                    messages_preview.append({"role": msg.role, "content": content_str})
                
                self.emit("history_loaded", messages_preview)

            elif cmd == "get_state":
                self.emit_state()
            elif cmd == "raw":
                self.process_text_command(args.get("text", ""))
            else:
                self.emit("error", {"message": f"Unknown command: {cmd}"})
        except Exception as e:
            self.emit("error", {"message": str(e)})

    def process_text_command(self, line):
        if self.cmd_manager.dispatch(line, self):
            return
        # If it wasn't a command, treat it as a chat message
        self.do_chat(line)

    def do_chat(self, msg):
        self.emit("user", msg)
        payload = self.logic.get_full_payload(msg)
        self.emit("payload", payload)
        
        ans, reason, pld = self.logic.chat(msg)
        self.emit("payload", pld)
        
        if reason:
            self.emit("reasoning", reason)
        
        # 始终发出回答（包括工具调用的检测信息或错误信息）
        if ans:
            self.emit("assistant", ans)
            
        if self.logic.is_in_tool_call_mode():
            self.emit("tool_calls", self.logic.get_pending_tool_calls())
            
        self.emit_state()

    def do_execute(self):
        results = self.logic.execute_pending_tools()
        self.emit("tool_result", results)
        self.emit_state()

    def do_send_results(self):
        ans, reason, pld = self.logic.send_tool_results_to_agent()
        self.emit("payload", pld)
        if reason:
            self.emit("reasoning", reason)
            
        # 始终发出回答（包括工具调用的检测信息或错误信息）
        if ans:
            self.emit("assistant", ans)
            
        if self.logic.is_in_tool_call_mode():
            self.emit("tool_calls", self.logic.get_pending_tool_calls())
            
        self.emit_state()

    def _get_state_dict(self):
        options_dict = {}
        if hasattr(self.logic.options, '__dict__'):
            for k, v in vars(self.logic.options).items():
                if isinstance(v, (str, int, float, bool, type(None), dict, list)):
                    options_dict[k] = v
                    
        return {
            "provider": self.logic.get_current_provider(),
            "model": self.logic.get_current_model(),
            "available_providers": self.logic.get_available_providers(),
            "models_for_provider": self.logic.get_models_for_provider(self.logic.get_current_provider()),
            "options": options_dict,
            "constraints": self.logic.get_option_constraints(),
            "tool_call_mode": self.logic.is_in_tool_call_mode(),
            "pending_tools": self.logic.get_pending_tool_calls(),
            "enabled_tools": self.logic.get_enabled_tools(),
            "all_tool_groups": list(self.logic.get_tools_config().get("tool_groups", {}).keys()),
            "enabled_groups": self.logic.get_tools_config().get('defaults', {}).get('enabled_groups', []),
            "supported_features": {
                "json_output": self.logic.supports_feature("json_output")
            }
        }

    def emit_state(self):
        self.emit("state", self._get_state_dict())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Enable JSON output mode")
    parser.add_argument("--port", type=int, help="Specify port for GUI bridge")
    args = parser.parse_args()
    cli = ChatCLI(json_mode=args.json, port=args.port)
    cli.run()
