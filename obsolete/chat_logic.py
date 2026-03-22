import yaml
import json
import os
from openai import OpenAI
from google import genai

class ChatLogic:
    def __init__(self, config_path="api_keys.yaml"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, config_path)
        self.config = self._load_config()
        self.context = []
        self.current_provider = "deepseek"
        self.current_model = "deepseek-chat"
        self.client = None
        self._init_client()

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _init_client(self):
        provider_info = self.config['providers'][self.current_provider]
        env_var_name = provider_info['api_key']
        api_key = os.getenv(env_var_name)
        
        if not api_key:
            raise ValueError(f"Environment variable {env_var_name} not set.")

        if self.current_provider == "google":
            self.client = genai.Client(api_key=api_key)
        else:
            base_url = provider_info.get('base_url')
            if base_url == "N/A":
                base_url = None
            self.client = OpenAI(api_key=api_key, base_url=base_url)

    def set_provider(self, provider, model):
        if provider in self.config['providers']:
            self.current_provider = provider
            self.current_model = model
            self._init_client()

    def get_available_providers(self):
        return list(self.config['providers'].keys())

    def get_models_for_provider(self, provider):
        return self.config['providers'].get(provider, {}).get('models', [])

    def add_message(self, role, content):
        self.context.append({"role": role, "content": content})

    def clear_context(self): #清空上下文
        self.context = []

    def get_full_payload(self, user_input=""):
        """
        核心方法：构造即将发送给 API 的完整数据结构。
        如果提供了 user_input, 则将其视为对话的最后一条消息加入。
        """
        # 构造临时的上下文副本
        temp_messages = list(self.context)
        if user_input:
            temp_messages.append({"role": "user", "content": user_input})

        if self.current_provider == "google":
            # 严格对应 Google GenAI SDK 的 contents 格式
            gemini_contents = []
            for msg in temp_messages:
                role = "user" if msg["role"] == "user" else "model"
                gemini_contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            return {
                "model": self.current_model,
                "contents": gemini_contents
            }
        else:
            # 严格对应 OpenAI 风格的参数格式
            return {
                "model": self.current_model,
                "messages": temp_messages,
                "stream": False
            }

    def chat(self, user_input):
        # 获取本次请求的完整 Payload
        payload = self.get_full_payload(user_input)
        
        try:
            if self.current_provider == "google":
                # 使用 payload 中的数据直接调用
                response = self.client.models.generate_content(
                    model=payload["model"],
                    contents=payload["contents"]
                )
                assistant_message = response.text
            else:
                # 使用解包方式调用 OpenAI
                response = self.client.chat.completions.create(**payload)
                assistant_message = response.choices[0].message.content
            
            # 只有在 API 调用成功后才正式更新本地上下文
            self.add_message("user", user_input)
            self.add_message("assistant", assistant_message)
            return assistant_message, payload
        except Exception as e:
            return f"Error: {str(e)}", payload