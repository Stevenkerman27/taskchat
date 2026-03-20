import subprocess
import json
import sys
import time
import os
import threading
from queue import Queue, Empty

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

def test_cli():
    print("=== 开始测试 CLI 功能 (异步观察模式) ===")
    
    test_file = "test/test_write.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("你好世界")
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        [sys.executable, "chat_cli_v2.py", "--json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        bufsize=1
    )

    stdout_reader = NonBlockingStreamReader(process.stdout)

    def send_cmd(cmd_dict):
        cmd_str = json.dumps(cmd_dict, ensure_ascii=False) + "\n"
        process.stdin.write(cmd_str)
        process.stdin.flush()

    def get_json_msg(timeout=1):
        line = stdout_reader.readline(timeout=timeout)
        if not line: return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            if line.strip(): print(f"[STDOUT] {line.strip()}")
            return None

    def wait_for_sys(part, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            msg = get_json_msg(timeout=1)
            if msg and msg.get('type') == 'sys':
                print(f"[SYS] {msg.get('content')}")
                if part in msg.get('content', ''): return True
        return False

    # --- 初始化 ---
    print("\n[TEST] 基础配置中...")
    send_cmd({"cmd": "raw", "args": {"text": "/provider Silicon_flow"}})
    wait_for_sys("Switched to Silicon_flow")
    send_cmd({"cmd": "raw", "args": {"text": "/tools basic,filesystem"}})
    wait_for_sys("Active tools")
    send_cmd({"cmd": "raw", "args": {"text": "/option 1 1"}})
    wait_for_sys("Set option temperature = 1")

    # --- 开始对话 ---
    prompt = "请读取当前时间，然后阅读 test/test_write.txt 的内容并告诉我。把该文件内容修改为 '测试成功' 并附带你刚才读到的时间。修改完后请再次读取文件确认。"
    print(f"\n[USER] {prompt}")
    send_cmd({"cmd": "chat", "args": {"msg": prompt}})

    last_activity_time = time.time()
    wait_for_terminal = False # 是否进入收尾静默期等待
    
    while True:
        msg = get_json_msg(timeout=0.1)
        
        if msg:
            last_activity_time = time.time()
            m_type = msg.get("type")
            content = msg.get("content")

            if m_type == "state": continue
            
            if m_type == "payload":
                print(f"[RECV] payload: model={content.get('model')}")
            
            elif m_type == "tool_calls":
                calls = content if isinstance(content, list) else []
                print(f"[RECV] tool_calls: {len(calls)} items")
                
                to_execute = [tc for tc in calls if not tc.get("executed")]
                if to_execute:
                    print(f"-> 执行工具: {[tc.get('function_name') for tc in to_execute]}")
                    send_cmd({"cmd": "execute"})
                    wait_for_terminal = False # 重置静默期
                else:
                    # 所有工具都已执行，但模型还没收到结果
                    print("-> 工具列表已全部执行，手动同步结果...")
                    send_cmd({"cmd": "send_results"})
                    wait_for_terminal = False
            
            elif m_type == "tool_result":
                print(f"[RECV] tool_result received. 即将发送结果回 Agent...")
                send_cmd({"cmd": "send_results"})
                wait_for_terminal = False
            
            elif m_type == "assistant":
                print(f"\n[ASSISTANT] {content}")
                wait_for_terminal = True # AI 发话了，可能进入收尾阶段，开始倒计时
            
            elif m_type == "error":
                print(f"!!! 错误: {content}")
                break

        # 检查是否退出
        elapsed_since_last = time.time() - last_activity_time
        if wait_for_terminal and elapsed_since_last > 30:
            print(f"\n[TEST] 判定流程结束。")
            break
        
        # 兜底超时
        if elapsed_since_last > 60:
            print("\n[TEST] 超过 60 秒无任何交互响应，强制退出。")
            break

        time.sleep(0.01)

    # --- 退出 ---
    send_cmd({"cmd": "exit"})
    process.terminate()
    
    print("\n=== 最终文件检查 (请观察下方输出确认逻辑正确性) ===")
    if os.path.exists(test_file):
        with open(test_file, "r", encoding="utf-8") as f:
            print(f"文件内容: {f.read()}")

    print("=== 测试脚本运行结束 ===")

if __name__ == "__main__":
    test_cli()
