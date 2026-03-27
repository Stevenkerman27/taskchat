import sys
import json
import argparse
import traceback
import socket
import threading
import queue
import shlex
from typing import Callable, Dict, List, Any, Optional

from prompt_toolkit import PromptSession, print_formatted_text, ANSI
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from chat_logic_v2 import ChatLogicV2

class TerminalRenderer:
    """负责终端的消息渲染和显示"""
    def __init__(self, json_mode: bool = False):
        # 强制开启颜色渲染以生成 ANSI 码，限制颜色系统为 256 以获得最佳的跨平台和 prompt_toolkit 兼容性
        self.console = Console(highlight=False, force_terminal=True, color_system="256")
        self.json_mode = json_mode

    def safe_print(self, *args, **kwargs):
        """
        核心机制：
        1. 用 rich 的 capture 机制，拦截本来要打印到屏幕的内容。
        2. 获取带有底层 ANSI 转义码（类似 \x1b[31m）的原始字符串。
        3. 将原始字符串包装为 prompt_toolkit 认识的 ANSI 对象，由其统一输出。
        """
        with self.console.capture() as capture:
            self.console.print(*args, **kwargs)
        
        ansi_text = capture.get()
        print_formatted_text(ANSI(ansi_text), end="")

    def render(self, msg_type: str, content: Any, **kwargs):
        if self.json_mode:
            return

        if msg_type == "error":
            self.render_error(content)
        elif msg_type == "sys":
            self.render_system(content)
        elif msg_type == "assistant":
            self.render_assistant(content)
        elif msg_type == "user":
            self.render_user(content)
        elif msg_type == "payload":
            self.render_payload(content, **kwargs)
        elif msg_type == "reasoning":
            self.render_reasoning(content)
        elif msg_type == "tool_calls":
            self.render_tool_calls(content)
        elif msg_type == "tool_result":
            self.render_tool_results(content)

    def render_error(self, content):
        msg = content.get("message", content) if isinstance(content, dict) else content
        t = Text()
        t.append("ERROR: ", style="bold red")
        t.append(msg)
        self.safe_print(t)

    def render_system(self, content):
        t = Text()
        t.append("SYSTEM: ", style="cyan")
        t.append(str(content))
        self.safe_print(t)

    def render_assistant(self, content):
        self.safe_print(Text("\nAssistant:", style="bold green"))
        self.safe_print(Text(str(content), style="green"))
        self.safe_print()

    def render_user(self, content):
        t = Text()
        t.append("You: ", style="bold blue")
        t.append(str(content), style="blue")
        self.safe_print("\n", t, "\n")

    def render_payload(self, content, logic=None):
        model = content.get("model", "unknown")
        temp = content.get("temperature", "N/A")
        max_tokens = content.get("max_tokens", "N/A")
        tools_count = len(content.get("tools", []))
        
        reasoning = content.get("reasoning_content_generation")
        if reasoning is None and logic:
            reasoning = logic.options.provider_specific.get("reasoning", "off")
        
        self.safe_print(f"PAYLOAD | Model: {model} | Temp: {temp} | Max: {max_tokens} | Tools: {tools_count} | Reasoning: {reasoning}")

    def render_reasoning(self, content):
        self.safe_print(Panel(str(content), title="Reasoning", style="italic"))

    def render_tool_calls(self, content):
        json_str = json.dumps(content, indent=2, ensure_ascii=False)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
        self.safe_print(Panel(syntax, title="Tool Calls", border_style="yellow"))

    def render_tool_results(self, content):
        json_str = json.dumps(content, indent=2, ensure_ascii=False)
        syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
        self.safe_print(Panel(syntax, title="Tool Result", border_style="blue"))


class SocketBridgeServer:
    """负责与 GUI 的 Socket 通信"""
    def __init__(self, port: int, cmd_queue: queue.Queue):
        self.port = port
        self.cmd_queue = cmd_queue
        self.clients = []
        self.clients_lock = threading.Lock()
        self.running = True

    def start(self):
        threading.Thread(target=self._server_loop, daemon=True).start()

    def _server_loop(self):
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
                with self.clients_lock:
                    self.clients.append(client_sock)
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[BRIDGE] Accept error: {e}")
                break
        server_socket.close()

    def _handle_client(self, client_sock):
        try:
            with client_sock.makefile('r', encoding='utf-8') as f:
                while self.running:
                    line = f.readline()
                    if not line: break
                    line = line.strip()
                    if not line: continue
                    try:
                        cmd_data = json.loads(line)
                        self.cmd_queue.put(("json", cmd_data))
                    except json.JSONDecodeError:
                        self.cmd_queue.put(("text", line))
        except Exception:
            pass
        finally:
            self._remove_client(client_sock)

    def _remove_client(self, client_sock):
        with self.clients_lock:
            if client_sock in self.clients:
                self.clients.remove(client_sock)
        try:
            client_sock.close()
        except:
            pass

    def broadcast(self, data: Dict[str, Any]):
        json_payload = json.dumps(data, ensure_ascii=False) + "\n"
        encoded_payload = json_payload.encode('utf-8')
        
        with self.clients_lock:
            disconnected = []
            for client in self.clients:
                try:
                    client.sendall(encoded_payload)
                except Exception:
                    disconnected.append(client)
            
            for client in disconnected:
                if client in self.clients:
                    self.clients.remove(client)

    def stop(self):
        self.running = False


class CommandDispatcher:
    """负责命令注册和分发"""
    def __init__(self):
        self.commands: Dict[str, Dict[str, Any]] = {}
        
    def register(self, name: str, func: Callable, aliases: List[str] = None, help_text: str = ""):
        cmd_info = {"func": func, "help": help_text}
        self.commands[name] = cmd_info
        if aliases:
            for alias in aliases:
                self.commands[alias] = cmd_info

    def dispatch(self, input_line: str, context: Any) -> bool:
        if not input_line.startswith('/'):
            return False
            
        try:
            parts = shlex.split(input_line)
        except ValueError as e:
            context.emit_error(f"Invalid command format: {str(e)}")
            return True
            
        if not parts:
            return False
            
        cmd_name = parts[0]
        args = parts[1:]
        
        if cmd_name in self.commands:
            try:
                self.commands[cmd_name]["func"](*args)
            except Exception as e:
                context.emit_error(f"Command execution error: {str(e)}\n{traceback.format_exc()}")
            return True
        else:
            context.emit_error(f"Unknown command: {cmd_name}. Type /help for available commands.")
            return True
            
    def get_help_text(self) -> str:
        help_lines = ["Available Commands:"]
        seen_funcs = set()
        for name in sorted(self.commands.keys()):
            info = self.commands[name]
            if info["func"] not in seen_funcs:
                help_lines.append(f"  {name.ljust(15)} - {info['help']}")
                seen_funcs.add(info["func"])
        return "\n".join(help_lines)


class ChatCLI:
    def __init__(self, json_mode=False, port=None):
        self.json_mode = json_mode
        self.port = port
        self.cmd_queue = queue.Queue()
        self.running = True
        self.is_multiline = False
        
        self.renderer = TerminalRenderer(json_mode=json_mode)
        self.bridge = SocketBridgeServer(port, self.cmd_queue) if port else None
        self.dispatcher = CommandDispatcher()
        
        self._register_all_commands()
        
        try:
            self.logic = ChatLogicV2()
        except Exception as e:
            self.emit_error(f"Initialization Error: {str(e)}")
            sys.exit(1)
            
        if self.bridge:
            self.bridge.start()

    def _register_all_commands(self):
        self.dispatcher.register("/help", self._cmd_help, help_text="Show this help message")
        self.dispatcher.register("/exit", self._cmd_exit, aliases=["/quit"], help_text="Exit the application")
        self.dispatcher.register("/chat", self._cmd_chat, help_text="Send a message to the assistant")
        self.dispatcher.register("/provider", self._cmd_provider, help_text="Switch provider and optionally model")
        self.dispatcher.register("/option", self._cmd_option, help_text="Set a chat option")
        self.dispatcher.register("/tools", self._cmd_tools, help_text="Enable tool groups")
        self.dispatcher.register("/execute", self._cmd_execute, help_text="Execute pending tool calls")
        self.dispatcher.register("/send_results", self._cmd_send_results, help_text="Send tool results back")
        self.dispatcher.register("/cancel_tools", self._cmd_cancel_tools, help_text="Cancel pending tool calls")
        self.dispatcher.register("/new", self._cmd_new, aliases=["/clear"], help_text="Start a new blank session")
        self.dispatcher.register("/save", self._cmd_save, help_text="Save current chat to a file")
        self.dispatcher.register("/load", self._cmd_load, help_text="Load a chat from a file")
        self.dispatcher.register("/state", self._cmd_state, help_text="Show current system state")
        self.dispatcher.register("/multiline", self._cmd_multiline, help_text="Toggle multiline input mode")

    # Command Implementations
    def _cmd_help(self, *args):
        self.emit_sys(self.dispatcher.get_help_text())

    def _cmd_exit(self, *args):
        self.running = False
        sys.exit(0)

    def _cmd_chat(self, *args):
        msg = " ".join(args)
        self.do_chat(msg)

    def _cmd_provider(self, *args):
        available = self.logic.get_available_providers()
        if not args:
            self.emit_sys("Available Providers:")
            for i, p in enumerate(available, 1):
                status = "[ACTIVE]" if p['is_current'] else ""
                self.emit_sys(f"  {i}. {p['id']} ({p['name']}) {status}")
                self.emit_sys(f"     Models: {', '.join(p['models'])}")
            self.emit_sys("Use '/provider <name_or_index> [model]' to switch.")
            return

        provider_input = args[0]
        model = args[1] if len(args) > 1 else None
        
        if provider_input.isdigit():
            idx = int(provider_input) - 1
            if 0 <= idx < len(available):
                provider_input = available[idx]['id']
            else:
                self.emit_error(f"Invalid provider index: {idx+1}")
                return

        try:
            self.logic.set_provider(provider_input, model)
            self.emit_sys(f"Switched to {provider_input} - {self.logic.get_current_model()}")
            self.emit_state()
        except Exception as e:
            self.emit_error(str(e))

    def _cmd_option(self, *args):
        current_options = self.logic.get_current_options_dict()
        if not args:
            self.emit_sys("Current Chat Options:")
            for i, (k, v) in enumerate(current_options.items(), 1):
                self.emit_sys(f"  {i}. {k} = {v}")
            self.emit_sys("Use '/option <key_or_index> <value>' to set.")
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
                    self.emit_error(f"Invalid option index: {idx+1}")
                    return

            try:
                if val_str.lower() == "true": val = True
                elif val_str.lower() == "false": val = False
                else:
                    try: val = int(val_str)
                    except ValueError:
                        try: val = float(val_str)
                        except ValueError: val = val_str
                self.logic.set_option(key_input, val)
                self.emit_sys(f"Set option {key_input} = {val}")
                self.emit_state()
            except Exception as e:
                self.emit_error(str(e))
        else:
            self.emit_sys("Usage: /option <key_or_index> <value>")

    def _cmd_tools(self, *args):
        tool_info = self.logic.get_available_tool_groups()
        all_groups = list(tool_info['groups'].keys())
        
        if not args:
            self.emit_sys("Available Tool Groups:")
            for i, group_name in enumerate(all_groups, 1):
                status = "[ACTIVE]" if group_name in tool_info['enabled'] else ""
                tools = tool_info['groups'][group_name].get('tools', [])
                desc = tool_info['groups'][group_name].get('description', '')
                self.emit_sys(f"  {i}. {group_name} ({desc}) {status}")
                self.emit_sys(f"     Tools: {', '.join(tools)}")
            self.emit_sys("Use '/tools <name_or_index1,index2...>' to enable.")
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
                    self.emit_error(f"Invalid tool group index: {idx+1}")
            else:
                final_groups.append(item)
        
        self.logic.set_enabled_tool_groups(final_groups)
        enabled_tools = self.logic.get_enabled_tools()
        self.emit_sys(f"Enabled tool groups updated. Active tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
        self.emit_state()

    def _cmd_execute(self, *args):
        self.do_execute()

    def _cmd_send_results(self, *args):
        self.do_send_results()

    def _cmd_cancel_tools(self, *args):
        self.logic.cancel_tool_calls()
        self.emit_sys("Tool calls cancelled.")
        self.emit_state()

    def _cmd_new(self, *args):
        self.logic.clear_context()
        self.emit_sys("New session started.")
        self.emit_state()

    def _cmd_save(self, *args):
        if not args:
            self.emit_error("Usage: /save <filename>")
            return
        filename = args[0]
        try:
            self.logic.save_context_to_file(filename)
            self.emit_sys(f"Chat saved to {filename}")
        except Exception as e:
            self.emit_error(str(e))

    def _cmd_load(self, *args):
        if not args:
            self.emit_error("Usage: /load <filename>")
            return
        filename = args[0]
        try:
            self.logic.load_context_from_file(filename)
            self.emit_sys(f"Chat loaded from {filename}")
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
        except Exception as e:
            self.emit_error(str(e))

    def _cmd_state(self, *args):
        self.emit_state()
        if not self.json_mode:
            state = self._get_state_dict()
            self.renderer.safe_print(f"State: {json.dumps(state, indent=2, ensure_ascii=False)}")

    def _cmd_multiline(self, *args):
        self.is_multiline = not self.is_multiline
        status = "ON" if self.is_multiline else "OFF"
        if not self.json_mode:
            self.renderer.safe_print(f"[bold magenta]Multiline mode {status}[/bold magenta]. (Press Esc+Enter to submit in multiline mode)")
        else:
            self.emit_sys(f"Multiline mode {status}")

    # Core Logic
    def emit(self, msg_type: str, content: Any, silent_console: bool = False, **kwargs):
        """统一的消息发送入口"""
        data = {"type": msg_type, "content": content}
        data.update(kwargs)
        
        # 发送给 GUI
        if self.bridge:
            self.bridge.broadcast(data)
            
        # 终端渲染
        if not silent_console:
            if self.json_mode:
                print(json.dumps(data, ensure_ascii=False), flush=True)
            else:
                self.renderer.render(msg_type, content, logic=self.logic, **kwargs)

    def emit_error(self, message):
        self.emit("error", {"message": message})

    def emit_sys(self, message):
        self.emit("sys", message)

    def emit_state(self):
        self.emit("state", self._get_state_dict())

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

    def do_chat(self, msg):
        self.emit("user", msg)
        payload = self.logic.get_full_payload(msg)
        self.emit("payload", payload)
        
        ans, reason, pld = self.logic.chat(msg)
        self.emit("payload", pld)
        
        if reason:
            self.emit("reasoning", reason)
        
        if ans:
            self.emit("assistant", ans)
            
        if self.logic.is_in_tool_call_mode():
            self.emit("tool_calls", self.logic.get_pending_tool_calls())
            
        self.emit_state()

    def do_execute(self):
        self.emit_sys("DEBUG: starting execute_pending_tools")
        results = self.logic.execute_pending_tools()
        self.emit_sys("DEBUG: finished execute_pending_tools")
        self.emit("tool_result", results)
        self.emit_state()

    def do_send_results(self):
        ans, reason, pld = self.logic.send_tool_results_to_agent()
        self.emit("payload", pld)
        if reason:
            self.emit("reasoning", reason)
            
        if ans:
            self.emit("assistant", ans)
            
        if self.logic.is_in_tool_call_mode():
            self.emit("tool_calls", self.logic.get_pending_tool_calls())
            
        self.emit_state()

    def run(self):
        self.emit_sys(f"System initialized. {self.logic.get_current_provider()} - {self.logic.get_current_model()}")
        self.emit_state()

        # Input Thread
        def input_thread():
            if self.json_mode:
                while self.running:
                    try:
                        line = sys.stdin.readline()
                        if not line:
                            self.cmd_queue.put(("json", {"cmd": "exit"}))
                            break
                        line = line.strip()
                        if not line: continue
                        try:
                            cmd_data = json.loads(line)
                            self.cmd_queue.put(("json", cmd_data))
                        except json.JSONDecodeError:
                            self.cmd_queue.put(("text", line))
                    except EOFError:
                        break
                    except Exception as e:
                        if self.running:
                            self.emit_error(f"Input thread error: {e}")
                        break
            else:
                session = PromptSession()
                while self.running:
                    try:
                        with patch_stdout():
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
                        if self.running:
                            self.emit_error(f"Prompt error: {e}")
                        break
        
        threading.Thread(target=input_thread, daemon=True).start()

        # Main Loop
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
                self.emit_error(f"Main loop error: {str(e)}\n{traceback.format_exc()}")
        
        self.running = False
        if self.bridge:
            self.bridge.stop()

    def process_json_command(self, data):
        cmd = data.get("cmd")
        args = data.get("args", {})
        
        try:
            if cmd == "exit":
                self.running = False
                sys.exit(0)
            elif cmd == "chat":
                self.do_chat(args.get("msg", ""))
            elif cmd == "get_payload":
                try:
                    payload = self.logic.get_full_payload(args.get("msg", ""))
                    self.emit("payload", payload, silent_console=True)
                except:
                    pass
            elif cmd == "provider":
                self.logic.set_provider(args.get("provider"), args.get("model"))
                self.emit_sys(f"Switched to {self.logic.get_current_provider()} - {self.logic.get_current_model()}")
                self.emit_state()
            elif cmd == "option":
                self.logic.set_option(args.get("key"), args.get("value"))
                self.emit_sys(f"Set option {args.get('key')} = {args.get('value')}")
                self.emit_state()
            elif cmd == "tools":
                self.logic.set_enabled_tool_groups(args.get("groups", []))
                enabled_tools = self.logic.get_enabled_tools()
                self.emit_sys(f"Enabled tool groups updated. Active tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
                self.emit_state()
            elif cmd == "execute":
                self.do_execute()
            elif cmd == "send_results":
                self.do_send_results()
            elif cmd == "cancel_tools":
                self.logic.cancel_tool_calls()
                self.emit_sys("Tool calls cancelled.")
                self.emit_state()
            elif cmd == "new" or cmd == "clear":
                self.logic.clear_context()
                self.emit_sys("New session started.")
                self.emit_state()
            elif cmd == "save":
                self.logic.save_context_to_file(args.get("filename"))
                self.emit_sys(f"Chat saved to {args.get('filename')}")
            elif cmd == "list_contexts":
                contexts = self.logic.list_saved_contexts()
                self.emit("contexts_list", contexts)
            elif cmd == "load":
                self._cmd_load(args.get("filename"))
            elif cmd == "get_state":
                self.emit_state()
            elif cmd == "raw":
                self.process_text_command(args.get("text", ""))
            else:
                self.emit_error(f"Unknown JSON command: {cmd}")
        except Exception as e:
            self.emit_error(f"JSON command error: {str(e)}")

    def process_text_command(self, line):
        if self.dispatcher.dispatch(line, self):
            return
        self.do_chat(line)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Enable JSON output mode")
    parser.add_argument("--port", type=int, help="Specify port for GUI bridge")
    args = parser.parse_args()
    cli = ChatCLI(json_mode=args.json, port=args.port)
    cli.run()
