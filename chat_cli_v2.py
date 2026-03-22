import sys
import json
import argparse
import traceback
import socket
import threading
import queue
from chat_logic_v2 import ChatLogicV2

class ChatCLI:
    def __init__(self, json_mode=False, port=None):
        self.json_mode = json_mode
        self.port = port
        self.clients = []
        self.cmd_queue = queue.Queue()
        self.running = True
        
        try:
            self.logic = ChatLogicV2()
        except Exception as e:
            self.emit("error", {"message": f"Initialization Error: {str(e)}"})
            sys.exit(1)
            
        if self.port:
            self.start_socket_server()

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
                print(f"[ERROR] {msg}", flush=True)
            elif msg_type == "sys":
                print(f"[SYSTEM] {content}", flush=True)
            elif msg_type == "assistant":
                print(f"\nAssistant:\n{content}\n", flush=True)
            elif msg_type == "user":
                print(f"\nYou: {content}\n", flush=True)
            elif msg_type == "payload":
                model = content.get("model", "unknown")
                temp = content.get("temperature", "N/A")
                max_tokens = content.get("max_tokens", "N/A")
                tools_count = len(content.get("tools", []))
                
                # 尝试从不同提供商可能的字段提取 reasoning
                reasoning = content.get("reasoning_content_generation")
                if reasoning is None:
                    # 尝试从逻辑选项中获取
                    reasoning = self.logic.options.provider_specific.get("reasoning", "off")
                
                print(f"[PAYLOAD] Model: {model} | Temp: {temp} | Max: {max_tokens} | Tools: {tools_count} | Reasoning: {reasoning}", flush=True)
            elif msg_type == "reasoning":
                print(f"Reasoning:\n{content}\n", flush=True)
            elif msg_type == "tool_calls":
                print(f"Tool Calls:\n{json.dumps(content, indent=2, ensure_ascii=False)}\n", flush=True)
            elif msg_type == "tool_result":
                print(f"Tool Result:\n{json.dumps(content, indent=2, ensure_ascii=False)}\n", flush=True)
            elif msg_type == "state":
                pass 
            elif msg_type == "contexts_list":
                pass

    def run(self):
        self.emit("sys", f"System initialized. {self.logic.get_current_provider()} - {self.logic.get_current_model()}")
        self.emit_state()

        # 启动 Stdin 读取线程
        def stdin_thread():
            while self.running:
                try:
                    if not self.json_mode:
                        print("> ", end="", flush=True)
                    line = sys.stdin.readline()
                    if not line:
                        self.cmd_queue.put(("json", {"cmd": "exit"}))
                        break
                    line = line.strip()
                    if line:
                        if self.json_mode:
                            try:
                                cmd_data = json.loads(line)
                                self.cmd_queue.put(("json", cmd_data))
                            except json.JSONDecodeError:
                                self.cmd_queue.put(("text", line))
                        else:
                            self.cmd_queue.put(("text", line))
                except EOFError:
                    break
                except Exception:
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
        if line == "/exit" or line == "/quit":
            sys.exit(0)
        elif line == "/help":
            help_text = """
Available Commands:
  /chat <msg>          - Send a message to the assistant
  /provider <p> [m]    - Switch provider and optionally model
  /option <k> <v>      - Set a chat option (e.g. /option temperature 0.5)
  /tools <g1,g2>       - Enable tool groups (comma separated)
  /execute             - Execute pending tool calls
  /send_results        - Send tool results back to the assistant
  /cancel_tools        - Cancel pending tool calls
  /new                 - Start a new blank session
  /save <filename>     - Save current chat to a file
  /load <filename>     - Load a chat from a file
  /state               - Show current system state
  /exit                - Exit the application
  /help                - Show this help message
            """
            print(help_text)
        elif line.startswith("/chat "):
            msg = line[6:].strip()
            self.do_chat(msg)
        elif line.startswith("/provider"):
            args_str = line[9:].strip()
            available = self.logic.get_available_providers()
            
            if not args_str:
                # 查询模式
                self.emit("sys", "Available Providers:")
                for i, p in enumerate(available, 1):
                    status = "[ACTIVE]" if p['is_current'] else ""
                    self.emit("sys", f"  {i}. {p['id']} ({p['name']}) {status}")
                    self.emit("sys", f"     Models: {', '.join(p['models'])}")
                self.emit("sys", "Use '/provider <name_or_index> [model]' to switch.")
                return

            parts = args_str.split()
            provider_input = parts[0]
            model = parts[1] if len(parts) > 1 else None
            
            # 处理数字索引
            if provider_input.isdigit():
                idx = int(provider_input) - 1
                if 0 <= idx < len(available):
                    provider_input = available[idx]['id']
                else:
                    self.emit("error", {"message": f"Invalid provider index: {idx+1}"})
                    return

            try:
                self.logic.set_provider(provider_input, model)
                self.emit("sys", f"Switched to {provider_input} - {self.logic.get_current_model()}")
                self.emit_state()
            except Exception as e:
                self.emit("error", {"message": str(e)})

        elif line.startswith("/option"):
            args_str = line[7:].strip()
            current_options = self.logic.get_current_options_dict()
            
            if not args_str:
                # 查询模式
                self.emit("sys", "Current Chat Options:")
                for i, (k, v) in enumerate(current_options.items(), 1):
                    self.emit("sys", f"  {i}. {k} = {v}")
                self.emit("sys", "Use '/option <key_or_index> <value>' to set.")
                return

            parts = args_str.split(maxsplit=1)
            if len(parts) == 2:
                key_input, val_str = parts
                
                # 处理数字索引
                if key_input.isdigit():
                    idx = int(key_input) - 1
                    keys = list(current_options.keys())
                    if 0 <= idx < len(keys):
                        key_input = keys[idx]
                    else:
                        self.emit("error", {"message": f"Invalid option index: {idx+1}"})
                        return

                try:
                    if val_str.lower() == "true": val = True
                    elif val_str.lower() == "false": val = False
                    else:
                        try:
                            val = int(val_str)
                        except ValueError:
                            try:
                                val = float(val_str)
                            except ValueError:
                                val = val_str
                    self.logic.set_option(key_input, val)
                    self.emit("sys", f"Set option {key_input} = {val}")
                    self.emit_state()
                except Exception as e:
                    self.emit("error", {"message": str(e)})
            else:
                self.emit("sys", "Usage: /option <key_or_index> <value>")

        elif line.startswith("/tools"):
            args_str = line[6:].strip()
            tool_info = self.logic.get_available_tool_groups()
            all_groups = list(tool_info['groups'].keys())
            
            if not args_str:
                # 查询模式
                self.emit("sys", "Available Tool Groups:")
                for i, group_name in enumerate(all_groups, 1):
                    status = "[ACTIVE]" if group_name in tool_info['enabled'] else ""
                    tools = tool_info['groups'][group_name].get('tools', [])
                    desc = tool_info['groups'][group_name].get('description', '')
                    self.emit("sys", f"  {i}. {group_name} ({desc}) {status}")
                    self.emit("sys", f"     Tools: {', '.join(tools)}")
                self.emit("sys", "Use '/tools <name_or_index1,index2...>' to enable.")
                return

            # 处理输入（支持逗号分隔的名字或索引）
            inputs = [i.strip() for i in args_str.split(",") if i.strip()]
            final_groups = []
            for item in inputs:
                if item.isdigit():
                    idx = int(item) - 1
                    if 0 <= idx < len(all_groups):
                        final_groups.append(all_groups[idx])
                    else:
                        self.emit("error", {"message": f"Invalid tool group index: {idx+1}"})
                else:
                    final_groups.append(item)
            
            self.logic.set_enabled_tool_groups(final_groups)
            enabled_tools = self.logic.get_enabled_tools()
            self.emit("sys", f"Enabled tool groups updated. Active tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
            self.emit_state()
        elif line == "/execute":
            self.do_execute()
        elif line == "/send_results":
            self.do_send_results()
        elif line == "/cancel_tools":
            self.logic.cancel_tool_calls()
            self.emit("sys", "Tool calls cancelled.")
            self.emit_state()
        elif line == "/new" or line == "/clear":
            self.logic.clear_context()
            self.emit("sys", "New session started.")
            self.emit_state()
        elif line.startswith("/save "):
            filename = line[6:].strip()
            try:
                self.logic.save_context_to_file(filename)
                self.emit("sys", f"Chat saved to {filename}")
            except Exception as e:
                self.emit("error", {"message": str(e)})
        elif line.startswith("/load "):
            filename = line[6:].strip()
            try:
                self.logic.load_context_from_file(filename)
                self.emit("sys", f"Chat loaded from {filename}")
                self.emit_state()
            except Exception as e:
                self.emit("error", {"message": str(e)})
        elif line == "/state":
            self.emit_state()
            if not self.json_mode:
                state = self._get_state_dict()
                print(f"State: {json.dumps(state, indent=2, ensure_ascii=False)}", flush=True)
        elif line.startswith("/"):
            self.emit("error", {"message": f"Unknown command: {line}"})
        else:
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
