# TaleStreamAI Migration Guide

## Recent Updates (v0.1.0)

This version includes major updates replacing CosyVoice with Edge-TTS and Stable Diffusion with Flux API.

### 🔧 Core Changes

#### Text-to-Speech Migration
- **Replaced**: CosyVoice API → Microsoft Edge-TTS
- **Benefits**: 
  - No API key required
  - Better Chinese voice quality
  - Built-in subtitle generation
  - Async concurrency support

#### Image Generation Migration  
- **Replaced**: Stable Diffusion → Flux API (Pollinations.ai)
- **Benefits**:
  - No local GPU required
  - No complex setup
  - Better image quality
  - Simple REST API

#### Subtitle Generation Enhancement
- **Replaced**: Whisper → Edge-TTS + text matching
- **Solution**: Combines Edge-TTS word boundaries with original text to preserve punctuation

### 📋 New Environment Variables

Add these to your `.env` file:

```env
# Edge-TTS Configuration
EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural  # Default Chinese female voice
EDGE_TTS_RATE=+0%                    # Speech rate adjustment
EDGE_TTS_PITCH=+0Hz                  # Pitch adjustment  
EDGE_TTS_CONCURRENT=4                # Max concurrent TTS requests

# Flux API Configuration
FLUX_MODEL=flux                      # Image generation model
FLUX_WIDTH=1024                      # Image width
FLUX_HEIGHT=1024                     # Image height
FLUX_ENHANCE=false                   # Enhance prompts with LLM
FLUX_SAFE=false                      # Enable NSFW filtering
FLUX_NOLOGO=false                    # Remove Pollinations logo
```

### 🚀 Performance Improvements

#### Async Concurrency
- Edge-TTS now uses `asyncio` with semaphore control
- Configurable concurrency limits
- Better resource management

#### Subtitle Quality
The new system addresses Edge-TTS subtitle issues:

**Problem**: Edge-TTS generates word-by-word subtitles without punctuation:
```srt
1
00:00:00,000 --> 00:00:00,500
这是

2  
00:00:00,500 --> 00:00:01,000
一个
```

**Solution**: Match with original text to preserve punctuation:
```srt
1
00:00:00,000 --> 00:00:02,500
这是一个测试文本，包含各种标点符号！

2
00:00:02,500 --> 00:00:04,000
比如逗号、感叹号？
```

### 🔄 Migration Steps

1. **Update dependencies**:
   ```bash
   pip install edge-tts>=7.0.0 srt>=3.5.0
   pip uninstall librosa torch transformers  # Remove old dependencies
   ```

2. **Update environment configuration**:
   - Copy new variables from `.env.example`
   - Remove old CosyVoice and SD settings

3. **Test the migration**:
   ```bash
   python test_migration.py
   python demo_migration.py
   ```

### 📚 API Changes

#### Audio Generation
```python
# Old (CosyVoice)
audio_data = generate_audio(text)

# New (Edge-TTS)  
success = await generate_audio_edge_tts(text, audio_path, subtitle_path)
```

#### Image Generation
```python
# Old (Stable Diffusion)
base64_image = create_Image(prompt)
save_base64_image(base64_image, path)

# New (Flux)
image_data = create_Image(prompt)  # Returns bytes
save_image_data(image_data, path)
```

#### Subtitle Generation
```python
# Old (Whisper)
generate_subtitle(audio_file, precision_mode="high")

# New (Edge-TTS + text matching)
generate_subtitle_from_audio(audio_file, original_text=text)
```

### 🐛 Known Issues & Solutions

#### Network Connectivity
Edge-TTS requires internet access. In restricted environments:
- Ensure `speech.platform.bing.com` is accessible
- Use proxy settings if needed
- Fallback to local TTS if necessary

#### Subtitle Timing
- Edge-TTS timing may vary from original audio
- Use `original_text` parameter for better results
- Adjust `EDGE_TTS_RATE` for timing calibration

### 🔧 Troubleshooting

#### Import Errors
```bash
# Install missing dependencies
pip install -r requirements.txt
pip install edge-tts srt
```

#### Voice Issues
```python
# List available voices
from app.edge_tts_impl import get_available_voices
print(get_available_voices())
```

#### Async Errors
```python
# Reduce concurrency if getting timeouts
EDGE_TTS_CONCURRENT=2  # In .env file
```

### 🎯 Python 3.12+ Features Used

- Type hints with `typing` module
- Async context managers
- Enhanced error handling
- F-string expressions
- Pathlib usage
- Dataclass patterns (planned)

### 📝 Testing

Run the test suite:
```bash
python test_migration.py      # Core functionality tests
python demo_migration.py      # Feature demonstrations
```

### 🔮 Future Enhancements

- [ ] Add more voice customization options
- [ ] Implement subtitle timing calibration
- [ ] Add batch processing optimizations  
- [ ] Support for more languages
- [ ] Integration with local TTS fallback