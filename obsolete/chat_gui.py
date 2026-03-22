import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
import json
import traceback
import sys
from chat_logic import ChatLogic

class ChatGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Model Chat GUI")
        try:
            self.chat_logic = ChatLogic()
        except Exception as e:
            messagebox.showerror("Initialization Error", f"Failed to initialize ChatLogic:\n{str(e)}")
            sys.exit(1)

        # 布局配置
        self.root.grid_rowconfigure(1, weight=3)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Config Frame
        self.config_frame = tk.Frame(root)
        self.config_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        
        tk.Label(self.config_frame, text="Provider:").pack(side=tk.LEFT)
        self.provider_var = tk.StringVar(value=self.chat_logic.current_provider)
        self.provider_combo = ttk.Combobox(self.config_frame, textvariable=self.provider_var, 
                                          values=self.chat_logic.get_available_providers(), state="readonly", width=15)
        self.provider_combo.pack(side=tk.LEFT, padx=5)
        self.provider_combo.bind("<<ComboboxSelected>>", self.on_provider_change)

        tk.Label(self.config_frame, text="Model:").pack(side=tk.LEFT, padx=(10, 0))
        self.model_var = tk.StringVar(value=self.chat_logic.current_model)
        self.model_combo = ttk.Combobox(self.config_frame, textvariable=self.model_var, 
                                       values=self.chat_logic.get_models_for_provider(self.provider_var.get()), 
                                       state="readonly", width=25)
        self.model_combo.pack(side=tk.LEFT, padx=5)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_change)

        # Output & Preview 区域
        self.output_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state='disabled', bg="#1e1e1e", fg="#d4d4d4", font=("Microsoft YaHei", 10))
        self.output_area.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")
        
        self.payload_label = tk.Label(root, text="Real-time API Payload Preview (Exactly as sent):", anchor="w", font=("Consolas", 9, "bold"))
        self.payload_label.grid(row=2, column=0, padx=10, sticky="ew")
        self.preview_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state='disabled', bg="#252526", fg="#85c46c", font=("Consolas", 9), height=8)
        self.preview_area.grid(row=2, column=0, padx=10, pady=(20, 5), sticky="nsew")

        # 样式标签
        self.output_area.tag_config("payload", foreground="#6a9955")
        self.output_area.tag_config("user", foreground="#569cd6", font=("Microsoft YaHei", 10, "bold"))
        self.output_area.tag_config("assistant", foreground="#ce9178")

        # 输入区域
        self.input_frame = tk.Frame(root)
        self.input_frame.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.input_area = tk.Text(self.input_frame, height=4, font=("Microsoft YaHei", 10))
        self.input_area.grid(row=0, column=0, sticky="ew")
        self.input_area.bind("<Control-Return>", lambda event: self.send_message())
        self.input_area.bind("<KeyRelease>", lambda event: self.update_preview())

        # 按钮
        self.btn_frame = tk.Frame(self.input_frame)
        self.btn_frame.grid(row=0, column=1, padx=(10, 0), sticky="ns")

        self.send_btn = tk.Button(self.btn_frame, text="Send\n(Ctrl+Enter)", command=self.send_message, width=12)
        self.send_btn.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.clear_btn = tk.Button(self.btn_frame, text="Clear Context", command=self.clear_context, width=12)
        self.clear_btn.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        self.log(f"System initialized. {self.chat_logic.current_provider} - {self.chat_logic.current_model}\n")
        self.update_preview()

    def on_provider_change(self, event=None):
        provider = self.provider_var.get()
        models = self.chat_logic.get_models_for_provider(provider)
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])
            self.on_model_change()

    def on_model_change(self, event=None):
        self.chat_logic.set_provider(self.provider_var.get(), self.model_var.get())
        self.log(f"\n[System] Switched to {self.chat_logic.current_provider} - {self.chat_logic.current_model}\n")
        self.update_preview()

    def log(self, message, tag=None):
        self.output_area.configure(state='normal')
        self.output_area.insert(tk.END, message, tag)
        self.output_area.see(tk.END)
        self.output_area.configure(state='disabled')

    def update_preview(self, event=None):
        user_input = self.input_area.get("1.0", tk.END).strip()
        # 直接获取逻辑层构造的真实 Payload
        payload = self.chat_logic.get_full_payload(user_input)
        
        self.preview_area.configure(state='normal')
        self.preview_area.delete("1.0", tk.END)
        self.preview_area.insert(tk.END, json.dumps(payload, indent=2, ensure_ascii=False))
        self.preview_area.configure(state='disabled')

    def send_message(self):
        user_input = self.input_area.get("1.0", tk.END).strip()
        if not user_input:
            return

        self.input_area.delete("1.0", tk.END)
        self.log(f"\nYou: {user_input}\n", "user")
        self.log("--- Sending Request ---\n", "payload")
        self.root.update_idletasks()

        # 发送请求，获取结果和当时发送的内容
        response, payload = self.chat_logic.chat(user_input)
        
        self.log(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "payload")
        self.log("--------------------\n", "payload")
        self.log(f"Assistant: {response}\n", "assistant")
        self.update_preview()

    def clear_context(self): #调用logic的clear_context
        self.chat_logic.clear_context()
        self.log("\n[System] Context cleared.\n")
        self.update_preview()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatGUI(root)
    root.mainloop()