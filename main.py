import os
import sys
from pathlib import Path
from app.main import get_book_content, extract_free_chapters, get_chapter_content
from app.board import generate_board
from app.image import get_book_images, get_book_content as create_book_image
from app.audio import create_book_audio
from app.tts import create_tts
from app.video import create_book_video
from app.video_end import save_output_video


def main():
    """Main function to process a novel (from URL or local file)."""
    # 支持命令行参数指定本地文件
    local_file = None
    book_id = "1043294775"  # 默认书籍ID
    
    if len(sys.argv) >= 2:
        if sys.argv[1].endswith('.txt'):
            local_file = sys.argv[1]
            if len(sys.argv) >= 3:
                book_id = sys.argv[2]
            else:
                # 使用文件名作为book_id
                book_id = Path(local_file).stem
        else:
            book_id = sys.argv[1]
    
    print(f"处理书籍ID: {book_id}")
    if local_file:
        print(f"使用本地文件: {local_file}")
    
    # 获取书籍内容
    book = get_book_content(book_id, local_file)
    if book:
        if not local_file:  # 只有网络获取的才需要解析HTML
            extract_free_chapters(book, book_id)
        get_chapter_content(book_id, from_local=bool(local_file))
    else:
        print("获取书籍内容失败")
        return
    
    # 生成分镜
    success = generate_board(book_id)
    if success:
        # 生成图片
        create_book_image(book_id)
        # 高清修复
        get_book_images(book_id)
        # 生成音频和字幕 (使用Edge TTS)
        create_book_audio(book_id)
        # 验证字幕文件
        create_tts(book_id, os.getcwd())
        # 视频分段生成
        create_book_video(book_id)
        # 视频总合成
        save_output_video(book_id)
        
        print(f"✅ 书籍 {book_id} 处理完成!")
    else:
        print("❌ 生成分镜失败")


if __name__ == "__main__":
    main()
