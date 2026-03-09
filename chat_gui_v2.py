"""
重构的ChatGUI类
支持根据提供商动态适配高级选项和工具调用
"""
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import json
import traceback
import sys
import datetime
from chat_logic_v2 import ChatLogicV2


class ChatGUIV2:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Model Chat GUI v2 - Architecture Optimized")
        
        try:
            self.chat_logic = ChatLogicV2()
        except Exception as e:
            messagebox.showerror("Initialization Error", f"Failed to initialize ChatLogicV2:\n{str(e)}")
            sys.exit(1)
        
        # 布局配置
        self.root.grid_rowconfigure(2, weight=3)
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        
        # 创建UI组件
        self.create_config_frame()
        self.create_advanced_options_frame()
        self.create_tools_frame()
        self.create_output_area()
        self.create_input_area()
        
        # 初始化状态
        self.log(f"System initialized. {self.chat_logic.get_current_provider()} - {self.chat_logic.get_current_model()}\n")
        self.refresh_ui_options()
        self.update_preview()
    
    def create_config_frame(self):
        """创建配置框架"""
        self.config_frame = tk.Frame(self.root)
        self.config_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        
        # 提供商选择
        tk.Label(self.config_frame, text="Provider:").pack(side=tk.LEFT)
        self.provider_var = tk.StringVar(value=self.chat_logic.get_current_provider())
        self.provider_combo = ttk.Combobox(
            self.config_frame, 
            textvariable=self.provider_var,
            values=self.chat_logic.get_available_providers(),
            state="readonly",
            width=15
        )
        self.provider_combo.pack(side=tk.LEFT, padx=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)
        
        # 模型选择
        tk.Label(self.config_frame, text="Model:").pack(side=tk.LEFT, padx=(10, 0))
        self.model_var = tk.StringVar(value=self.chat_logic.get_current_model())
        self.model_combo = ttk.Combobox(
            self.config_frame,
            textvariable=self.model_var,
            values=self.chat_logic.get_models_for_provider(self.provider_var.get()),
            state="readonly",
            width=25
        )
        self.model_combo.pack(side=tk.LEFT, padx=5)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_change)
    
    def create_advanced_options_frame(self):
        """创建高级选项框架"""
        self.options_frame = tk.LabelFrame(self.root, text="Advanced Options", padx=10, pady=5)
        self.options_frame.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="ew")
        
        # 温度设置
        tk.Label(self.options_frame, text="Temperature:").grid(row=0, column=0, sticky="w")
        self.temperature_var = tk.DoubleVar(value=0.7)
        self.temperature_scale = tk.Scale(
            self.options_frame,
            from_=0.0,
            to=2.0,
            resolution=0.1,
            orient=tk.HORIZONTAL,
            variable=self.temperature_var,
            length=200,
            command=self.on_temperature_change
        )
        self.temperature_scale.grid(row=0, column=1, padx=(5, 20), sticky="w")
        
        # 温度值显示
        self.temperature_label = tk.Label(self.options_frame, text="0.7")
        self.temperature_label.grid(row=0, column=2, sticky="w")
        
        # JSON输出模式
        self.json_output_var = tk.BooleanVar(value=False)
        self.json_output_check = tk.Checkbutton(
            self.options_frame,
            text="JSON Output",
            variable=self.json_output_var,
            command=self.on_json_output_change
        )
        self.json_output_check.grid(row=0, column=3, padx=(20, 10), sticky="w")
        
        # 最大token数
        tk.Label(self.options_frame, text="Max Tokens:").grid(row=1, column=2, sticky="w", pady=(10, 0))
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
        self.max_tokens_spinbox.grid(row=1, column=3, padx=(5, 10), pady=(10, 0), sticky="w")
        
        # 思维链容器
        self.reasoning_container = tk.Frame(self.options_frame)
        self.reasoning_container.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.reasoning_widget = None
        self.reasoning_var = None

    def create_tools_frame(self):
        """创建工具管理框架"""
        self.tools_frame = tk.LabelFrame(self.root, text="Tool Management", padx=10, pady=5)
        self.tools_frame.grid(row=2, column=0, padx=10, pady=(5, 5), sticky="ew")
        
        # 工具启用状态
        self.tools_enabled_var = tk.BooleanVar(value=True)
        self.tools_enabled_check = tk.Checkbutton(
            self.tools_frame,
            text="Enable Tools",
            variable=self.tools_enabled_var,
            command=self.on_tools_enabled_change
        )
        self.tools_enabled_check.pack(side=tk.LEFT, padx=(0, 20))
        
        # 工具列表标签
        tk.Label(self.tools_frame, text="Enabled Tools:").pack(side=tk.LEFT)
        
        # 工具列表显示
        self.tools_list_var = tk.StringVar()
        self.tools_list_label = tk.Label(
            self.tools_frame,
            textvariable=self.tools_list_var,
            fg="blue",
            font=("Microsoft YaHei", 9)
        )
        self.tools_list_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # 工具调用控制按钮框架
        self.tool_control_frame = tk.Frame(self.tools_frame)
        self.tool_control_frame.pack(side=tk.RIGHT, padx=(10, 0))
        
        # 执行工具按钮
        self.execute_tools_btn = tk.Button(
            self.tool_control_frame,
            text="Execute Tools",
            command=self.execute_pending_tools,
            state="disabled",
            width=12
        )
        self.execute_tools_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 发送工具结果按钮
        self.send_tool_results_btn = tk.Button(
            self.tool_control_frame,
            text="Send Results",
            command=self.send_tool_results,
            state="disabled",
            width=12
        )
        self.send_tool_results_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 取消工具调用按钮
        self.cancel_tools_btn = tk.Button(
            self.tool_control_frame,
            text="Cancel",
            command=self.cancel_tool_calls,
            state="disabled",
            width=8
        )
        self.cancel_tools_btn.pack(side=tk.LEFT)
        
        # 刷新工具列表
        self.refresh_tools_list()
    
    def refresh_tools_list(self):
        """刷新工具列表显示"""
        if self.tools_enabled_var.get():
            enabled_tools = self.chat_logic.get_enabled_tools()
            if enabled_tools:
                self.tools_list_var.set(", ".join(enabled_tools))
            else:
                self.tools_list_var.set("No tools enabled")
        else:
            self.tools_list_var.set("Tools disabled")
    
    def refresh_ui_options(self):
        """根据当前提供商刷新UI选项"""
        constraints = self.chat_logic.get_option_constraints()
        defaults = self.chat_logic.get_default_options()
        
        # 更新温度范围
        temp_range = constraints.get("temperature_range", [0.0, 2.0])
        self.temperature_scale.config(from_=temp_range[0], to=temp_range[1])
        self.temperature_var.set(defaults.temperature or 0.7)
        self.temperature_label.config(text=f"{self.temperature_var.get():.1f}")
        
        # 更新最大token
        self.max_tokens_var.set(defaults.max_tokens or 1000)
        
        # 更新JSON支持
        json_supported = self.chat_logic.supports_feature("json_output")
        self.json_output_check.config(state="normal" if json_supported else "disabled")
        
        # 更新工具支持
        tools_supported = self.chat_logic.supports_feature("tools")
        self.tools_enabled_check.config(state="normal" if tools_supported else "disabled")
        
        # 动态创建思维链控件
        for widget in self.reasoning_container.winfo_children():
            widget.destroy()
            
        reasoning_config = constraints.get("reasoning", {})
        if reasoning_config:
            tk.Label(self.reasoning_container, text="Reasoning:").pack(side=tk.LEFT)
            
            if reasoning_config.get("type") == "boolean":
                self.reasoning_var = tk.BooleanVar(value=reasoning_config.get("default", False))
                self.reasoning_widget = tk.Checkbutton(
                    self.reasoning_container,
                    text="Enabled",
                    variable=self.reasoning_var,
                    command=self.on_reasoning_change
                )
                self.reasoning_widget.pack(side=tk.LEFT, padx=5)
            elif reasoning_config.get("type") == "enum":
                self.reasoning_var = tk.StringVar(value=reasoning_config.get("default", "off"))
                self.reasoning_widget = ttk.Combobox(
                    self.reasoning_container,
                    textvariable=self.reasoning_var,
                    values=reasoning_config.get("values", []),
                    state="readonly",
                    width=10
                )
                self.reasoning_widget.pack(side=tk.LEFT, padx=5)
                self.reasoning_widget.bind("<<ComboboxSelected>>", self.on_reasoning_change)
        
        # 同步逻辑层的选项
        self.chat_logic.set_option("temperature", self.temperature_var.get())
        self.chat_logic.set_option("max_tokens", self.max_tokens_var.get())
        if self.reasoning_var:
             val = self.reasoning_var.get()
             # 如果是布尔值，转换为字符串用于统一处理
             if isinstance(val, bool):
                 val = "on" if val else "off"
             self.chat_logic.set_option("reasoning", val)
        
        # 同步工具启用状态
        self.on_tools_enabled_change()
    
    def create_output_area(self):
        """创建输出和预览区域"""
        # 聊天输出区域
        self.output_area = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            state='disabled',
            bg="#1e1e1e",
            fg="#d4d4d4",
            font=("Microsoft YaHei", 10)
        )
        self.output_area.grid(row=3, column=0, padx=10, pady=(5, 5), sticky="nsew")
        
        # Payload预览标签
        self.payload_label = tk.Label(
            self.root,
            text="Real-time API Payload Preview (Exactly as sent):",
            anchor="w",
            font=("Consolas", 9, "bold")
        )
        self.payload_label.grid(row=4, column=0, padx=10, sticky="ew")
        
        # Payload预览区域
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
        
        # 样式标签
        self.output_area.tag_config("payload", foreground="#6a9955")
        self.output_area.tag_config("user", foreground="#569cd6", font=("Microsoft YaHei", 10, "bold"))
        self.output_area.tag_config("assistant", foreground="#ce9178")
        self.output_area.tag_config("reasoning", foreground="#9cdcfe", font=("Microsoft YaHei", 9, "italic"))
        self.output_area.tag_config("reasoning_header", foreground="#d7ba7d", font=("Microsoft YaHei", 9, "bold"))
        self.output_area.tag_config("tool_call", foreground="#b5cea8", font=("Microsoft YaHei", 9, "bold"))
        self.output_area.tag_config("tool_result", foreground="#d7ba7d", font=("Microsoft YaHei", 9))
    
    def create_input_area(self):
        """创建输入区域"""
        self.input_frame = tk.Frame(self.root)
        self.input_frame.grid(row=6, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        # 输入文本框
        self.input_area = tk.Text(self.input_frame, height=4, font=("Microsoft YaHei", 10))
        self.input_area.grid(row=0, column=0, sticky="ew")
        self.input_area.bind("<Control-Return>", lambda event: self.send_message())
        self.input_area.bind("<KeyRelease>", lambda event: self.update_preview())
        
        # 按钮框架
        self.btn_frame = tk.Frame(self.input_frame)
        self.btn_frame.grid(row=0, column=1, padx=(10, 0), sticky="ns")
        
        # 发送按钮
        self.send_btn = tk.Button(
            self.btn_frame,
            text="Send\n(Ctrl+Enter)",
            command=self.send_message,
            width=12
        )
        self.send_btn.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # 清空上下文按钮
        self.clear_btn = tk.Button(
            self.btn_frame,
            text="Clear Context",
            command=self.clear_context,
            width=12
        )
        self.clear_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        # 保存聊天记录按钮
        self.save_btn = tk.Button(
            self.btn_frame,
            text="Save Chat",
            command=self.save_chat_context,
            width=12
        )
        self.save_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # 加载聊天记录按钮
        self.load_btn = tk.Button(
            self.btn_frame,
            text="Load Chat",
            command=self.load_chat_context,
            width=12
        )
        self.load_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))
    
    def on_provider_change(self, event=None):
        """提供商变更处理"""
        provider = self.provider_var.get()
        models = self.chat_logic.get_models_for_provider(provider)
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])
            self.on_model_change()
    
    def on_model_change(self, event=None):
        """模型变更处理"""
        try:
            self.chat_logic.set_provider(self.provider_var.get(), self.model_var.get())
            self.log(f"\n[System] Switched to {self.chat_logic.get_current_provider()} - {self.chat_logic.get_current_model()}\n")
            
            # 刷新UI选项
            self.refresh_ui_options()
            self.update_preview()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to switch provider/model:\n{str(e)}")
            traceback.print_exc()
    
    def on_temperature_change(self, value):
        """温度变更处理"""
        try:
            temperature = float(value)
            self.temperature_label.config(text=f"{temperature:.1f}")
            self.chat_logic.set_option("temperature", temperature)
            self.update_preview()
        except ValueError:
            pass
    
    def on_json_output_change(self):
        """JSON输出模式变更处理"""
        self.chat_logic.set_option("json_output", self.json_output_var.get())
        self.update_preview()
    
    def on_reasoning_change(self, event=None):
        """思维链变更处理"""
        if self.reasoning_var:
            val = self.reasoning_var.get()
            if isinstance(val, bool):
                val = "on" if val else "off"
            self.chat_logic.set_option("reasoning", val)
            self.update_preview()
    
    def on_max_tokens_change(self):
        """最大token数变更处理"""
        try:
            max_tokens = int(self.max_tokens_var.get())
            self.chat_logic.set_option("max_tokens", max_tokens)
            self.update_preview()
        except ValueError:
            pass
    
    def on_tools_enabled_change(self):
        """工具启用状态变更处理"""
        if self.tools_enabled_var.get():
            # 启用工具
            self.chat_logic.set_option("tools_enabled", True)
            # 重新加载工具配置
            self.chat_logic._load_tools_to_options()
        else:
            # 禁用工具
            self.chat_logic.set_option("tools_enabled", False)
            self.chat_logic.options.tools = None
        
        self.refresh_tools_list()
        self.update_preview()
    
    def log(self, message, tag=None):
        """记录消息到输出区域"""
        self.output_area.configure(state='normal')
        self.output_area.insert(tk.END, message, tag)
        self.output_area.see(tk.END)
        self.output_area.configure(state='disabled')
    
    def update_preview(self, event=None):
        """更新payload预览"""
        try:
            user_input = self.input_area.get("1.0", tk.END).strip()
            payload = self.chat_logic.get_full_payload(user_input)
            
            self.preview_area.configure(state='normal')
            self.preview_area.delete("1.0", tk.END)
            self.preview_area.insert(tk.END, json.dumps(payload, indent=2, ensure_ascii=False))
            self.preview_area.configure(state='disabled')
        except Exception as e:
            # 预览出错不弹窗，只在控制台打印
            print(f"Preview update error: {e}")
    
    def clear_context(self):
        """清空聊天上下文"""
        self.chat_logic.clear_context()
        self.output_area.configure(state='normal')
        self.output_area.delete("1.0", tk.END)
        self.output_area.configure(state='disabled')
        self.log(f"[System] Context cleared. {self.chat_logic.get_current_provider()} - {self.chat_logic.get_current_model()}\n")
    
    def send_message(self):
        """发送消息"""
        user_input = self.input_area.get("1.0", tk.END).strip()
        if not user_input:
            return

        self.input_area.delete("1.0", tk.END)
        self.log(f"\nYou: {user_input}\n", "user")
        self.log("--- Sending Request ---\n", "payload")
        self.root.update_idletasks()

        # 发送请求
        final_answer, reasoning_content, payload = self.chat_logic.chat(user_input)

        # 显示payload
        self.log(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "payload")
        self.log("--------------------\n", "payload")

        # 显示思维链内容（如果存在）
        if reasoning_content:
            self.log("\n[Reasoning]\n", "reasoning_header")
            self.log(f"{reasoning_content}\n", "reasoning")
        
        # 检查是否进入工具调用模式
        if self.chat_logic.is_in_tool_call_mode():
            # 显示工具调用信息
            pending_tools = self.chat_logic.get_pending_tool_calls()
            self.log(f"\n[Tool Call Mode] 检测到 {len(pending_tools)} 个工具调用:\n", "tool_call")
            
            for i, tool_call in enumerate(pending_tools, 1):
                self.log(f"  {i}. {tool_call['function_name']}\n", "tool_call")
                self.log(f"     参数: {json.dumps(tool_call['arguments'], indent=2, ensure_ascii=False)}\n", "tool_call")
            
            self.log("\n请使用工具管理区域的按钮执行工具并发送结果。\n", "tool_call")
            
            # 更新按钮状态
            self.execute_tools_btn.config(state="normal")
            self.send_tool_results_btn.config(state="disabled")
            self.cancel_tools_btn.config(state="normal")
            self.send_btn.config(state="disabled")
        else:
            # 显示最终答案
            self.log(f"\nAssistant: {final_answer}\n", "assistant")
            
            # 确保按钮状态正常
            self.execute_tools_btn.config(state="disabled")
            self.send_tool_results_btn.config(state="disabled")
            self.cancel_tools_btn.config(state="disabled")
            self.send_btn.config(state="normal")
    
    def execute_pending_tools(self):
        """执行待处理的工具调用"""
        try:
            # 执行工具
            executed_tools = self.chat_logic.execute_pending_tools()
            
            # 显示执行结果
            self.log(f"\n[Tool Execution] 执行了 {len(executed_tools)} 个工具:\n", "tool_result")
            
            for i, tool_result in enumerate(executed_tools, 1):
                if "error" in tool_result:
                    self.log(f"  {i}. ❌ {tool_result['function_name']}: {tool_result['error']}\n", "tool_result")
                else:
                    self.log(f"  {i}. ✅ {tool_result['function_name']}\n", "tool_result")
                    # 显示工具结果（截断以避免过长）
                    result_str = str(tool_result['result'])
                    if len(result_str) > 500:
                        result_str = result_str[:500] + "..."
                    self.log(f"     结果: {result_str}\n", "tool_result")
            
            # 检查是否所有工具都已执行
            pending_tools = self.chat_logic.get_pending_tool_calls()
            all_executed = all(tool_call["executed"] for tool_call in pending_tools)
            
            if all_executed:
                self.log("\n所有工具已执行完成，请点击'发送结果'按钮将结果发送给agent。\n", "tool_result")
                self.send_tool_results_btn.config(state="normal")
            else:
                self.log(f"\n还有 {len([t for t in pending_tools if not t['executed']])} 个工具待执行。\n", "tool_result")
                
        except Exception as e:
            messagebox.showerror("工具执行错误", f"执行工具时发生错误:\n{str(e)}")
    
    def send_tool_results(self):
        """发送工具结果给agent"""
        try:
            self.log("\n[Tool Call Mode] 发送工具结果给agent...\n", "tool_call")
            self.root.update_idletasks()
            
            # 发送工具结果
            final_answer, reasoning_content, payload = self.chat_logic.send_tool_results_to_agent()
            
            # 显示payload
            self.log(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "payload")
            self.log("--------------------\n", "payload")
            
            # 显示思维链内容（如果存在）
            if reasoning_content:
                self.log("\n[Reasoning]\n", "reasoning_header")
                self.log(f"{reasoning_content}\n", "reasoning")
            
            # 显示最终答案
            self.log(f"\nAssistant: {final_answer}\n", "assistant")
            
            # 重置按钮状态
            self.execute_tools_btn.config(state="disabled")
            self.send_tool_results_btn.config(state="disabled")
            self.cancel_tools_btn.config(state="disabled")
            self.send_btn.config(state="normal")
            
        except Exception as e:
            messagebox.showerror("发送工具结果错误", f"发送工具结果时发生错误:\n{str(e)}")
    
    def cancel_tool_calls(self):
        """取消工具调用"""
        if messagebox.askyesno("取消工具调用", "确定要取消当前的工具调用吗？"):
            self.chat_logic.cancel_tool_calls()
            self.log("\n[Tool Call Mode] 工具调用已取消，恢复正常聊天模式。\n", "tool_call")
            
            # 重置按钮状态
            self.execute_tools_btn.config(state="disabled")
            self.send_tool_results_btn.config(state="disabled")
            self.cancel_tools_btn.config(state="disabled")
            self.send_btn.config(state="normal")
    
    def save_chat_context(self):
        """保存聊天上下文到文件"""
        try:
            # 检查是否处于思维链模式
            if self.chat_logic.is_in_reasoning_mode():
                messagebox.showerror("保存失败", "无法在思维链中途保存聊天记录")
                return
            
            # 创建保存对话框
            save_dialog = tk.Toplevel(self.root)
            save_dialog.title("保存聊天记录")
            save_dialog.geometry("400x200")
            save_dialog.transient(self.root)
            save_dialog.grab_set()
            
            # 默认文件名：当前日期时间
            default_filename = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 文件名输入框
            tk.Label(save_dialog, text="文件名:").pack(pady=(20, 5))
            filename_var = tk.StringVar(value=default_filename)
            filename_entry = tk.Entry(save_dialog, textvariable=filename_var, width=40)
            filename_entry.pack(pady=5)
            
            # 信息显示
            info_label = tk.Label(save_dialog, text=f"当前有 {len(self.chat_logic.messages)} 条消息")
            info_label.pack(pady=5)
            
            def do_save():
                filename = filename_var.get().strip()
                if not filename:
                    messagebox.showerror("错误", "文件名不能为空")
                    return
                
                # 保存聊天记录
                success = self.chat_logic.save_context_to_file(filename)
                
                if success:
                    self.log(f"\n[System] 聊天记录已保存: {filename}.json\n")
                    messagebox.showinfo("保存成功", f"聊天记录已保存为: {filename}.json")
                    save_dialog.destroy()
                else:
                    messagebox.showerror("保存失败", "保存聊天记录失败")
            
            # 按钮框架
            button_frame = tk.Frame(save_dialog)
            button_frame.pack(pady=20)
            
            tk.Button(button_frame, text="保存", command=do_save, width=10).pack(side=tk.LEFT, padx=10)
            tk.Button(button_frame, text="取消", command=save_dialog.destroy, width=10).pack(side=tk.LEFT, padx=10)
            
        except Exception as e:
            messagebox.showerror("保存错误", f"保存聊天记录时发生错误:\n{str(e)}")
    
    def load_chat_context(self):
        """从文件加载聊天上下文"""
        try:
            # 检查是否处于思维链模式
            if self.chat_logic.is_in_reasoning_mode():
                messagebox.showerror("加载失败", "无法在思维链中途加载聊天记录")
                return
            
            # 获取保存的聊天记录列表
            saved_contexts = self.chat_logic.list_saved_contexts()
            
            if not saved_contexts:
                messagebox.showinfo("无聊天记录", "没有找到保存的聊天记录")
                return
            
            # 创建加载对话框
            load_dialog = tk.Toplevel(self.root)
            load_dialog.title("加载聊天记录")
            load_dialog.geometry("600x500")
            load_dialog.transient(self.root)
            load_dialog.grab_set()
            
            # 标题
            tk.Label(load_dialog, text="选择要加载的聊天记录:", font=("Microsoft YaHei", 10, "bold")).pack(pady=10)
            
            # 创建列表框
            list_frame = tk.Frame(load_dialog)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
            
            # 滚动条
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 列表框
            context_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=15)
            context_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=context_listbox.yview)
            
            # 添加聊天记录到列表框
            for context in saved_contexts:
                display_text = f"{context['filename']} | {context['saved_at']} | {context['provider']} - {context['model']} | {context['message_count']} 条消息"
                context_listbox.insert(tk.END, display_text)
            
            # 详细信息显示区域
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
            
            # 按钮框架
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
                
                # 确认加载
                if not messagebox.askyesno("确认加载", f"确定要加载聊天记录 '{filename}' 吗？\n这将覆盖当前的聊天上下文。"):
                    return
                
                # 加载聊天记录
                try:
                    success = self.chat_logic.load_context_from_file(filename)
                    
                    if success:
                        # 清空输出区域并显示加载的消息
                        self.output_area.config(state='normal')
                        self.output_area.delete("1.0", tk.END)
                        self.output_area.config(state='disabled')
                        
                        self.log(f"[System] 已加载聊天记录: {filename}\n")
                        self.log(f"[System] 包含 {context['message_count']} 条消息\n")
                        self.log(f"[System] 提供商: {context['provider']} - 模型: {context['model']}\n")
                        
                        # 显示加载的消息
                        if self.chat_logic.messages:
                            self.log("\n--- 加载的聊天记录 ---\n")
                            for i, msg in enumerate(self.chat_logic.messages, 1):
                                role_display = "用户" if msg.role == "user" else "助手"
                                # 安全地获取消息内容预览
                                try:
                                    if hasattr(msg, 'content') and msg.content:
                                        # 如果是MessagePart列表，提取文本内容
                                        if isinstance(msg.content, list) and len(msg.content) > 0:
                                            first_part = msg.content[0]
                                            if hasattr(first_part, 'content'):
                                                content_preview = str(first_part.content)
                                            else:
                                                content_preview = str(first_part)
                                        else:
                                            content_preview = str(msg.content)
                                    else:
                                        content_preview = "[无内容]"
                                except Exception as e:
                                    content_preview = f"[内容获取错误: {e}]"
                                
                                # 显示完整内容，不截断
                                self.log(f"{i}. [{role_display}] {content_preview}\n")
                            self.log("--- 结束 ---\n")
                        
                        messagebox.showinfo("加载成功", f"聊天记录 '{filename}' 加载成功")
                        load_dialog.destroy()
                    else:
                        messagebox.showerror("加载失败", "加载聊天记录失败")
                except Exception as e:
                    # 提供更详细的错误信息
                    error_msg = str(e)
                    if "JSON格式错误" in error_msg or "JSON解析错误" in error_msg:
                        error_msg = f"文件格式错误: {error_msg}\n\n文件可能已损坏或不完整。"
                    messagebox.showerror("加载失败", f"加载聊天记录时发生错误:\n{error_msg}")
            
            tk.Button(button_frame, text="加载", command=do_load, width=10).pack(side=tk.LEFT, padx=10)
            tk.Button(button_frame, text="取消", command=load_dialog.destroy, width=10).pack(side=tk.LEFT, padx=10)
            
        except Exception as e:
            messagebox.showerror("加载错误", f"加载聊天记录时发生错误:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatGUIV2(root)
    root.mainloop()
           