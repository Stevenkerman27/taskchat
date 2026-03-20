"""
重构的ChatGUI类
采用 GUI 包装器模式 (GUI Wrapper Architecture)
作为 chat_cli_v2.py 的前端，通过标准输入输出与核心逻辑通信
"""
import os
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import json
import traceback
import sys
import datetime
import subprocess
import threading
import socket
import time

class ChatGUIV2:
    FONT_MAIN = ("Microsoft YaHei", 10)
    FONT_BOLD = ("Microsoft YaHei", 10, "bold")
    FONT_ITALIC = ("Microsoft YaHei", 9, "italic")
    FONT_SMALL = ("Microsoft YaHei", 9)
    FONT_SMALL_BOLD = ("Microsoft YaHei", 9, "bold")
    FONT_MONO = ("Consolas", 9)
    FONT_MONO_BOLD = ("Consolas", 9, "bold")

    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Model Chat GUI v2 - CLI Bridge Architecture")
        
        # 状态缓存与通信
        self.current_state = {}
        self.cli_process = None
        self.sock = None
        self.sock_port = 9999
        self.bridge_connected = False
        self._preview_timer = None
        
        # 布局配置
        self.root.grid_rowconfigure(3, weight=3) # Chat Output
        self.root.grid_rowconfigure(5, weight=1) # Preview Area
        self.root.grid_columnconfigure(0, weight=1)
        
        # 创建UI组件
        self.create_config_frame()
        self.create_advanced_options_frame()
        self.create_tools_frame()
        self.create_output_area()
        self.create_input_area()
        
        # 启动 CLI 并建立连接
        self.start_cli()
    
    def start_cli(self):
        """在独立控制台中启动 CLI 并建立 Socket 连接"""
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            
            # 使用 CREATE_NEW_CONSOLE 弹出可见窗口
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_CONSOLE
                
            # 启动 CLI，带上 --port 参数
            self.cli_process = subprocess.Popen(
                [sys.executable, "-X", "utf8", "-u", "chat_cli_v2.py", "--port", str(self.sock_port)],
                creationflags=creationflags,
                env=env
            )
            
            # 尝试连接 Socket (带重试逻辑)
            threading.Thread(target=self.connect_to_bridge, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Initialization Error", f"Failed to start CLI process:\n{str(e)}")
            sys.exit(1)

    def connect_to_bridge(self):
        """后台尝试连接到 CLI 的 Socket Bridge"""
        retries = 10
        while retries > 0:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect(('localhost', self.sock_port))
                self.bridge_connected = True
                self.log("[System] Connected to CLI Bridge.\n")
                
                # 启动读取线程
                threading.Thread(target=self.read_socket_loop, daemon=True).start()
                
                # 请求初始状态
                self.send_cmd("get_state")
                return
            except Exception:
                retries -= 1
                time.sleep(0.5)
        
        self.root.after(0, lambda: messagebox.showerror("Connection Error", "Failed to connect to CLI Bridge server."))

    def send_cmd(self, cmd, args=None):
        """通过 Socket 发送 JSON 指令到 CLI"""
        if args is None: 
            args = {}
        if self.bridge_connected:
            data = {"cmd": cmd, "args": args}
            try:
                payload = json.dumps(data, ensure_ascii=False) + "\n"
                self.sock.sendall(payload.encode('utf-8'))
            except Exception as e:
                self.log(f"[Error] Failed to send command: {e}\n", "error")
                self.bridge_connected = False
        else:
            self.log("[Error] CLI bridge is not connected.\n", "error")

    def read_socket_loop(self):
        """循环读取 Socket 中的 JSON 事件"""
        buffer = ""
        while self.bridge_connected:
            try:
                data = self.sock.recv(4096).decode('utf-8')
                if not data:
                    self.bridge_connected = False
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip(): continue
                    try:
                        event_data = json.loads(line)
                        self.root.after(0, self.handle_cli_event, event_data)
                    except json.JSONDecodeError:
                        pass
            except Exception:
                self.bridge_connected = False
                break
        self.log("[System] CLI Bridge disconnected.\n", "error")

    def handle_cli_event(self, data):
        """处理来自 CLI 的 JSON 事件"""
        msg_type = data.get("type")
        content = data.get("content")
        
        if msg_type == "state":
            self.update_state(content)
        elif msg_type == "sys":
            self.log(f"[System] {content}\n")
        elif msg_type == "error":
            msg = content.get("message", content) if isinstance(content, dict) else content
            self.log(f"[ERROR] Error: {msg}\n", "error")
            messagebox.showerror("Error", msg)
        elif msg_type == "user":
            pass # UI 已经自己打印了，或者 CLI 会回传消息我们在这里打印
            # 既然是同步的，CLI 也会回传 user 消息，如果 GUI 没打过，可以在这里打
        elif msg_type == "assistant":
            self.log(f"\nAssistant: {content}\n\n", "assistant")
            self.on_interaction_end()
        elif msg_type == "reasoning":
            self.log("\n[Reasoning]\n", "reasoning_header")
            self.log(f"{content}\n", "reasoning")
        elif msg_type == "tool_calls":
            self.log(f"\n[Tool Call Mode] 检测到 {len(content)} 个工具调用:\n", "tool_call")
            for i, tc in enumerate(content, 1):
                self.log(f"  {i}. {tc.get('function_name', 'unknown')}\n", "tool_call")
                self.log(f"     参数: {json.dumps(tc.get('arguments', {}), indent=2, ensure_ascii=False)}\n", "tool_call")
            self.log("\n请使用工具管理区域的按钮执行工具并发送结果。\n", "tool_call")
            self.on_tool_mode_start()
        elif msg_type == "tool_result":
            self.log(f"\n[Tool Execution] 执行了 {len(content)} 个工具:\n", "tool_result")
            for i, res in enumerate(content, 1):
                if "error" in res:
                    self.log(f"  {i}. [ERROR] {res.get('function_name', 'unknown')}: {res['error']}\n", "tool_result")
                else:
                    self.log(f"  {i}. [OK] {res.get('function_name', 'unknown')}\n", "tool_result")
                    self.log(f"     结果: {str(res.get('result', ''))}\n", "tool_result")
        elif msg_type == "payload":
            self.update_preview_area(content)
        elif msg_type == "contexts_list":
            self.show_load_dialog(content)
        elif msg_type == "history_loaded":
            self.display_loaded_history(content)

    def display_loaded_history(self, messages):
        self.output_area.config(state='normal')
        self.output_area.delete("1.0", tk.END)
        self.output_area.config(state='disabled')
        
        self.log("\n--- 加载的聊天记录 ---\n")
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            role_display = "用户" if role == "user" else "助手" if role == "assistant" else role
            content = msg.get("content", "[无内容]")
            self.log(f"{i}. [{role_display}] {content}\n")
        self.log("--- 结束 ---\n")

    def update_state(self, new_state):
        old_state = self.current_state
        self.current_state = new_state
        
        # update providers
        if old_state.get("available_providers") != new_state.get("available_providers"):
            self.provider_combo['values'] = new_state.get("available_providers", [])
        
        # update models
        provider_changed = old_state.get("provider") != new_state.get("provider")
        models_changed = old_state.get("models_for_provider") != new_state.get("models_for_provider")
        if provider_changed or models_changed:
            self.provider_var.set(new_state.get("provider", ""))
            self.model_combo['values'] = new_state.get("models_for_provider", [])
            
        if old_state.get("model") != new_state.get("model"):
            self.model_var.set(new_state.get("model", ""))
            
        # UI Options refresh when provider/model changes
        if provider_changed or old_state.get("model") != new_state.get("model"):
            self.refresh_ui_options(new_state)
            
        # Update tools UI
        if old_state.get("enabled_groups") != new_state.get("enabled_groups") or old_state.get("all_tool_groups") != new_state.get("all_tool_groups"):
            self.update_tools_ui(new_state)
            
        if old_state.get("enabled_tools") != new_state.get("enabled_tools"):
            enabled = new_state.get("enabled_tools", [])
            self.tools_list_var.set(", ".join(enabled) if enabled else "No tools enabled")

        # Update Tool state (check if all executed)
        if new_state.get("tool_call_mode"):
            pending = new_state.get("pending_tools", [])
            if pending:
                all_executed = all(t.get("executed", False) for t in pending)
                if all_executed:
                    self.send_tool_results_btn.config(state="normal")
                    self.execute_tools_btn.config(state="disabled")
                else:
                    self.send_tool_results_btn.config(state="disabled")
                    self.execute_tools_btn.config(state="normal")
        else:
            self.on_interaction_end()
    
    def on_interaction_end(self):
        self.send_btn.config(state="normal")
        self.execute_tools_btn.config(state="disabled")
        self.send_tool_results_btn.config(state="disabled")
        self.cancel_tools_btn.config(state="disabled")
    
    def on_tool_mode_start(self):
        self.send_btn.config(state="disabled")
        self.execute_tools_btn.config(state="normal")
        self.send_tool_results_btn.config(state="disabled")
        self.cancel_tools_btn.config(state="normal")

    def create_config_frame(self):
        self.config_frame = tk.Frame(self.root)
        self.config_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        
        tk.Label(self.config_frame, text="Provider:").pack(side=tk.LEFT)
        self.provider_var = tk.StringVar()
        self.provider_combo = ttk.Combobox(
            self.config_frame, 
            textvariable=self.provider_var,
            state="readonly",
            width=15
        )
        self.provider_combo.pack(side=tk.LEFT, padx=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)
        
        tk.Label(self.config_frame, text="Model:").pack(side=tk.LEFT, padx=(10, 0))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            self.config_frame,
            textvariable=self.model_var,
            state="readonly",
            width=25
        )
        self.model_combo.pack(side=tk.LEFT, padx=5)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_change)
    
    def create_advanced_options_frame(self):
        self.options_frame = tk.LabelFrame(self.root, text="Advanced Options", padx=10, pady=5)
        self.options_frame.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="ew")
        
        # 温度设置
        tk.Label(self.options_frame, text="Temperature:").pack(side=tk.LEFT, padx=(0, 5))
        self.temperature_var = tk.DoubleVar(value=0.7)
        self.temperature_spinbox = tk.Spinbox(
            self.options_frame,
            from_=0.0,
            to=2.0,
            increment=0.1,
            textvariable=self.temperature_var,
            width=5,
            command=self.on_temperature_change
        )
        self.temperature_spinbox.pack(side=tk.LEFT, padx=(0, 20))
        self.temperature_spinbox.bind("<Return>", lambda e: self.on_temperature_change())
        self.temperature_spinbox.bind("<FocusOut>", lambda e: self.on_temperature_change())
        
        # JSON输出模式
        self.json_output_var = tk.BooleanVar(value=False)
        self.json_output_check = tk.Checkbutton(
            self.options_frame,
            text="JSON Output",
            variable=self.json_output_var,
            command=self.on_json_output_change
        )
        self.json_output_check.pack(side=tk.LEFT, padx=(0, 20))
        
        # 最大token数
        tk.Label(self.options_frame, text="Max Tokens:").pack(side=tk.LEFT, padx=(0, 5))
        self.max_tokens_var = tk.IntVar(value=1000)
        self.max_tokens_spinbox = tk.Spinbox(
            self.options_frame,
            from_=1,
            to=100000,
            increment=100,
            textvariable=self.max_tokens_var,
            width=8,
            command=self.on_max_tokens_change
        )
        self.max_tokens_spinbox.pack(side=tk.LEFT, padx=(0, 20))
        
        # 思维链容器
        self.reasoning_container = tk.Frame(self.options_frame)
        self.reasoning_container.pack(side=tk.LEFT)
        self.reasoning_widget = None
        self.reasoning_var = None

    def create_tools_frame(self):
        self.tools_frame = tk.LabelFrame(self.root, text="Tool Management", padx=10, pady=5)
        self.tools_frame.grid(row=2, column=0, padx=10, pady=(5, 5), sticky="ew")
        self.tools_frame.grid_columnconfigure(1, weight=1) 
        
        tk.Label(self.tools_frame, text="Tool Groups:").grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=2)
        self.tool_groups_container = tk.Frame(self.tools_frame)
        self.tool_groups_container.grid(row=0, column=1, sticky="nw", pady=2)
        
        tk.Label(self.tools_frame, text="Enabled Tools:").grid(row=1, column=0, sticky="nw", padx=(0, 10), pady=2)
        self.tools_list_var = tk.StringVar()
        self.tools_list_label = tk.Label(
            self.tools_frame,
            textvariable=self.tools_list_var,
            fg="blue",
            font=("Microsoft YaHei", 9),
            wraplength=600,
            justify=tk.LEFT,
            anchor="w"
        )
        self.tools_list_label.grid(row=1, column=1, sticky="nw", pady=2)
        
        self.tool_control_frame = tk.Frame(self.tools_frame)
        self.tool_control_frame.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(10, 0))
        
        self.execute_tools_btn = tk.Button(
            self.tool_control_frame,
            text="Execute Tools",
            command=self.execute_pending_tools,
            state="disabled",
            width=12
        )
        self.execute_tools_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.send_tool_results_btn = tk.Button(
            self.tool_control_frame,
            text="Send Results",
            command=self.send_tool_results,
            state="disabled",
            width=12
        )
        self.send_tool_results_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.cancel_tools_btn = tk.Button(
            self.tool_control_frame,
            text="Cancel",
            command=self.cancel_tool_calls,
            state="disabled",
            width=8
        )
        self.cancel_tools_btn.pack(side=tk.LEFT)
        
        self.tool_group_vars = {}
    
    def update_tools_ui(self, state):
        for widget in self.tool_groups_container.winfo_children():
            widget.destroy()
            
        all_groups = state.get("all_tool_groups", [])
        enabled_groups = state.get("enabled_groups", [])
        
        self.tool_group_vars = {}
        
        for i, group_name in enumerate(all_groups):
            var = tk.BooleanVar(value=group_name in enabled_groups)
            self.tool_group_vars[group_name] = var
            
            check = tk.Checkbutton(
                self.tool_groups_container,
                text=group_name,
                variable=var,
                command=lambda g=group_name: self.on_tool_group_change(g)
            )
            check.grid(row=0, column=i, sticky="w", padx=(0, 10))
    
    def on_tool_group_change(self, group_name):
        enabled_groups = [name for name, var in self.tool_group_vars.items() if var.get()]
        self.send_cmd("tools", {"groups": enabled_groups})
        self.trigger_preview_update()
    
    def refresh_ui_options(self, state):
        constraints = state.get("constraints", {})
        options = state.get("options", {})

        temp_range = constraints.get("temperature_range", [0.0, 2.0])
        self.temperature_spinbox.config(from_=temp_range[0], to=temp_range[1])
        self.temperature_var.set(options.get("temperature", 0.7))
        self.max_tokens_var.set(options.get("max_tokens", 1000))
        
        json_supported = state.get("supported_features", {}).get("json_output", False)
        self.json_output_check.config(state="normal" if json_supported else "disabled")
        
        for widget in self.reasoning_container.winfo_children():
            widget.destroy()
            
        reasoning_config = constraints.get("reasoning", {})
        if reasoning_config:
            tk.Label(self.reasoning_container, text="Reasoning:").pack(side=tk.LEFT)
            
            if reasoning_config.get("type") == "boolean":
                val = options.get("reasoning", reasoning_config.get("default", False))
                if isinstance(val, str): val = val.lower() == "on"
                self.reasoning_var = tk.BooleanVar(value=val)
                self.reasoning_widget = tk.Checkbutton(
                    self.reasoning_container,
                    text="Enabled",
                    variable=self.reasoning_var,
                    command=self.on_reasoning_change
                )
                self.reasoning_widget.pack(side=tk.LEFT, padx=5)
            elif reasoning_config.get("type") == "enum":
                val = options.get("reasoning", reasoning_config.get("default", "off"))
                self.reasoning_var = tk.StringVar(value=val)
                self.reasoning_widget = ttk.Combobox(
                    self.reasoning_container,
                    textvariable=self.reasoning_var,
                    values=reasoning_config.get("values", []),
                    state="readonly",
                    width=10
                )
                self.reasoning_widget.pack(side=tk.LEFT, padx=5)
                self.reasoning_widget.bind("<<ComboboxSelected>>", self.on_reasoning_change)
    
    def create_output_area(self):
        self.output_area = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            state='disabled',
            bg="#1e1e1e",
            fg="#d4d4d4",
            font=("Microsoft YaHei", 10),
            height=16
        )
        self.output_area.grid(row=3, column=0, padx=10, pady=(5, 5), sticky="nsew")
        
        self.payload_label = tk.Label(
            self.root,
            text="Real-time API Payload Preview (Exactly as sent):",
            anchor="w",
            font=("Consolas", 9, "bold")
        )
        self.payload_label.grid(row=4, column=0, padx=10, sticky="ew")
        
        self.preview_area = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            state='disabled',
            bg="#252526",
            fg="#85c46c",
            font=("Consolas", 9),
            height=8
        )
        self.preview_area.grid(row=5, column=0, padx=10, pady=(0, 5), sticky="nsew")
        
        self.output_area.tag_config("payload", foreground="#6a9955")
        self.output_area.tag_config("user", foreground="#569cd6", font=("Microsoft YaHei", 10, "bold"))
        self.output_area.tag_config("assistant", foreground="#ce9178")
        self.output_area.tag_config("reasoning", foreground="#9cdcfe", font=("Microsoft YaHei", 9, "italic"))
        self.output_area.tag_config("reasoning_header", foreground="#d7ba7d", font=("Microsoft YaHei", 9, "bold"))
        self.output_area.tag_config("tool_call", foreground="#b5cea8", font=("Microsoft YaHei", 9, "bold"))
        self.output_area.tag_config("tool_result", foreground="#d7ba7d", font=("Microsoft YaHei", 9))
    
    def create_input_area(self):
        self.input_frame = tk.Frame(self.root)
        self.input_frame.grid(row=6, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        # --- 命令输入区域 ---
        self.cmd_frame = tk.Frame(self.input_frame)
        self.cmd_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.cmd_frame.grid_columnconfigure(1, weight=1)
        
        tk.Label(self.cmd_frame, text=">_ CLI Command:", font=("Consolas", 10, "bold"), fg="#00529B").grid(row=0, column=0, padx=(0, 5))
        self.cmd_entry = tk.Entry(self.cmd_frame, font=("Consolas", 10))
        self.cmd_entry.grid(row=0, column=1, sticky="ew")
        self.cmd_entry.bind("<Return>", lambda event: self.send_command())
        
        # --- 聊天输入区域 ---
        self.chat_input_frame = tk.Frame(self.input_frame)
        self.chat_input_frame.grid(row=1, column=0, sticky="ew")
        self.chat_input_frame.grid_columnconfigure(0, weight=1)
        
        self.input_area = tk.Text(self.chat_input_frame, height=5, font=("Microsoft YaHei", 10))
        self.input_area.grid(row=0, column=0, sticky="ew")
        self.input_area.bind("<Control-Return>", lambda event: self.send_message())
        self.input_area.bind("<KeyRelease>", self.trigger_preview_update)
        
        # --- 按钮区域 ---
        self.btn_frame = tk.Frame(self.input_frame)
        self.btn_frame.grid(row=1, column=1, padx=(10, 0), sticky="ns")
        
        self.send_btn = tk.Button(self.btn_frame, text="Send Chat", command=self.send_message, width=12)
        self.send_btn.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.clear_btn = tk.Button(self.btn_frame, text="Clear Context", command=self.clear_context, width=12)
        self.clear_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        self.save_btn = tk.Button(self.btn_frame, text="Save Chat", command=self.save_chat_context, width=12)
        self.save_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.load_btn = tk.Button(self.btn_frame, text="Load Chat", command=self.load_chat_context, width=12)
        self.load_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
    
    def send_command(self):
        cmd_text = self.cmd_entry.get().strip()
        if not cmd_text:
            return
        
        self.cmd_entry.delete(0, tk.END)
        self.log(f"\n> {cmd_text}\n", "user")
        self.send_cmd("raw", {"text": cmd_text})
    
    def on_provider_change(self, event=None):
        self.send_cmd("provider", {"provider": self.provider_var.get()})
        self.trigger_preview_update()
    
    def on_model_change(self, event=None):
        self.send_cmd("provider", {"provider": self.provider_var.get(), "model": self.model_var.get()})
        self.trigger_preview_update()
    
    def on_temperature_change(self, value=None):
        try:
            temp = float(self.temperature_var.get())
            self.send_cmd("option", {"key": "temperature", "value": temp})
            self.trigger_preview_update()
        except ValueError:
            pass
    
    def on_json_output_change(self):
        self.send_cmd("option", {"key": "json_output", "value": self.json_output_var.get()})
        self.trigger_preview_update()
    
    def on_reasoning_change(self, event=None):
        if self.reasoning_var:
            val = self.reasoning_var.get()
            if isinstance(val, bool):
                val = "on" if val else "off"
            self.send_cmd("option", {"key": "reasoning", "value": val})
            self.trigger_preview_update()
    
    def on_max_tokens_change(self):
        try:
            max_tokens = int(self.max_tokens_var.get())
            self.send_cmd("option", {"key": "max_tokens", "value": max_tokens})
            self.trigger_preview_update()
        except ValueError:
            pass
    
    def log(self, message, tag=None):
        self.output_area.configure(state='normal')
        self.output_area.insert(tk.END, message, tag)
        self.output_area.see(tk.END)
        self.output_area.configure(state='disabled')
    
    def trigger_preview_update(self, event=None):
        if self._preview_timer:
            self.root.after_cancel(self._preview_timer)
        user_input = self.input_area.get("1.0", tk.END).strip()
        self._preview_timer = self.root.after(300, lambda: self.send_cmd("get_payload", {"msg": user_input}))
        
    def update_preview_area(self, payload):
        self.preview_area.configure(state='normal')
        self.preview_area.delete("1.0", tk.END)
        self.preview_area.insert(tk.END, json.dumps(payload, indent=2, ensure_ascii=False))
        self.preview_area.configure(state='disabled')
    
    def clear_context(self):
        self.send_cmd("clear")
        self.output_area.configure(state='normal')
        self.output_area.delete("1.0", tk.END)
        self.output_area.configure(state='disabled')
        self.trigger_preview_update()
    
    def send_message(self):
        user_input = self.input_area.get("1.0", tk.END).strip()
        if not user_input:
            return

        self.input_area.delete("1.0", tk.END)
        self.log(f"\nYou: {user_input}\n", "user")
        self.log("--- Sending Request ---\n", "payload")
        
        self.send_btn.config(state="disabled")
        self.send_cmd("chat", {"msg": user_input})
    
    def execute_pending_tools(self):
        self.send_cmd("execute")
    
    def send_tool_results(self):
        self.log("\n[Tool Call Mode] 发送工具结果给agent...\n", "tool_call")
        self.send_tool_results_btn.config(state="disabled")
        self.send_cmd("send_results")
    
    def cancel_tool_calls(self):
        if messagebox.askyesno("取消工具调用", "确定要取消当前的工具调用吗？"):
            self.send_cmd("cancel_tools")
            self.trigger_preview_update()
    
    def save_chat_context(self):
        if self.current_state.get("tool_call_mode", False):
            messagebox.showerror("保存失败", "无法在思维链中途保存聊天记录")
            return
            
        save_dialog = tk.Toplevel(self.root)
        save_dialog.title("保存聊天记录")
        save_dialog.geometry("400x200")
        save_dialog.transient(self.root)
        save_dialog.grab_set()
        
        default_filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tk.Label(save_dialog, text="文件名:").pack(pady=(20, 5))
        filename_var = tk.StringVar(value=default_filename)
        filename_entry = tk.Entry(save_dialog, textvariable=filename_var, width=40)
        filename_entry.pack(pady=5)
        
        def do_save():
            filename = filename_var.get().strip()
            if not filename:
                messagebox.showerror("错误", "文件名不能为空")
                return
            self.send_cmd("save", {"filename": filename})
            save_dialog.destroy()
            messagebox.showinfo("请求已发送", f"保存请求已发送: {filename}.json")
        
        button_frame = tk.Frame(save_dialog)
        button_frame.pack(pady=20)
        tk.Button(button_frame, text="保存", command=do_save, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="取消", command=save_dialog.destroy, width=10).pack(side=tk.LEFT, padx=10)
    
    def load_chat_context(self):
        if self.current_state.get("tool_call_mode", False):
            messagebox.showerror("加载失败", "无法在思维链中途加载聊天记录")
            return
        self.send_cmd("list_contexts")
        
    def show_load_dialog(self, saved_contexts):
        if not saved_contexts:
            messagebox.showinfo("无聊天记录", "没有找到保存的聊天记录")
            return
            
        load_dialog = tk.Toplevel(self.root)
        load_dialog.title("加载聊天记录")
        load_dialog.geometry("600x500")
        load_dialog.transient(self.root)
        load_dialog.grab_set()
        
        tk.Label(load_dialog, text="选择要加载的聊天记录:", font=("Microsoft YaHei", 10, "bold")).pack(pady=10)
        
        list_frame = tk.Frame(load_dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        context_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=15)
        context_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=context_listbox.yview)
        
        for context in saved_contexts:
            display_text = f"{context['filename']} | {context['saved_at']} | {context['provider']} - {context['model']} | {context['message_count']} 条消息"
            context_listbox.insert(tk.END, display_text)
        
        detail_frame = tk.LabelFrame(load_dialog, text="详细信息", padx=10, pady=5)
        detail_frame.pack(fill=tk.X, padx=20, pady=10)
        detail_text = tk.Text(detail_frame, height=4, width=60, state='disabled')
        detail_text.pack(fill=tk.X, pady=5)
        
        def update_detail(event):
            selection = context_listbox.curselection()
            if selection:
                index = selection[0]
                context = saved_contexts[index]
                detail_text.config(state='normal')
                detail_text.delete("1.0", tk.END)
                detail_text.insert(tk.END, 
                    f"文件名: {context['filename']}\n"
                    f"保存时间: {context['saved_at']}\n"
                    f"提供商: {context['provider']}\n"
                    f"模型: {context['model']}\n"
                    f"消息数量: {context['message_count']} 条\n"
                    f"文件大小: {context['size_kb']:.1f} KB"
                )
                detail_text.config(state='disabled')
        
        context_listbox.bind("<<ListboxSelect>>", update_detail)
        
        button_frame = tk.Frame(load_dialog)
        button_frame.pack(pady=10)
        
        def do_load():
            selection = context_listbox.curselection()
            if not selection:
                messagebox.showerror("错误", "请选择要加载的聊天记录")
                return
            
            index = selection[0]
            context = saved_contexts[index]
            filename = context['filename']
            
            if messagebox.askyesno("确认加载", f"确定要加载聊天记录 '{filename}' 吗？\n这将覆盖当前的聊天上下文。"):
                self.send_cmd("load", {"filename": filename})
                self.trigger_preview_update()
                load_dialog.destroy()
        
        tk.Button(button_frame, text="加载", command=do_load, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="取消", command=load_dialog.destroy, width=10).pack(side=tk.LEFT, padx=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatGUIV2(root)
    root.mainloop()
