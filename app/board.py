import os
import json
import time
import asyncio
from openai import OpenAI
import re
from tqdm import tqdm
from dotenv import load_dotenv
from .llm_client import get_storyboard_client, async_chat_with_semaphore, batch_async_chat_completion
from .logger import (log_step_start, log_step_complete, log_progress, log_info, 
                    log_error, log_debug, log_api_start, log_api_success, log_api_error)



load_dotenv(override=True)


prompt = """
你是一个资深的剧本编辑
请根据我输入的内容生成分镜，分镜要包含所有小说内容，并且严格按照我输入的格式给我，其中 text为分镜文字内容，screenKeywords_cn 为分镜内容的镜头语言中文描述 screenKeywords_en为 镜头语言的英文描述，一个好的镜头语言可能包含这几类
角色，动作，场景，情绪，风格，镜头角度，灯光与环境
角色   年轻男子、老年女性、英雄、反派   描述角色的年龄、外观或角色类型。
动作   跑步、微笑、哭泣、惊讶地看   明确角色的动作或表情。
场景   森林、城市街道、海滩、厨房   指定故事发生的地点或背景。
情绪   快乐、悲伤、神秘、浪漫   设定场景的氛围或情绪基调。
风格   素描、水彩、卡通、写实、动漫   选择图像的艺术风格。
镜头角度   特写、中景、广角、俯视   指定摄像机的视角或构图。
灯光与环境   阳光、雨天、黄昏、夜景、背光  描述光线条件或环境氛围。
不要对分镜文案进行提炼，一些角色人名，可以根据名字推测是男女还是青年少年，提示词中不要用人名
错误例子 
角色：年轻男子，动作：喝酒、沉思，场景：星空下，情绪：孤独、怀念，镜头角度：中景，灯光与环境：星光、夜晚
正确例子 
年轻男子，喝酒、沉思，星空下，孤独、怀念，中景，星光、夜晚

请严格按照以下JSON格式返回，不要添加任何其他文字或解释，只返回有效的JSON数组：
[
    {
        "id": "1",
        "text": "xxxxxx",
        "lensLanguage_cn": "",
        "lensLanguage_en": ""
    },
    {
        "id":"2",
        "text":"xxxxxxxx",
        "lensLanguage_cn":"",
        "lensLanguage_en":""
    }
]

重要：
1. 必须返回完整的JSON数组
2. 每个对象必须包含 id、text、lensLanguage_cn、lensLanguage_en 四个字段
3. 不要在JSON前后添加任何解释文字
4. 确保JSON格式完整且有效
"""


def generate_board_json(chapter_content: str, max_retries=3, retry_delay=2, use_stream=True):
    """
    生成分鏡JSON，包含詳細的進度日誌記錄
    
    Args:
        chapter_content: 章節内容
        max_retries: 最大重試次數
        retry_delay: 重試延遲時間
        use_stream: 是否使用流式響應
        
    Returns:
        分鏡列表
    """
    step_name = "生成章節分鏡JSON"
    log_step_start(step_name, f"內容長度: {len(chapter_content)} 字符")
    start_time = time.time()
    
    try:
        client = get_storyboard_client()
        log_info("分鏡模型客戶端初始化成功")
    except Exception as e:
        log_error(f"分鏡模型客戶端初始化失敗: {str(e)}")
        return []

    for attempt in range(max_retries):
        try:
            log_info(f"開始第 {attempt + 1}/{max_retries} 次分鏡生成嘗試")
            
            if use_stream:
                # 使用流式請求
                log_api_start("STORYBOARD_STREAM", model=client.model)
                response_stream = client.chat_completion_stream(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": chapter_content},
                    ],
                    temperature=0.5,
                )
                
                # 收集流式響應
                full_content = ""
                log_debug("開始收集流式響應內容...")
                
                for chunk in response_stream:
                    if chunk.choices[0].delta.content is not None:
                        chunk_content = chunk.choices[0].delta.content
                        full_content += chunk_content
                
                content = full_content
                log_api_success("STORYBOARD_STREAM", details=f"內容長度: {len(content)} 字符")
            else:
                # 使用非流式請求
                response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": chapter_content},
                    ],
                    temperature=0.5,
                )
                content = response.choices[0].message.content
                log_debug(f"收到API響應，內容長度: {len(content)} 字符")
            
            # 清理響應內容
            log_debug("開始清理和解析響應內容...")
            content = re.sub(r"```json\n?|\n?```", "", content)
            content = content.strip()
            
            log_debug(f"清理後內容長度: {len(content)} 字符")

            try:
                log_debug("嘗試解析JSON格式...")
                result = json.loads(content)
                # 验证结果非空
                if result and isinstance(result, list) and len(result) > 0:
                    duration = time.time() - start_time
                    log_step_complete(step_name, duration, f"生成 {len(result)} 個分鏡項目")
                    
                    # 顯示生成的分鏡摘要
                    log_info(f"分鏡生成詳情:")
                    for i, item in enumerate(result[:3]):  # 只顯示前3個
                        text_preview = item.get('text', '')[:30] + "..." if len(item.get('text', '')) > 30 else item.get('text', '')
                        log_info(f"  分鏡 {i+1}: ID={item.get('id')}, 文字='{text_preview}'")
                    if len(result) > 3:
                        log_info(f"  ...還有 {len(result) - 3} 個分鏡項目")
                    
                    return result
                else:
                    log_error(f"API返回空結果或格式錯誤，第 {attempt+1} 次嘗試")
                    log_debug(f"原始內容預覽: {content[:200]}...")
                    if attempt < max_retries - 1:
                        log_info(f"等待 {retry_delay}s 後重試...")
                        time.sleep(retry_delay)
                    continue
                    
            except json.JSONDecodeError as e:
                log_error(f"JSON解析失敗，第 {attempt+1} 次嘗試")
                log_error(f"JSON錯誤: {str(e)} (行 {e.lineno}, 列 {e.colno})")
                log_debug(f"原始內容: {content[:500]}...")
                
                # 尝试修复常见的JSON问题
                if attempt == max_retries - 1:  # 最后一次尝试时才进行修复
                    log_info("嘗試修復JSON格式...")
                    fixed_content = fix_json_format(content)
                    if fixed_content:
                        try:
                            result = json.loads(fixed_content)
                            if result and isinstance(result, list) and len(result) > 0:
                                log_info("JSON修復成功!")
                                duration = time.time() - start_time
                                log_step_complete(step_name, duration, f"修復後生成 {len(result)} 個分鏡項目")
                                return result
                        except json.JSONDecodeError:
                            log_error("JSON修復失敗")
                
                if attempt < max_retries - 1:
                    log_info(f"等待 {retry_delay}s 後重試...")
                    time.sleep(retry_delay)
                continue

        except Exception as e:
            log_api_error("STORYBOARD_REQUEST", str(e), retry_count=attempt + 1)
            if "timeout" in str(e).lower():
                log_error("請求超時，可能是因為內容太長或服務器忙碌")
            if attempt < max_retries - 1:
                log_info(f"等待 {retry_delay}s 後重試...")
                time.sleep(retry_delay)
            continue

    duration = time.time() - start_time
    log_error(f"所有重試嘗試都失敗，返回空列表")
    log_step_complete(step_name, duration, "失敗")
    return []


def split_content_into_chunks(content, chunk_size=100):
    """
    将内容按行分割成多个块

    Args:
        content (str): 要分割的内容
        chunk_size (int): 每个块的最大行数

    Returns:
        list: 分割后的内容块列表
    """
    lines = content.splitlines()
    chunks = []

    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i : i + chunk_size])
        chunks.append(chunk)

    return chunks


def merge_json_results(results_list):
    """
    合并多个JSON结果列表为一个列表

    Args:
        results_list (list): 包含多个JSON结果列表的列表

    Returns:
        list: 合并后的JSON结果列表
    """
    merged_results = []
    id_counter = 1

    for results in results_list:
        for item in results:
            # 更新ID以确保连续性
            item["id"] = str(id_counter)
            merged_results.append(item)
            id_counter += 1

    return merged_results


def generate_board(book_id: str):
    """
    生成書籍的所有章節分鏡，包含詳細的進度追蹤
    """
    step_name = "生成書籍分鏡"
    log_step_start(step_name, f"書籍ID: {book_id}")
    start_time = time.time()
    
    # 首先测试API连接
    log_info("開始處理前先測試API連接...")
    if not test_api_connection():
        log_error("API連接失敗，請檢查環境變量設置")
        return False
    
    # 確保目標目錄存在
    storyboard_dir = f"data/book/{book_id}/storyboard"
    if not os.path.exists(storyboard_dir):
        os.makedirs(storyboard_dir)
        log_info(f"創建分鏡目錄: {storyboard_dir}")

    # 獲取所有章節文件
    chapter_dir = f"data/book/{book_id}/list"
    if not os.path.exists(chapter_dir):
        log_error(f"章節目錄不存在: {chapter_dir}")
        return False
        
    chapter_files = os.listdir(chapter_dir)
    # 按文件名排序
    chapter_files.sort(key=lambda x: int(x.split(".")[0]))
    
    log_info(f"發現 {len(chapter_files)} 個章節文件")

    # 跟踪处理结果
    failed_chapters = []
    skipped_chapters = []
    processed_chapters = []

    for i, chapter_file in enumerate(chapter_files):
        # 獲取章節索引
        index = chapter_file.split(".")[0]
        # 檢查目標文件是否已存在且有內容
        target_file = f"{storyboard_dir}/{index}.json"
        
        log_progress("章節分鏡處理", i + 1, len(chapter_files), f"處理章節 {index}")

        # 文件存在性檢查
        if os.path.exists(target_file):
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    existing_content = json.load(f)
                # 驗證內容有效（非空列表或字典）
                if existing_content and (
                    isinstance(existing_content, list) and len(existing_content) > 0
                ):
                    log_info(f"跳過章節 {chapter_file} - 文件已存在且內容有效")
                    skipped_chapters.append(chapter_file)
                    continue  # 跳過處理
            except (json.JSONDecodeError, IOError):
                # 如果文件存在但內容無效或不可讀，則重新處理
                log_warning(f"文件 {target_file} 存在但包含無效數據 - 重新處理")

        # 讀取章節內容
        with open(
            f"data/book/{book_id}/list/{chapter_file}", "r", encoding="utf-8"
        ) as file:
            chapter_content = file.read()

        # 檢查內容長度，如果太長則自動分塊處理
        lines = chapter_content.splitlines()
        line_count = len(lines)
        content_size = len(chapter_content)
        
        print(f"章節 {chapter_file}: {line_count} 行, {content_size} 字符")

        # 如果內容超過20行或5KB，進行分塊處理
        if line_count > 20 or content_size > 5000:
            print(f"章節 {chapter_file} 內容較長，進行分塊處理")
            chunks = split_content_into_chunks(chapter_content, 20)  # 每塊20行
            chunk_results = []

            print(f"將章節分為 {len(chunks)} 個塊進行處理")
            for i, chunk in enumerate(chunks):
                print(f"\n🔄 處理塊 {i+1}/{len(chunks)}")
                print(f"塊內容長度: {len(chunk)} 字符")
                chunk_json = generate_board_json(chunk, use_stream=True)

                if chunk_json:
                    chunk_results.append(chunk_json)
                    print(f"✅ 塊 {i+1} 處理成功，生成 {len(chunk_json)} 個分鏡")
                else:
                    print(f"❌ 警告：無法為章節 {chapter_file} 的塊 {i+1} 生成分鏡")

            if chunk_results:
                # 合并所有成功的块结果
                board_json = merge_json_results(chunk_results)
                print(f"成功合併 {len(chunk_results)} 個塊的結果，共 {len(board_json)} 個分鏡項")
            else:
                print(f"警告：章節 {chapter_file} 的所有塊處理都失败了")
                board_json = []
        else:
            # 直接處理完整章節
            print(f"📖 直接處理完整章節")
            board_json = generate_board_json(chapter_content, use_stream=True)

        # 处理空结果
        if not board_json:
            failed_chapters.append(chapter_file)
            print(f"警告：无法为章节 {chapter_file} 生成分镜")
            continue

        # 将JSON写入文件
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(board_json, f, ensure_ascii=False, indent=2)

    # 报告处理结果
    if skipped_chapters:
        print(f"跳过了 {len(skipped_chapters)} 个章节（文件已存在且内容有效）")

    if failed_chapters:
        print(f"处理完成，但以下章节失败: {', '.join(failed_chapters)}")
        return False
    else:
        processed_count = len(chapter_files) - len(skipped_chapters)
        print(
            f"所有章节处理成功。处理了 {processed_count} 个章节，跳过了 {len(skipped_chapters)} 个章节"
        )
        return True


def fix_json_format(content):
    """
    尝试修复常见的JSON格式问题
    """
    try:
        # 移除markdown代码块标记
        content = re.sub(r"```json\n?|\n?```", "", content)
        
        # 如果内容被截断，尝试添加缺失的结构
        content = content.strip()
        
        # 确保以[开始
        if not content.startswith('['):
            content = '[' + content
        
        # 如果没有正确结束，尝试补全
        if not content.endswith(']'):
            # 寻找最后一个完整的对象
            last_brace = content.rfind('}')
            if last_brace != -1:
                content = content[:last_brace + 1] + ']'
            else:
                content = content + ']'
        
        # 尝试修复常见的引号问题
        content = re.sub(r'([{,]\s*)(\w+):', r'\1"\2":', content)  # 给键加引号
        
        return content
    except Exception as e:
        print(f"JSON修复过程中出错: {str(e)}")
        return None


def test_api_connection():
    """
    测试API连接是否正常
    """
    try:
        client = get_storyboard_client()
        print("正在测试分鏡生成API连接...")
        
        if client.test_connection():
            print("✅ 分鏡生成API连接测试成功!")
            return True
        else:
            print("❌ 分鏡生成API连接测试失败")
            return False
        
    except Exception as e:
        print(f"❌ 分鏡生成API连接测试失败: {str(e)}")
        return False


if __name__ == "__main__":
    success = generate_board("1043294775")
    if not success:
        print("部分章节处理失败。请检查并重试。")
