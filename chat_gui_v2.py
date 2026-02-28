"""
重构的ChatGUI类
支持根据提供商动态适配高级选项
"""
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import json
import traceback
import sys
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
        self.output_area.grid(row=2, column=0, padx=10, pady=(5, 5), sticky="nsew")
        
        # Payload预览标签
        self.payload_label = tk.Label(
            self.root,
            text="Real-time API Payload Preview (Exactly as sent):",
            anchor="w",
            font=("Consolas", 9, "bold")
        )
        self.payload_label.grid(row=3, column=0, padx=10, sticky="ew")
        
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
        self.preview_area.grid(row=4, column=0, padx=10, pady=(0, 5), sticky="nsew")
        
        # 样式标签
        self.output_area.tag_config("payload", foreground="#6a9955")
        self.output_area.tag_config("user", foreground="#569cd6", font=("Microsoft YaHei", 10, "bold"))
        self.output_area.tag_config("assistant", foreground="#ce9178")
        self.output_area.tag_config("reasoning", foreground="#9cdcfe", font=("Microsoft YaHei", 9, "italic"))
        self.output_area.tag_config("reasoning_header", foreground="#d7ba7d", font=("Microsoft YaHei", 9, "bold"))
    
    def create_input_area(self):
        """创建输入区域"""
        self.input_frame = tk.Frame(self.root)
        self.input_frame.grid(row=5, column=0, padx=10, pady=(0, 10), sticky="ew")
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
            self.log("\n[思维链过程]:\n", "reasoning_header")
            self.log(f"{reasoning_content}\n", "reasoning")
        
        # 显示最终答案
        self.log(f"Assistant: {final_answer}\n", "assistant")
        self.update_preview()
    
    def clear_context(self):
        """清空上下文"""
        self.chat_logic.clear_context()
        self.log("\n[System] Context cleared.\n")
        self.update_preview()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatGUIV2(root)
    root.mainloop()
