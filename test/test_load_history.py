import sys
import os
import json

# 添加父目录到路径以导入模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chat_logic_v2 import ChatLogicV2

def test_load_history():
    print("Testing load history bug fix...")
    
    # 初始化 ChatLogicV2
    try:
        chat_logic = ChatLogicV2()
    except Exception as e:
        print(f"Failed to initialize ChatLogicV2: {e}")
        return False
        
    # 查找测试用聊天记录文件
    history_file = "shell_test0.json"
    if not os.path.exists(os.path.join("contexts", history_file)):
        print(f"Test file contexts/{history_file} not found. Searching for any .json in contexts...")
        contexts = chat_logic.list_saved_contexts()
        if contexts:
            history_file = contexts[0]['filename']
        else:
            print("No context file found to test.")
            return False
            
    print(f"Loading history from {history_file}...")
    try:
        success = chat_logic.load_context_from_file(history_file)
        if not success:
            print("Failed to load history file.")
            return False
            
        print("History loaded successfully.")
    except Exception as e:
        print(f"Exception during load: {e}")
        return False
        
    # 测试 1: 检查是否存在重复的系统指令
    system_msgs = [msg for msg in chat_logic.messages if msg.role == "system"]
    if len(system_msgs) > 1:
        print(f"❌ FAILED: Found {len(system_msgs)} system messages. Duplicate system instruction bug still exists!")
        for msg in system_msgs:
            print(msg)
        return False
    else:
        print("✅ PASSED: No duplicate system instructions found.")
        
    # 测试 2: 检查生成 payload 时的工具 schema (针对 type 为 array 的报错)
    try:
        print("Setting tools to basic...")
        chat_logic.set_enabled_tool_groups(["basic"])
        
        print("Getting full payload to verify tool schema...")
        payload = chat_logic.get_full_payload("test message")
        
        tools = payload.get("tools", [])
        has_array_type = False
        for tool in tools:
            params = tool.get("function", {}).get("parameters", {})
            properties = params.get("properties", {})
            for prop_name, prop_val in properties.items():
                if "type" in prop_val and isinstance(prop_val["type"], list):
                    print(f"❌ FAILED: Found list type in schema for {tool['function']['name']} -> {prop_name}: {prop_val['type']}")
                    has_array_type = True
        
        if has_array_type:
            return False
        else:
            print("✅ PASSED: Payload tool schema is clean. No list types found.")
            
        return True
    except Exception as e:
        print(f"❌ FAILED during tool setup or payload generation: {e}")
        return False

if __name__ == "__main__":
    success = test_load_history()
    sys.exit(0 if success else 1)
