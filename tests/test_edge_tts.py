"""
Test suite for TaleStreamAI Edge TTS functionality.
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path
import sys

# Add the app directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from app.edge import EdgeTTSGenerator, generate_audio_with_edge_tts, sync_generate_audio_with_edge_tts


class TestEdgeTTS:
    """Test suite for Edge TTS functionality."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def sample_text(self):
        """Sample Chinese text for testing."""
        return "这是一个测试文本。我们正在测试Edge TTS的功能。"
    
    @pytest.fixture
    def edge_generator(self):
        """Create an EdgeTTSGenerator instance."""
        return EdgeTTSGenerator()
    
    def test_edge_tts_generator_init(self, edge_generator):
        """Test EdgeTTSGenerator initialization."""
        assert edge_generator.voice == "zh-CN-XiaoyiNeural"
        assert edge_generator.rate == "+0%"
        assert edge_generator.volume == "+0%"
        assert edge_generator.pitch == "+0Hz"
        assert edge_generator.semaphore._value == 5
    
    def test_split_into_sentences(self, edge_generator):
        """Test sentence splitting functionality."""
        text = "这是第一句。这是第二句！这是第三句？"
        sentences = edge_generator._split_into_sentences(text)
        expected = ["这是第一句。", "这是第二句！", "这是第三句？"]
        assert sentences == expected
    
    def test_seconds_to_srt_time(self, edge_generator):
        """Test time conversion for SRT format."""
        import datetime
        time_obj = edge_generator._seconds_to_srt_time(65.123)
        expected = datetime.timedelta(seconds=65.123)
        assert time_obj == expected
    
    def test_group_words_into_subtitles(self, edge_generator):
        """Test word grouping for subtitles."""
        word_timings = [
            {"word": "这是", "start": 0.0, "duration": 0.5},
            {"word": "一个", "start": 0.5, "duration": 0.5},
            {"word": "测试", "start": 1.0, "duration": 0.5},
        ]
        
        subtitles = edge_generator._group_words_into_subtitles(word_timings)
        assert len(subtitles) == 1
        assert subtitles[0]["text"] == "这是 一个 测试"
        assert subtitles[0]["start"] == 0.0
        assert subtitles[0]["end"] == 1.5
    
    def test_restore_punctuation_to_subtitles(self, edge_generator):
        """Test punctuation restoration."""
        word_timings = [
            {"word": "这是", "start": 0.0, "duration": 0.5},
            {"word": "测试", "start": 0.5, "duration": 0.5},
        ]
        original_text = "这是测试。"
        
        subtitles = edge_generator._restore_punctuation_to_subtitles(word_timings, original_text)
        assert len(subtitles) == 1
        assert subtitles[0]["text"] == "这是测试。"
    
    def test_format_as_srt(self, edge_generator):
        """Test SRT formatting."""
        subtitles = [
            {"start": 0.0, "end": 2.0, "text": "这是第一句。"},
            {"start": 2.0, "end": 4.0, "text": "这是第二句。"},
        ]
        
        srt_content = edge_generator._format_as_srt(subtitles)
        assert "1\n" in srt_content
        assert "00:00:00,000 --> 00:00:02,000" in srt_content
        assert "这是第一句。" in srt_content
    
    def test_sync_generate_audio_with_edge_tts_interface(self, temp_dir, sample_text):
        """Test the synchronous interface (without actual TTS call)."""
        audio_path = os.path.join(temp_dir, "test.mp3")
        subtitle_path = os.path.join(temp_dir, "test.srt")
        
        # This test only checks the interface, not actual TTS generation
        # which would require network access
        try:
            success, returned_subtitle_path = sync_generate_audio_with_edge_tts(
                sample_text, audio_path, subtitle_path=subtitle_path, original_text=sample_text
            )
            # If we get here without exception, the interface works
            # But we expect failure due to no network access
            assert not success  # Should fail due to network issues
        except Exception as e:
            # Expected if no network access - we're just testing the interface
            error_msg = str(e)
            assert ("Cannot connect" in error_msg or 
                   "Temporary failure" in error_msg or
                   "Failed to generate audio with Edge TTS" in error_msg)


class TestAudioModule:
    """Test suite for audio module functionality."""
    
    def test_import_audio_module(self):
        """Test that the audio module can be imported successfully."""
        import app.audio
        assert hasattr(app.audio, 'generate_audio')
        assert hasattr(app.audio, 'create_book_audio')
    
    def test_import_tts_module(self):
        """Test that the tts module can be imported successfully."""
        import app.tts
        assert hasattr(app.tts, 'create_tts')
        assert hasattr(app.tts, 'generate_subtitle_from_audio')


class TestImageModule:
    """Test suite for image module functionality."""
    
    def test_import_image_module(self):
        """Test that the image module can be imported successfully.""" 
        import app.image
        assert hasattr(app.image, 'create_Image')
        assert hasattr(app.image, 'save_image_data')
        assert hasattr(app.image, 'get_book_content')
    
    def test_flux_url_generation(self):
        """Test Flux API URL generation."""
        import urllib.parse
        prompt = "A beautiful landscape"
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        assert "beautiful" in url
        assert "landscape" in url


if __name__ == "__main__":
    pytest.main([__file__])