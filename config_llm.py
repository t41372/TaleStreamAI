#!/usr/bin/env python3
"""
LLM API 配置工具
用於幫助用戶設置和測試大模型API配置
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv, set_key

# 添加項目根目錄到路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.llm_client import test_all_connections, get_storyboard_client, get_prompt_client


def load_current_config():
    """加載當前配置"""
    load_dotenv(override=True)
    config = {
        'storyboard_key': os.getenv('STORYBOARD_API_KEY', ''),
        'storyboard_url': os.getenv('STORYBOARD_API_URL', ''),
        'storyboard_model': os.getenv('STORYBOARD_MODEL', ''),
        'prompt_key': os.getenv('PROMPT_API_KEY', ''),
        'prompt_url': os.getenv('PROMPT_API_URL', ''),
        'prompt_model': os.getenv('PROMPT_MODEL', ''),
        'al_key': os.getenv('AL_API_KEY', ''),
        'al_url': os.getenv('AL_API_URL', ''),
        'gemini_key': os.getenv('GEMINI_API_KEY', ''),
        'gemini_url': os.getenv('GEMINI_API_URL', ''),
    }
    return config


def display_current_config():
    """顯示當前配置"""
    config = load_current_config()
    print("=== 當前大模型API配置 ===")
    print(f"分鏡生成:")
    print(f"  API Key: {config['storyboard_key'][:10]}..." if config['storyboard_key'] else "  API Key: 未設置")
    print(f"  API URL: {config['storyboard_url']}")
    print(f"  Model: {config['storyboard_model']}")
    print()
    print(f"提示詞生成:")
    print(f"  API Key: {config['prompt_key'][:10]}..." if config['prompt_key'] else "  API Key: 未設置")
    print(f"  API URL: {config['prompt_url']}")
    print(f"  Model: {config['prompt_model']}")
    print()
    print(f"備用配置:")
    print(f"  阿里雲 Key: {config['al_key'][:10]}..." if config['al_key'] else "  阿里雲 Key: 未設置")
    print(f"  Gemini Key: {config['gemini_key'][:10]}..." if config['gemini_key'] else "  Gemini Key: 未設置")


def set_config_value(key, value):
    """設置配置值到.env文件"""
    env_file = Path('.env')
    if not env_file.exists():
        env_file.touch()
    set_key(str(env_file), key, value)


def configure_storyboard():
    """配置分鏡生成API"""
    print("=== 配置分鏡生成API ===")
    
    providers = {
        '1': ('Gemini', 'https://generativelanguage.googleapis.com/v1beta/openai/', 'gemini-2.0-flash'),
        '2': ('阿里雲通義千問', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'deepseek-v3'),
        '3': ('OpenAI', 'https://api.openai.com/v1', 'gpt-4'),
        '4': ('自定義', '', ''),
    }
    
    print("選擇API提供商：")
    for key, (name, url, model) in providers.items():
        print(f"{key}. {name}")
    
    choice = input("請選擇 (1-4): ").strip()
    
    if choice in providers:
        name, default_url, default_model = providers[choice]
        
        api_key = input(f"請輸入 {name} API Key: ").strip()
        
        if choice == '4':  # 自定義
            api_url = input("請輸入 API URL: ").strip()
            model = input("請輸入模型名稱: ").strip()
        else:
            api_url = default_url
            model = default_model
            print(f"使用默認 URL: {api_url}")
            print(f"使用默認模型: {model}")
        
        # 保存配置
        set_config_value('STORYBOARD_API_KEY', api_key)
        set_config_value('STORYBOARD_API_URL', api_url)
        set_config_value('STORYBOARD_MODEL', model)
        
        print(f"✅ {name} 分鏡生成配置已保存")
    else:
        print("❌ 無效選擇")


def configure_prompt():
    """配置提示詞生成API"""
    print("=== 配置提示詞生成API ===")
    
    providers = {
        '1': ('Gemini', 'https://generativelanguage.googleapis.com/v1beta/openai/', 'gemini-2.0-flash'),
        '2': ('阿里雲通義千問', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'deepseek-v3'),
        '3': ('OpenAI', 'https://api.openai.com/v1', 'gpt-4'),
        '4': ('自定義', '', ''),
    }
    
    print("選擇API提供商：")
    for key, (name, url, model) in providers.items():
        print(f"{key}. {name}")
    
    choice = input("請選擇 (1-4): ").strip()
    
    if choice in providers:
        name, default_url, default_model = providers[choice]
        
        api_key = input(f"請輸入 {name} API Key: ").strip()
        
        if choice == '4':  # 自定義
            api_url = input("請輸入 API URL: ").strip()
            model = input("請輸入模型名稱: ").strip()
        else:
            api_url = default_url
            model = default_model
            print(f"使用默認 URL: {api_url}")
            print(f"使用默認模型: {model}")
        
        # 保存配置
        set_config_value('PROMPT_API_KEY', api_key)
        set_config_value('PROMPT_API_URL', api_url)
        set_config_value('PROMPT_MODEL', model)
        
        print(f"✅ {name} 提示詞生成配置已保存")
    else:
        print("❌ 無效選擇")


def test_config():
    """測試配置"""
    print("=== 測試API配置 ===")
    results = test_all_connections()
    
    for api_type, success in results.items():
        status = "✅ 成功" if success else "❌ 失敗"
        print(f"{api_type.capitalize()}: {status}")
    
    if all(results.values()):
        print("\n🎉 所有API連接正常！")
    else:
        print("\n⚠️  部分API連接失敗，請檢查配置")


def main():
    """主函數"""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "test":
            test_config()
            return
        elif command == "show":
            display_current_config()
            return
    
    while True:
        print("\n=== TaleStreamAI LLM API 配置工具 ===")
        print("1. 查看當前配置")
        print("2. 配置分鏡生成API")
        print("3. 配置提示詞生成API") 
        print("4. 測試API連接")
        print("5. 退出")
        
        choice = input("\n請選擇操作 (1-5): ").strip()
        
        if choice == '1':
            display_current_config()
        elif choice == '2':
            configure_storyboard()
        elif choice == '3':
            configure_prompt()
        elif choice == '4':
            test_config()
        elif choice == '5':
            print("再見！")
            break
        else:
            print("❌ 無效選擇，請重試")


if __name__ == "__main__":
    main()
