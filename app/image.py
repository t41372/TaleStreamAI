import requests
import json
import os
import base64
import time
import urllib.parse
from io import BytesIO
from pathlib import Path
from PIL import Image  # 需要安装 Pillow 库: pip install Pillow
from dotenv import load_dotenv
from tqdm import tqdm  # 用于显示进度条
import gc
import subprocess
import glob
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .logger import (
    log_step_start,
    log_step_complete,
    log_progress,
    log_info,
    log_error,
    log_debug,
    log_api_start,
    log_api_success,
    log_api_error,
)


# 加载环境变量
load_dotenv(override=True)


# 用Flux API生成画面 
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def create_Image(prompt: str, width: int = None, height: int = None) -> bytes:
    """
    Use Flux API via Pollinations to generate images.

    Args:
        prompt: Text description for image generation
        width: Image width (if None, uses environment variable)
        height: Image height (if None, uses environment variable)

    Returns:
        bytes: Image data
    """
    try:
        # URL encode the prompt
        encoded_prompt = urllib.parse.quote(prompt)

        # Get parameters from environment or use defaults
        if width is None:
            width = int(os.getenv("FLUX_WIDTH", "1024"))
        if height is None:
            height = int(os.getenv("FLUX_HEIGHT", "1024"))
        model = os.getenv("FLUX_MODEL", "flux")
        seed = os.getenv("FLUX_SEED", "")
        enhance = os.getenv("FLUX_ENHANCE", "false").lower()

        # Build URL with parameters
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        params = {
            "width": width,
            "height": height,
            "model": model,
            "nologo": "true",
            "enhance": enhance,
        }

        if seed:
            params["seed"] = seed

        # Make request with timeout
        response = requests.get(url, params=params, timeout=300)
        response.raise_for_status()

        return response.content

    except Exception as e:
        raise Exception(f"Flux API generation failed: {str(e)}")


# 调用高清修复
def upscale_image(image_path: str):
    try:
        path = os.path.join(os.getcwd(), image_path)
        # 构建命令
        command = [
            os.path.join(os.getcwd(), "models", "upscayl-bin.exe"),
            "-i",
            path,
            "-o",
            path,
            "-s",
            os.getenv("UPSCAYL_SCALE"),
            "-m",
            os.path.join(os.getcwd(), "models"),
            "-n",
            os.getenv("UPSCAYL_MODEL"),
            "-f",
            os.getenv("UPSCALY_FILE_TYPE"),
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        return False


# 删除log文件
def delete_log_file():
    # 新增功能：删除当前目录下的所有.log文件
    log_files = glob.glob("*.log")
    for log_file in log_files:
        try:
            os.remove(log_file)
        except Exception as e:
            print(f"删除日志文件失败 {log_file}: {e}")
    time.sleep(0.1)


# 保存图片数据到文件（保存为JPG格式）
def save_image_data(image_data: bytes, save_path: str):
    """Save binary image data to file as JPG."""
    # 确保目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 将图片数据保存为JPG
    try:
        # 使用上下文管理器处理BytesIO
        with BytesIO(image_data) as image_buffer:
            # 使用上下文管理器处理图像
            with Image.open(image_buffer) as image:
                # 保存为JPG
                image = image.convert("RGB")
                image.save(save_path, "JPEG", quality=95)

        # 手动触发垃圾回收
        gc.collect()
        return True
    except Exception as e:
        return str(e)


# 保存base64图片到文件（保存为JPG格式） - 保留兼容性
def save_base64_image(base64_data: str, save_path: str):
    """Legacy function for base64 image saving."""
    try:
        image_data = base64.b64decode(base64_data)
        return save_image_data(image_data, save_path)
    except Exception as e:
        return str(e)


# 保存错误信息到文件
def save_error_message(error_msg: str, save_path: str):
    # 确保目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 保存错误信息
    with open(save_path, "w", encoding="utf-8") as error_file:
        error_file.write(error_msg)


# 根据ID生成小说图片
def generate_book_images(book_id: str, width: int = 1024, height: int = 1024):
    """
    生成書籍的所有章節圖片，使用Flux API

    Args:
        book_id: 書籍ID
        width: 图片宽度
        height: 图片高度
    """
    step_name = "圖片生成"
    log_step_start(step_name, f"書籍ID: {book_id}")
    start_time = time.time()

    # 使用pathlib处理路径
    base_path = Path("data") / "book" / book_id
    storyboard_dir = base_path / "storyboard"

    if not storyboard_dir.exists():
        log_error(f"分鏡目錄不存在: {storyboard_dir}")
        raise Exception(f"目录不存在: {storyboard_dir}")

    log_info(f"開始處理分鏡目錄: {storyboard_dir}")

    # 按照文件名排序
    chapter_files = list(storyboard_dir.glob("*.json"))
    chapter_files.sort(key=lambda x: int(x.stem))

    log_info(f"發現 {len(chapter_files)} 個章節分鏡文件")

    # 计算总进度
    total_items = 0
    for chapter_file in chapter_files:
        with open(chapter_file, "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
            total_items += len(chapter_data)

    log_info(f"總共需要處理 {total_items} 個分鏡項目")

    # 创建总进度条
    with tqdm(total=total_items, desc="圖片生成總進度", unit="圖") as pbar:
        # 处理每个章节文件
        for chapter_file in chapter_files:
            chapter_name = chapter_file.stem
            log_progress(
                "章節圖片生成",
                chapter_files.index(chapter_file) + 1,
                len(chapter_files),
                f"處理章節 {chapter_name}",
            )

            # 读取章节数据
            with open(chapter_file, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                # 根据 id字段从小到大排序
                chapter_data.sort(key=lambda x: int(x["id"]))

            # 标记是否需要更新JSON文件
            json_updated = False

            # 处理章节中的每个对象
            for item_idx, item in enumerate(chapter_data):
                # 获取id，如果不存在则使用索引
                item_id = item.get("id", f"index_{item_idx}")

                # 获取提示词
                if "lensLanguage_end" in item:
                    prompt = item["lensLanguage_end"]
                    log_debug(f"處理分鏡 {item_id}, 原始提示詞長度: {len(prompt)} 字符")

                    # 使用逗号将他们分隔为数组
                    prompt = prompt.split(",")
                    # 从新将他们拼接为字符串,只取前30个 不足30个则全部取
                    prompt = ",".join(prompt[:30])
                    log_debug(f"分鏡 {item_id} 提示詞截取後長度: {len(prompt)} 字符")

                    # 使用pathlib处理图片保存路径
                    images_dir = base_path / "images" / chapter_name
                    images_dir.mkdir(parents=True, exist_ok=True)

                    # 设置图片保存路径，使用.jpg后缀
                    image_path = images_dir / f"{item_id}.jpg"
                    error_path = images_dir / f"{item_id}.txt"

                    # 如果图片已存在，跳过
                    if image_path.exists():
                        # 检查是否需要更新JSON数据中的image_path字段
                        if "image_path" not in item:
                            # 添加相对路径到JSON数据 - 使用pathlib确保跨平台兼容
                            relative_image_path = str(images_dir / f"{item_id}.jpg")
                            item["image_path"] = relative_image_path
                            json_updated = True
                            log_debug(
                                f"更新分鏡 {item_id} 的圖片路徑: {relative_image_path}"
                            )
                        gc.collect()
                    else:
                        # 生成图片 - tenacity 会自动处理重试
                        log_api_start(
                            "FLUX_IMAGE_GENERATION", details=f"分鏡 {item_id}"
                        )

                        try:
                            # 生成图片 - Flux API returns bytes directly
                            image_data = create_Image(prompt, width, height)
                            log_debug(
                                f"Flux API 返回圖片數據大小: {len(image_data)} 字節"
                            )

                            # 保存图片
                            save_result = save_image_data(image_data, str(image_path))
                            del image_data
                            gc.collect()

                            if save_result is True:
                                log_api_success(
                                    "FLUX_IMAGE_GENERATION",
                                    details=f"分鏡 {item_id} 圖片生成成功",
                                )

                                # 添加image_path字段到JSON数据
                                relative_image_path = str(images_dir / f"{item_id}.jpg")
                                item["image_path"] = relative_image_path
                                json_updated = True
                                log_debug(
                                    f"添加分鏡 {item_id} 的圖片路徑: {relative_image_path}"
                                )
                                del save_result
                                gc.collect()
                            else:
                                error_msg = f"保存圖片失敗: {save_result}"
                                log_error(f"分鏡 {item_id} 保存失敗: {save_result}")
                                save_error_message(error_msg, str(error_path))
                        except Exception as e:
                            error_msg = f"生成圖片失敗: {str(e)}"
                            log_api_error(
                                "FLUX_IMAGE_GENERATION",
                                str(e),
                                details=f"分鏡 {item_id}",
                            )
                            save_error_message(error_msg, str(error_path))
                            log_error(f"分鏡 {item_id} 圖片生成最終失敗: {error_msg}")
                else:
                    log_error(
                        f"分鏡 {item_id} 缺少 lensLanguage_end 字段，跳過圖片生成"
                    )
                # 更新进度条
                pbar.update(1)
                # 定期释放内存
                if item_idx % 10 == 0:
                    gc.collect()

            # 如果有更新，保存更新后的JSON文件
            if json_updated:
                with open(chapter_file, "w", encoding="utf-8") as f:
                    json.dump(chapter_data, f, ensure_ascii=False, indent=2)
                log_info(f"更新了章節 {chapter_name} 的分鏡JSON文件")

            # 每处理完一个章节，强制清理内存
            del chapter_data
            gc.collect()

    duration = time.time() - start_time
    log_step_complete(step_name, duration, f"生成 {total_items} 個圖片")
    log_info(f"圖片生成完成，耗時 {duration:.2f} 秒")


def get_book_images(book_id: str):
    """
    對書籍圖片進行高清修復處理（如果啟用）

    Args:
        book_id: 書籍ID
    """
    step_name = "圖片高清修復"
    log_step_start(step_name, f"書籍ID: {book_id}")
    start_time = time.time()

    # 新增：根據環境變數 UPSCALY_ENABLE 決定是否執行高清修復
    upscaly_enable = os.getenv("UPSCALY_ENABLE", "false").lower() in [
        "true",
        "1",
        "yes",
    ]
    log_info(f"高清修復設定: {'啟用' if upscaly_enable else '停用'}")

    if not upscaly_enable:
        log_info("跳過圖片高清修復步驟")
        return

    # 使用pathlib处理路径
    base_path = Path("data") / "book" / book_id
    storyboard_dir = base_path / "storyboard"

    if not storyboard_dir.exists():
        log_error(f"分鏡目錄不存在: {storyboard_dir}")
        return

    # 获取所有json文件并排序
    chapter_files = list(storyboard_dir.glob("*.json"))
    chapter_files.sort(key=lambda x: int(x.stem))

    log_info(f"發現 {len(chapter_files)} 個章節文件")

    # 计算总进度
    total_items = 0
    for chapter_file in chapter_files:
        with open(chapter_file, "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
            total_items += len(chapter_data)

    log_info(f"總共需要處理 {total_items} 個圖片")

    # 创建总进度条
    with tqdm(total=total_items, desc="圖片高清修復進度", unit="圖") as pbar:
        # 遍历每个章节文件
        for chapter_file in chapter_files:
            chapter_name = chapter_file.stem
            log_progress(
                "圖片高清修復",
                chapter_files.index(chapter_file) + 1,
                len(chapter_files),
                f"處理章節 {chapter_name}",
            )

            # 读取章节数据
            with open(chapter_file, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                # 根据 id字段从小到大排序
                chapter_data.sort(key=lambda x: int(x["id"]))
                # 遍历每个对象
                for item in chapter_data:
                    if "image_path" in item:
                        image_path = Path(item["image_path"])

                        # 检查图片大小是否超过2MB
                        if image_path.exists():
                            file_size_mb = image_path.stat().st_size / (1024 * 1024)
                            if file_size_mb > 2:
                                log_debug(
                                    f"圖片 {image_path} 大小 {file_size_mb:.2f}MB，跳過處理"
                                )
                                pbar.update(1)
                                # 删除log文件
                                delete_log_file()
                                continue

                        log_debug(f"處理圖片: {image_path}")
                        upscale_result = upscale_image(str(image_path))
                        if upscale_result is True:
                            log_debug(f"圖片 {image_path} 高清修復成功")
                            # 更新进度条
                            pbar.update(1)
                            # 删除log文件
                            delete_log_file()
                        else:
                            # 重试
                            retry_count = 0
                            while retry_count < 3:
                                log_debug(
                                    f"重試高清修復圖片 {image_path} (第 {retry_count + 1}/3 次)"
                                )
                                upscale_result = upscale_image(str(image_path))
                                if upscale_result is True:
                                    log_debug(f"圖片 {image_path} 重試後高清修復成功")
                                    # 更新进度条
                                    pbar.update(1)
                                    # 删除log文件
                                    delete_log_file()
                                    break
                                retry_count += 1

                            if retry_count >= 3:
                                log_error(
                                    f"圖片 {image_path} 高清修復失敗，已重試 3 次"
                                )
                                pbar.update(1)
                    else:
                        log_debug("跳過沒有圖片路徑的分鏡項目")
                        pbar.update(1)

    duration = time.time() - start_time
    log_step_complete(step_name, duration, f"處理 {total_items} 個圖片")
    log_info(f"圖片高清修復完成，耗時 {duration:.2f} 秒")


if __name__ == "__main__":
    generate_book_images("1043294775")
    get_book_images("1043294775")
