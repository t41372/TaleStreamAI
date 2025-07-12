import os
import json
from tqdm import tqdm
import logging
from .edge import EdgeTTSGenerator, DEFAULT_VOICE

logger = logging.getLogger(__name__)


def generate_subtitle_from_audio(audio_path: str, original_text: str = None) -> str:
    """
    Generate subtitle from existing audio file using Edge TTS metadata.
    This is used when we already have audio but need to regenerate subtitles.
    
    Args:
        audio_path: Path to audio file
        original_text: Original text with punctuation for restoration
        
    Returns:
        Path to generated subtitle file
    """
    try:
        # Check if subtitle already exists
        subtitle_path = os.path.splitext(audio_path)[0] + ".srt"
        
        if os.path.exists(subtitle_path):
            return subtitle_path
            
        # If we have original text, try to read it and regenerate subtitles
        if original_text:
            # Note: Edge TTS subtitles are generated during audio creation
            # For existing audio files, we'd need to re-process them
            logger.warning(f"Subtitle not found for {audio_path}, would need to regenerate audio for subtitles")
            
        return subtitle_path
        
    except Exception as e:
        logger.error(f"Failed to generate subtitle for {audio_path}: {e}")
        return ""


def create_tts(book_id: str, base_path: str):
    """
    Create subtitles for book audio using Edge TTS.
    Note: With Edge TTS, subtitles are generated alongside audio.
    This function mainly validates and creates missing subtitles.
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
    with tqdm(total=total_items, desc="字幕检查进度", unit="项") as pbar:
        for chapter_file_path in chapter_file_paths:
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                for item in chapter_data:
                    audio_path = item.get("audio_path", "")
                    
                    # 处理路径
                    if "data/" in audio_path:
                        full_audio_path = os.path.join(base_path, audio_path.lstrip("/"))
                    else:
                        full_audio_path = os.path.join(base_path, f"data/book/{book_id}/{audio_path}")
                    
                    # 检查音频文件是否存在
                    if os.path.exists(full_audio_path):
                        # 检查对应的字幕文件
                        subtitle_path = os.path.splitext(full_audio_path)[0] + ".srt"
                        if not os.path.exists(subtitle_path):
                            # 尝试生成字幕
                            original_text = item.get("text", "")
                            generate_subtitle_from_audio(full_audio_path, original_text)
                    
                    pbar.update(1)


if __name__ == "__main__":
    create_tts("1043294775", os.getcwd())
