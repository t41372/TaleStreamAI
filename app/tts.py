import asyncio
import os
import json
from tqdm import tqdm
from typing import List, Optional
from .edge_tts_impl import EdgeTTSService
import logging

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def generate_subtitle_from_audio(
    audio_file: str,
    output_srt: Optional[str] = None,
    original_text: Optional[str] = None
) -> str:
    """
    从Edge-TTS生成的音频中提取或生成字幕
    
    Args:
        audio_file: 音频文件路径
        output_srt: 输出SRT文件路径
        original_text: 原始文本（用于改进字幕质量）
        
    Returns:
        str: 生成的字幕文件路径
    """
    # 设置默认输出文件名
    if output_srt is None:
        base_name = os.path.splitext(audio_file)[0]
        output_srt = f"{base_name}.srt"
    
    # 检查是否已有字幕文件
    if os.path.exists(output_srt):
        return output_srt
    
    # 如果没有原始文本，尝试从JSON文件中获取
    if original_text is None:
        original_text = _extract_text_from_json_structure(audio_file)
    
    if original_text:
        # 使用原始文本生成字幕
        return _generate_subtitle_from_text(original_text, audio_file, output_srt)
    else:
        logger.warning(f"无法获取原始文本，跳过字幕生成: {audio_file}")
        return ""


def _extract_text_from_json_structure(audio_file: str) -> Optional[str]:
    """
    从音频文件路径推断并提取对应的文本内容
    
    Args:
        audio_file: 音频文件路径 (例如: data/book/1043294775/audio/1/123.mp3)
        
    Returns:
        Optional[str]: 提取的文本内容
    """
    try:
        # 解析路径结构: data/book/{book_id}/audio/{chapter}/{item_id}.mp3
        path_parts = audio_file.split(os.sep)
        book_id = path_parts[2]
        chapter = path_parts[4]
        item_id = os.path.splitext(path_parts[5])[0]
        
        # 构建对应的storyboard JSON路径
        json_file = f"data/book/{book_id}/storyboard/{chapter}.json"
        
        if os.path.exists(json_file):
            with open(json_file, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                
            # 查找对应的条目
            for item in chapter_data:
                if str(item.get("id")) == item_id:
                    return item.get("text", "")
        
        return None
        
    except Exception as e:
        logger.error(f"提取文本时出错: {e}")
        return None


def _generate_subtitle_from_text(text: str, audio_file: str, output_srt: str) -> str:
    """
    基于原始文本和音频文件生成字幕
    
    Args:
        text: 原始文本
        audio_file: 音频文件路径
        output_srt: 输出字幕文件路径
        
    Returns:
        str: 字幕文件路径
    """
    try:
        # 使用asyncio运行Edge-TTS字幕生成
        async def generate_with_edge_tts():
            tts_service = EdgeTTSService()
            
            # 临时生成音频和字幕以获取时间信息
            temp_audio = audio_file + ".temp"
            temp_subtitle = output_srt + ".temp"
            
            try:
                success, subtitle_content = await tts_service.generate_audio_with_subtitles(
                    text, temp_audio, temp_subtitle
                )
                
                if success and os.path.exists(temp_subtitle):
                    # 移动临时字幕文件到目标位置
                    os.rename(temp_subtitle, output_srt)
                    
                    # 清理临时音频文件
                    if os.path.exists(temp_audio):
                        os.remove(temp_audio)
                    
                    return output_srt
                else:
                    # 回退到简单的时间估算
                    return _generate_simple_subtitle(text, audio_file, output_srt)
                    
            except Exception as e:
                logger.error(f"Edge-TTS字幕生成失败: {e}")
                # 清理临时文件
                for temp_file in [temp_audio, temp_subtitle]:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                # 回退到简单方法
                return _generate_simple_subtitle(text, audio_file, output_srt)
        
        # 运行异步函数
        result = asyncio.run(generate_with_edge_tts())
        return result
        
    except Exception as e:
        logger.error(f"字幕生成出错: {e}")
        return _generate_simple_subtitle(text, audio_file, output_srt)


def _generate_simple_subtitle(text: str, audio_file: str, output_srt: str) -> str:
    """
    生成简单的字幕文件（回退方法）
    
    Args:
        text: 文本内容
        audio_file: 音频文件路径  
        output_srt: 输出字幕文件路径
        
    Returns:
        str: 字幕文件路径
    """
    try:
        # 估算音频时长（可以使用librosa等库，这里简化处理）
        import subprocess
        
        try:
            # 尝试使用ffprobe获取音频时长
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", 
                 "-of", "csv=p=0", audio_file],
                capture_output=True, text=True, timeout=10
            )
            duration = float(result.stdout.strip()) if result.returncode == 0 else 5.0
        except:
            # 如果ffprobe不可用，使用默认时长
            duration = max(len(text) * 0.15, 5.0)  # 估算：每字0.15秒
        
        # 生成简单的SRT内容
        srt_content = f"""1
00:00:00,000 --> {_format_time(duration)}
{text}

"""
        
        # 保存字幕文件
        os.makedirs(os.path.dirname(output_srt), exist_ok=True)
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write(srt_content)
        
        return output_srt
        
    except Exception as e:
        logger.error(f"简单字幕生成失败: {e}")
        return ""


def _format_time(seconds: float) -> str:
    """将秒数转换为SRT时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def create_tts(book_id: str, base_path: str):
    """
    为指定图书创建字幕文件，使用Edge-TTS或原始文本
    """
    # 获取 data/book/{book_id}/storyboard 目录下的所有json
    storyboard_dir = f"data/book/{book_id}/storyboard"
    if not os.path.exists(storyboard_dir):
        logger.error(f"小说信息不存在{storyboard_dir}")
        return
        
    try:
        chapter_files = os.listdir(storyboard_dir)
        chapter_files.sort(key=lambda x: int(x.split(".")[0]))
        chapter_file_paths = [os.path.join(storyboard_dir, f) for f in chapter_files]
    except Exception as e:
        logger.error(f"读取章节文件失败：{str(e)}")
        return
        
    # 计算总进度
    total_items = 0
    try:
        for chapter_file_path in chapter_file_paths:
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                total_items += len(chapter_data)
    except Exception as e:
        logger.error(f"计算总进度失败：{str(e)}")
        return
        
    # 创建总进度条
    with tqdm(total=total_items, desc="生成字幕", unit="项") as pbar:
        for chapter_file_path in chapter_file_paths:
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                
            for item in chapter_data:
                audio_path = item.get("audio_path", "")
                
                # 处理音频路径
                if "data/" in audio_path:
                    full_audio_path = os.path.join(base_path, audio_path.lstrip("/"))
                else:
                    full_audio_path = os.path.join(base_path, f"data/book/{book_id}/{audio_path}")
                
                # 检查音频文件是否存在
                if os.path.exists(full_audio_path):
                    # 生成字幕
                    original_text = item.get("text", "")
                    generate_subtitle_from_audio(
                        full_audio_path, 
                        original_text=original_text
                    )
                else:
                    logger.warning(f"音频文件不存在，跳过: {full_audio_path}")
                
                pbar.update(1)


if __name__ == "__main__":
    create_tts("1043294775", os.getcwd())
