"""
Edge-TTS implementation for TaleStreamAI
Replaces CosyVoice with Microsoft Edge TTS
"""

import asyncio
import edge_tts
import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import re
import srt
from datetime import timedelta
import difflib

# Configure logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class EdgeTTSService:
    """Enhanced Edge-TTS service with subtitle generation and text matching"""
    
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate  
        self.pitch = pitch
        self.semaphore = asyncio.Semaphore(4)  # Limit concurrent TTS requests
        
    async def generate_audio_with_subtitles(
        self, 
        text: str, 
        output_audio_path: str,
        output_subtitle_path: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Generate audio and subtitles using Edge-TTS
        
        Args:
            text: Input text for TTS
            output_audio_path: Path to save audio file
            output_subtitle_path: Path to save subtitle file (optional)
            
        Returns:
            Tuple of (success, subtitle_content)
        """
        async with self.semaphore:
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)
                if output_subtitle_path:
                    os.makedirs(os.path.dirname(output_subtitle_path), exist_ok=True)
                
                # Create communication with edge-tts
                communication = edge_tts.Communicate(
                    text, 
                    self.voice,
                    rate=self.rate,
                    pitch=self.pitch
                )
                
                audio_data = b""
                subtitle_data = []
                
                # Stream and collect data
                async for chunk in communication.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                    elif chunk["type"] == "WordBoundary":
                        # Collect word boundary information for subtitles
                        subtitle_data.append({
                            "offset": chunk["offset"],
                            "duration": chunk["duration"], 
                            "text": chunk["text"]
                        })
                
                # Save audio file
                with open(output_audio_path, "wb") as f:
                    f.write(audio_data)
                
                # Generate subtitles if needed
                subtitle_content = None
                if output_subtitle_path and subtitle_data:
                    subtitle_content = self._generate_enhanced_subtitles(
                        subtitle_data, text, output_subtitle_path
                    )
                
                return True, subtitle_content
                
            except Exception as e:
                logger.error(f"Error generating audio with subtitles: {e}")
                return False, None
    
    def _generate_enhanced_subtitles(
        self, 
        word_boundaries: List[Dict], 
        original_text: str,
        output_path: str
    ) -> str:
        """
        Generate enhanced subtitles by matching edge-tts word boundaries 
        with original text to preserve punctuation
        """
        try:
            # Group word boundaries into sentences/phrases
            grouped_subtitles = self._group_word_boundaries(word_boundaries, original_text)
            
            # Generate SRT content
            srt_content = self._create_srt_content(grouped_subtitles)
            
            # Save to file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
                
            return srt_content
            
        except Exception as e:
            logger.error(f"Error generating enhanced subtitles: {e}")
            return ""
    
    def _group_word_boundaries(
        self, 
        word_boundaries: List[Dict], 
        original_text: str
    ) -> List[Dict]:
        """
        Group word boundaries into meaningful subtitle segments
        while preserving punctuation from original text
        """
        if not word_boundaries:
            return []
        
        # Clean original text for better matching
        sentences = self._split_into_sentences(original_text)
        
        # Extract words from boundaries (without punctuation)
        boundary_words = [wb["text"].strip() for wb in word_boundaries if wb["text"].strip()]
        
        # Match boundary words to original sentences
        matched_segments = []
        current_boundary_idx = 0
        
        for sentence in sentences:
            if current_boundary_idx >= len(word_boundaries):
                break
                
            # Extract words from sentence for matching
            sentence_words = re.findall(r'\w+', sentence)
            
            if not sentence_words:
                continue
                
            # Find matching boundaries for this sentence
            segment_boundaries = []
            words_matched = 0
            
            while (current_boundary_idx < len(word_boundaries) and 
                   words_matched < len(sentence_words)):
                
                boundary = word_boundaries[current_boundary_idx]
                boundary_word = boundary["text"].strip()
                
                if boundary_word and words_matched < len(sentence_words):
                    # Use fuzzy matching for better results
                    if (self._words_similar(boundary_word, sentence_words[words_matched]) or
                        boundary_word in sentence_words[words_matched] or
                        sentence_words[words_matched] in boundary_word):
                        segment_boundaries.append(boundary)
                        words_matched += 1
                
                current_boundary_idx += 1
            
            # Create segment if we found matching boundaries
            if segment_boundaries:
                start_time = segment_boundaries[0]["offset"] / 10000000.0  # Convert to seconds
                end_time = (segment_boundaries[-1]["offset"] + 
                           segment_boundaries[-1]["duration"]) / 10000000.0
                
                matched_segments.append({
                    "start": start_time,
                    "end": end_time,
                    "text": sentence.strip()
                })
        
        return matched_segments
    
    def _words_similar(self, word1: str, word2: str, threshold: float = 0.6) -> bool:
        """Check if two words are similar using difflib"""
        ratio = difflib.SequenceMatcher(None, word1.lower(), word2.lower()).ratio()
        return ratio >= threshold
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences preserving punctuation"""
        # Enhanced sentence splitting for Chinese and English
        patterns = [
            r'[。！？!?.;；]',  # Chinese and English sentence endings
            r'[，,](?=\s*[A-Z])',  # Comma followed by capital letter
        ]
        
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if re.match(r'[。！？!?.;；]', char):
                if current_sentence.strip():
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
        
        # Add remaining text as final sentence
        if current_sentence.strip():
            sentences.append(current_sentence.strip())
        
        return [s for s in sentences if s.strip()]
    
    def _create_srt_content(self, segments: List[Dict]) -> str:
        """Create SRT format content from segments"""
        subtitles = []
        
        for i, segment in enumerate(segments):
            start_time = timedelta(seconds=segment["start"])
            end_time = timedelta(seconds=segment["end"])
            
            subtitle = srt.Subtitle(
                index=i + 1,
                start=start_time,
                end=end_time,
                content=segment["text"]
            )
            subtitles.append(subtitle)
        
        return srt.compose(subtitles)


async def generate_audio_batch(
    texts_and_paths: List[Tuple[str, str, Optional[str]]], 
    voice: str = "zh-CN-XiaoxiaoNeural",
    max_concurrent: int = 4
) -> List[bool]:
    """
    Generate multiple audio files concurrently
    
    Args:
        texts_and_paths: List of (text, audio_path, subtitle_path) tuples
        voice: Edge-TTS voice to use
        max_concurrent: Maximum concurrent requests
        
    Returns:
        List of success flags for each generation
    """
    tts_service = EdgeTTSService(voice=voice)
    tts_service.semaphore = asyncio.Semaphore(max_concurrent)
    
    tasks = []
    for text, audio_path, subtitle_path in texts_and_paths:
        task = tts_service.generate_audio_with_subtitles(
            text, audio_path, subtitle_path
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Extract success flags
    success_flags = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Batch generation error: {result}")
            success_flags.append(False)
        else:
            success_flags.append(result[0])
    
    return success_flags


def get_available_voices() -> List[str]:
    """Get list of available Chinese voices for Edge-TTS"""
    # Common Chinese voices (since we can't query online in this environment)
    return [
        "zh-CN-XiaoxiaoNeural",  # Female
        "zh-CN-YunxiNeural",     # Male
        "zh-CN-XiaoyiNeural",    # Female
        "zh-CN-YunyangNeural",   # Male
        "zh-CN-XiaochenNeural",  # Female
        "zh-CN-XiaohanNeural",   # Female
        "zh-CN-XiaomengNeural",  # Female
        "zh-CN-XiaomoNeural",    # Female
        "zh-CN-XiaoqiuNeural",   # Female
        "zh-CN-XiaorouNeural",   # Female
        "zh-CN-XiaoruiNeural",   # Female
        "zh-CN-XiaoshuangNeural", # Female
        "zh-CN-XiaoxuanNeural",  # Female
        "zh-CN-XiaoyanNeural",   # Female
        "zh-CN-XiaoyouNeural",   # Female
        "zh-CN-XiaozhenNeural",  # Female
        "zh-CN-YunjianNeural",   # Male
        "zh-CN-YunxiaNeural",    # Male
        "zh-CN-YunyeNeural",     # Male
        "zh-CN-YunzeNeural",     # Male
    ]


if __name__ == "__main__":
    # Test example
    async def test_edge_tts():
        tts_service = EdgeTTSService()
        
        test_text = "你好，这是一个测试。今天天气很好！"
        audio_path = "/tmp/test_audio.mp3"
        subtitle_path = "/tmp/test_subtitle.srt"
        
        success, subtitle_content = await tts_service.generate_audio_with_subtitles(
            test_text, audio_path, subtitle_path
        )
        
        print(f"Generation success: {success}")
        if subtitle_content:
            print("Generated subtitle content:")
            print(subtitle_content)
    
    # Run test (will fail due to network restrictions, but shows the structure)
    # asyncio.run(test_edge_tts())
    print("Edge-TTS implementation ready")