import subprocess
import json
import sys
import time
import os

def test_cli():
    print("=== 开始测试 CLI 功能 ===")
    
    # 确保 test/test_write.txt 初始内容正确
    test_file = "test/test_write.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("你好世界")
    
    # 启动 CLI --json
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

    def send_cmd(cmd_dict):
        cmd_str = json.dumps(cmd_dict, ensure_ascii=False) + "\n"
        process.stdin.write(cmd_str)
        process.stdin.flush()

    def wait_for_type(target_types, timeout=30):
        start_time = time.time()
        results = []
        while time.time() - start_time < timeout:
            line = process.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line)
                msg_type = data.get('type')
                
                if msg_type not in ['state', 'payload']:
                    print(f"[RECV] {msg_type}: {data.get('content')}")
                
                if msg_type in target_types:
                    results.append(data)
                    return results
                
                if msg_type == "error":
                    print(f"[ERROR] {data.get('content')}")
                    return results
            except json.JSONDecodeError:
                # 忽略非 JSON 输出（虽然 --json 模式应该全是 JSON）
                if line.strip():
                    print(f"[STDOUT] {line.strip()}")
        return results

    # 1. 发送聊天指令
    prompt = "读取当前时间，阅读并告诉我 test/test_write.txt 的内容，然后把它的内容修改为 '测试成功' 并附带当前时间。最后告诉我修改后的内容。"
    print(f"\n[USER] {prompt}")
    send_cmd({"cmd": "chat", "args": {"msg": prompt}})

    # 循环处理工具调用直到得到最终回答
    max_turns = 10
    for turn in range(max_turns):
        res = wait_for_type(["tool_calls", "assistant", "error"])
        if not res:
            print("超时或无响应")
            break
        
        last_msg = res[-1]
        if last_msg.get("type") == "assistant":
            print(f"\n[ASSISTANT] {last_msg.get('content')}")
            break
        elif last_msg.get("type") == "tool_calls":
            print(f"检测到工具调用，正在执行...")
            send_cmd({"cmd": "execute"})
            res_exec = wait_for_type(["tool_result"])
            print(f"工具执行完毕，正在发送结果回 Agent...")
            send_cmd({"cmd": "send_results"})
        elif last_msg.get("type") == "error":
            break

    # 2. 检查文件内容是否已修改
    print("\n=== 检查文件修改情况 ===")
    if os.path.exists(test_file):
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"文件最终内容: {content}")
            if "测试成功" in content:
                print("测试结果: 成功 (文件已按预期修改)")
            else:
                print("测试结果: 失败 (文件内容不符合预期)")
    else:
        print("测试结果: 失败 (文件不存在)")

    # 退出 CLI
    send_cmd({"cmd": "exit"})
    process.terminate()
    print("\n=== 测试结束 ===")

if __name__ == "__main__":
    test_cli()
