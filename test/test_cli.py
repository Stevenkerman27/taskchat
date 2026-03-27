import subprocess
import json
import sys
import time
import os
import threading
from queue import Queue, Empty
import glob as py_glob

class NonBlockingStreamReader:
    def __init__(self, stream):
        self._s = stream
        self._q = Queue()
        self._t = threading.Thread(target=self._populateQueue, args=(self._s, self._q))
        self._t.daemon = True
        self._t.start()

    def _populateQueue(self, stream, queue):
        while True:
            line = stream.readline()
            if line:
                queue.put(line)
            else:
                break

    def readline(self, timeout=None):
        try:
            return self._q.get(block=timeout is not None, timeout=timeout)
        except Empty:
            return None

class CLITestBot:
    def __init__(self):
        print("=== 初始化 CLI 测试机器人 ===")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            [sys.executable, "chat_cli_v2.py", "--json"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=env,
            bufsize=1
        )
        self.stdout_reader = NonBlockingStreamReader(self.process.stdout)
        self.last_msg_time = time.time()

    def send_cmd(self, cmd_dict):
        cmd_str = json.dumps(cmd_dict, ensure_ascii=False) + "\n"
        self.process.stdin.write(cmd_str)
        self.process.stdin.flush()

    def get_json_msg(self, timeout=1):
        line = self.stdout_reader.readline(timeout=timeout)
        if not line: return None
        try:
            msg = json.loads(line)
            self.last_msg_time = time.time()
            return msg
        except json.JSONDecodeError:
            if line.strip(): print(f"[STDOUT] {line.strip()}")
            return None

    def wait_for_sys(self, part, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            msg = self.get_json_msg(timeout=1)
            if msg and msg.get('type') == 'sys':
                print(f"[SYS] {msg.get('content')}")
                if part in msg.get('content', ''): return True
        return False

    def chat_and_wait(self, prompt, timeout=120):
        print(f"\n[USER] {prompt}")
        self.send_cmd({"cmd": "chat", "args": {"msg": prompt}})
        
        start_time = time.time()
        assistant_done = False
        
        while time.time() - start_time < timeout:
            msg = self.get_json_msg(timeout=0.5)
            if not msg:
                # 如果 AI 已经发过话了，且队列空了，说明可能结束了
                if assistant_done:
                    time.sleep(2) # 留点余地
                    if self.stdout_reader._q.empty():
                        return True
                continue
            
            m_type = msg.get("type")
            content = msg.get("content")
            
            if m_type == "state": continue
            if m_type == "payload": continue
            
            if m_type == "sys":
                print(f"[SYS] {content}")
                continue
            
            if m_type == "assistant":
                print(f"[ASSISTANT] {content}")
                assistant_done = True
                if "Error" in str(content) or "失败" in str(content):
                    print("-> 检测到可能的消息错误")
            
            elif m_type == "tool_calls":
                print(f"[RECV] tool_calls: {content}")
                self.send_cmd({"cmd": "execute"})
                assistant_done = False # 重置，等待工具结果后的回答
            
            elif m_type == "tool_result":
                print(f"[RECV] tool_result received.")
                self.send_cmd({"cmd": "send_results"})
            
            elif m_type == "error":
                print(f"!!! Error: {content}")
                return False
                    
        print(f"Timeout ({timeout}s) waiting for response.")
        return assistant_done

    def stop(self):
        print("\n=== 停止测试机器人 ===")
        self.send_cmd({"cmd": "exit"})
        self.process.terminate()

def run_test():
    bot = CLITestBot()
    try:
        # --- 准备工作 ---
        print("\n[TEST] 0. 初始化配置")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/new"}})
        bot.wait_for_sys("New session started")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/provider Silicon_flow"}})
        bot.wait_for_sys("Switched to Silicon_flow")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/tools filesystem"}})
        bot.wait_for_sys("Active tools")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/option temperature 0.8"}})
        bot.wait_for_sys("Set option temperature = 0.8")

        # --- Phase 1: 文件操作 ---
        print("\n[TEST] 1. 基础文件操作 (write/read/replace)")
        prompt1 = "请创建一个文件 test/phase1.txt，内容为 'Initial Content'。然后将其中的 'Initial' 替换为 'Updated'。最后读取该文件内容告知我。"
        if not bot.chat_and_wait(prompt1):
            print("Phase 1 failed")

        # --- Phase 2: Session 保存与加载 ---
        print("\n[TEST] 2. Session 持久化")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/save test_session_auto"}})
        bot.wait_for_sys("Chat saved")
        
        bot.send_cmd({"cmd": "raw", "args": {"text": "/new"}})
        bot.wait_for_sys("New session started")
        
        bot.send_cmd({"cmd": "raw", "args": {"text": "/load test_session_auto.json"}})
        bot.wait_for_sys("Chat loaded")

        bot.send_cmd({"cmd": "raw", "args": {"text": "/tools basic,filesystem"}})
        bot.wait_for_sys("Active tools")
        
        prompt2 = "我们刚才在 test/phase1.txt 中写入了什么内容？请根据历史记录告诉我。"
        if not bot.chat_and_wait(prompt2):
            print("Phase 2 failed")

        # --- Phase 3: Glob & Grep ---
        print("\n[TEST] 3. Glob & Grep 测试")
        prompt3 = "请使用 glob 工具搜索.py文件。接着使用 grep_search 工具在 test/test_grep.txt 中搜索 'hapmemory'。"
        if not bot.chat_and_wait(prompt3):
            print("Phase 3 failed")

        # --- Phase 4: Shell 测试 ---
        print("\n[TEST] 4. Shell 工具测试 (切换工具组)")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/tools basic"}})
        bot.wait_for_sys("Active tools")
        
        prompt4 = "请使用 run_shell_command 工具在 shell 中打印 'hello world'。"
        if not bot.chat_and_wait(prompt4):
            print("Phase 4 failed")

        # --- Phase 5: Deepseek & Git ---
        print("\n[TEST] 5. Deepseek Provider & Git Status")
        bot.send_cmd({"cmd": "raw", "args": {"text": "/provider deepseek deepseek-chat"}})
        bot.wait_for_sys("Switched to deepseek")
        
        prompt5 = "请使用 ls 工具列出当前目录。然后使用 run_shell_command 工具执行 'git status'。"
        if not bot.chat_and_wait(prompt5):
            print("Phase 5 failed")

        print("\n=== 所有测试步骤已发送完毕 ===")

    except Exception as e:
        print(f"测试执行异常: {e}")
    finally:
        bot.stop()

if __name__ == "__main__":
    run_test()
