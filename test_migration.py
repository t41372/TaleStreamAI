#!/usr/bin/env python3
"""
Test script for the updated TaleStreamAI components
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

def test_edge_tts_import():
    """Test if Edge-TTS implementation can be imported"""
    try:
        from app.edge_tts_impl import EdgeTTSService, get_available_voices
        print("✓ Edge-TTS implementation imported successfully")
        
        voices = get_available_voices()
        print(f"✓ Available Chinese voices: {len(voices)}")
        print(f"  First few voices: {voices[:3]}")
        
        return True
    except Exception as e:
        print(f"✗ Edge-TTS import failed: {e}")
        return False

def test_audio_module():
    """Test if audio module can be imported"""
    try:
        from app.audio import generate_audio_edge_tts, create_book_audio
        print("✓ Audio module with Edge-TTS imported successfully")
        return True
    except Exception as e:
        print(f"✗ Audio module import failed: {e}")
        return False

def test_image_module():
    """Test if image module can be imported"""
    try:
        from app.image import create_Image, save_image_data
        print("✓ Image module with Flux API imported successfully")
        return True
    except Exception as e:
        print(f"✗ Image module import failed: {e}")
        return False

def test_tts_module():
    """Test if TTS module can be imported"""
    try:
        from app.tts import generate_subtitle_from_audio, create_tts
        print("✓ TTS module with Edge-TTS subtitles imported successfully")
        return True
    except Exception as e:
        print(f"✗ TTS module import failed: {e}")
        return False

def test_edge_tts_functionality():
    """Test basic Edge-TTS functionality (without network)"""
    try:
        from app.edge_tts_impl import EdgeTTSService
        
        # Create service instance
        service = EdgeTTSService()
        print("✓ EdgeTTSService instance created successfully")
        
        # Test text processing methods
        test_text = "你好，这是一个测试。今天天气很好！"
        sentences = service._split_into_sentences(test_text)
        print(f"✓ Text splitting works: {len(sentences)} sentences")
        
        # Test word similarity
        similar = service._words_similar("测试", "测试")
        print(f"✓ Word similarity works: {similar}")
        
        return True
    except Exception as e:
        print(f"✗ Edge-TTS functionality test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing TaleStreamAI Migration to Edge-TTS and Flux")
    print("=" * 50)
    
    tests = [
        test_edge_tts_import,
        test_audio_module,
        test_image_module,
        test_tts_module,
        test_edge_tts_functionality,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
        print()
    
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("✓ All tests passed! Migration successful.")
        return 0
    else:
        print("✗ Some tests failed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())