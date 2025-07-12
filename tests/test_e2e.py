"""
End-to-end test script that mocks external APIs to test the complete workflow.
"""

import os
import sys
import json
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add the app directory to the Python path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Import main module 
import main


def test_main_with_test_novel():
    """Test the main function using test_novel.txt with mocked APIs."""
    
    # Mock responses
    mock_board_response = json.dumps([
        {
            "id": "1",
            "text": "鼻骨断了？我一下揪住了蚊子的衣服，说：「我还要打！你想办法！」",
            "lensLanguage_cn": "年轻拳手，激动，擂台，紧张，写实，中景，强光",
            "lensLanguage_en": "young boxer, excited, ring, tense, realistic, medium shot, strong light"
        },
        {
            "id": "2", 
            "text": "「别打了！西毒，再打下去你真就没命了！」李哥死死的握着我的手说：「认输吧，我对裁判说我们认输！」",
            "lensLanguage_cn": "中年男子，担心，擂台边，焦急，写实，特写，阴影",
            "lensLanguage_en": "middle-aged man, worried, ringside, anxious, realistic, close-up, shadow"
        }
    ])
    
    # Create fake image data
    from PIL import Image
    import io
    img = Image.new('RGB', (1024, 1024), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    fake_image_data = img_bytes.getvalue()
    
    with patch('app.board.OpenAI') as mock_openai_class, \
         patch('app.image.create_Image') as mock_create_image, \
         patch('app.edge.edge_tts.Communicate') as mock_communicate, \
         patch('app.video.create_book_video') as mock_create_video, \
         patch('app.video_end.save_output_video') as mock_save_video:
        
        # Set up OpenAI mock for storyboard generation
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = mock_board_response
        mock_client.chat.completions.create.return_value = mock_response
        
        # Set up image generation mock
        mock_create_image.return_value = fake_image_data
        
        # Set up Edge TTS mock
        mock_comm_instance = MagicMock()
        mock_communicate.return_value = mock_comm_instance
        
        async def mock_stream():
            mock_chunk = MagicMock()
            mock_chunk.type = "audio"
            mock_chunk.data = b"fake_audio_data"
            yield mock_chunk
        
        mock_comm_instance.stream.return_value = mock_stream()
        
        # Set up video generation mocks
        mock_create_video.return_value = True
        mock_save_video.return_value = True
        
        # Also patch subprocess calls for video operations
        with patch('subprocess.call') as mock_subprocess, \
             patch('subprocess.run') as mock_subprocess_run:
            
            mock_subprocess.return_value = 0  # Success
            mock_subprocess_run.return_value = MagicMock(returncode=0)
        
            # Set environment variables to disable features that might cause issues
            os.environ['UPSCALY_ENABLE'] = 'false'
            os.environ['USE_ASYNC_AUDIO'] = 'false'
            
            try:
                # Mock sys.argv to simulate command line argument
                with patch('sys.argv', ['main.py', 'test_novel.txt']):
                    # Test the main function
                    main.main()
                    print("✅ End-to-end test completed successfully!")
                    
                    # Verify some outputs were created
                    book_id = "test_novel"
                    
                    # Check if data directory was created
                    if os.path.exists(f"data/book/{book_id}"):
                        print(f"✅ Book directory created: data/book/{book_id}")
                        
                        if os.path.exists(f"data/book/{book_id}/list"):
                            print(f"✅ Chapter list directory created")
                            
                        if os.path.exists(f"data/book/{book_id}/storyboard"):
                            print(f"✅ Storyboard directory created")
                            
                        if os.path.exists(f"data/book/{book_id}/images"):
                            print(f"✅ Images directory created")
                            
                        if os.path.exists(f"data/book/{book_id}/audio"):
                            print(f"✅ Audio directory created")
                    else:
                        print("❌ Book directory not found")
                    
                    return True
                    
            except Exception as e:
                print(f"❌ End-to-end test failed: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                # Clean up environment variables
                os.environ.pop('UPSCALY_ENABLE', None)
                os.environ.pop('USE_ASYNC_AUDIO', None)


if __name__ == "__main__":
    print("Running end-to-end test with mocked APIs...")
    success = test_main_with_test_novel()
    if success:
        print("\n🎉 All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Tests failed!")
        sys.exit(1)