# TaleStreamAI Architecture and Data Flow

## Overview

TaleStreamAI is a pipeline-based application that converts novels into videos through a series of well-defined processing stages. This document outlines the architectural design, data flow, and best practices implemented in the system.

## Core Architecture Principles

### 1. Pipeline-Based Processing
The application follows a clear pipeline architecture where data flows through distinct stages:
```
Novel Text → Storyboard → Prompt Refinement → Image Generation → Audio Generation → Video Assembly
```

### 2. Single Responsibility Principle
Each module has a clear, focused responsibility:
- `app/main.py` - Novel content extraction and management
- `app/board.py` - Storyboard generation from text
- `app/prompt.py` - LLM prompt refinement for image generation
- `app/image.py` - Image generation using Flux API
- `app/audio.py` - Audio synthesis with Edge TTS
- `app/video.py` - Video assembly and rendering

### 3. Cross-Platform Compatibility
All file path operations use Python's `pathlib` for cross-platform compatibility, replacing legacy f-string concatenation.

## Critical Data Flow

### The Core Pipeline Fix

**Previous Issue:** The pipeline had a critical break where `prompt.py` processing was skipped, causing image generation to fail.

**Current Flow:**
```python
# main.py - Correct pipeline order
success = generate_board(book_id)           # Creates lensLanguage_en
if success:
    process_board_files(book_id)            # ✅ CRITICAL: Refines to lensLanguage_end
    generate_book_images(book_id)           # Uses lensLanguage_end
    # ... rest of pipeline
```

### Data Structure Evolution

#### 1. Initial Storyboard Generation (`board.py`)
```json
{
    "id": "1",
    "text": "A young warrior stands in a forest",
    "lensLanguage_cn": "年轻战士，森林，站立",
    "lensLanguage_en": "young warrior, forest, standing"
}
```

#### 2. Prompt Refinement (`prompt.py`)
```json
{
    "id": "1", 
    "text": "A young warrior stands in a forest",
    "lensLanguage_cn": "年轻战士，森林，站立",
    "lensLanguage_en": "young warrior, forest, standing",
    "lensLanguage_end": "masterpiece, best quality, young warrior, mystical forest, standing pose, heroic, anime style, detailed"
}
```

#### 3. Image Generation (`image.py`)
```json
{
    "id": "1",
    "text": "A young warrior stands in a forest", 
    "lensLanguage_cn": "年轻战士，森林，站立",
    "lensLanguage_en": "young warrior, forest, standing",
    "lensLanguage_end": "masterpiece, best quality, young warrior, mystical forest, standing pose, heroic, anime style, detailed",
    "image_path": "data/book/bookid/images/0/1.jpg"
}
```

## File Structure and Path Management

### Directory Structure
```
data/
└── book/
    └── {book_id}/
        ├── list/           # Chapter text files
        ├── storyboard/     # Generated storyboard JSON files
        ├── images/         # Generated images organized by chapter
        ├── audio/          # Generated audio files
        └── video/          # Final video outputs
```

### Path Handling Best Practices

**❌ Old approach (f-string concatenation):**
```python
storyboard_dir = f"data/book/{book_id}/storyboard"
image_path = f"data/book/{book_id}/images/{chapter}/{item_id}.jpg"
```

**✅ New approach (pathlib):**
```python
from pathlib import Path

base_path = Path("data") / "book" / book_id
storyboard_dir = base_path / "storyboard"
image_path = base_path / "images" / chapter / f"{item_id}.jpg"
```

## Module Responsibilities

### `app/board.py` - Storyboard Generation
- **Input:** Chapter text content
- **Output:** JSON with basic storyboard structure
- **Key Fields Created:** `id`, `text`, `lensLanguage_cn`, `lensLanguage_en`
- **LLM Integration:** Uses storyboard client for scene breakdown

### `app/prompt.py` - Prompt Refinement  
- **Input:** Storyboard JSON with `lensLanguage_en`
- **Output:** Enhanced JSON with `lensLanguage_end`
- **Purpose:** Optimizes prompts for stable diffusion/Flux image generation
- **LLM Integration:** Uses prompt client for style enhancement

### `app/image.py` - Image Generation
- **Input:** Storyboard JSON with `lensLanguage_end`
- **Output:** Generated images and updated JSON with `image_path`
- **API:** Flux via Pollinations.ai
- **Features:** Automatic retry, progress tracking, memory management

### `app/audio.py` - Audio Synthesis
- **Input:** Storyboard JSON with `text` fields
- **Output:** Audio files and subtitle timing
- **Technology:** Microsoft Edge TTS
- **Features:** Async processing, word-level timing, Chinese voice support

## Logging and Observability

### Comprehensive Progress Tracking
```python
from app.logger import log_step_start, log_step_complete, log_api_start

log_step_start("圖片生成", f"書籍ID: {book_id}")
log_api_start("FLUX_IMAGE_GENERATION", details=f"分鏡 {item_id}")
# ... processing ...
log_step_complete("圖片生成", duration, f"生成 {total_items} 個圖片")
```

### Verbose Mode
Enable detailed logging with:
```bash
VERBOSE_LOGGING=true uv run main.py novel.txt
```

## Error Handling and Resilience

### Retry Logic
- **Image Generation:** 3 attempts with exponential backoff
- **LLM Calls:** Configurable retry with fallback to original prompts
- **API Timeouts:** Environment-controlled timeout settings

### Graceful Degradation
- If prompt refinement fails, falls back to `lensLanguage_en`
- If image generation fails, saves error details for debugging
- Continues processing other items even if some fail

## Configuration Management

### Environment Variables
```bash
# LLM Configuration
LLM_THREADS=3                    # Async concurrency for LLM calls
LLM_TIMEOUT=120                  # Request timeout
LLM_RETRY_ATTEMPTS=3             # Retry count

# Image Generation  
FLUX_WIDTH=1024                  # Image dimensions
FLUX_HEIGHT=1024
FLUX_ENHANCE=false               # Prompt enhancement (disabled by default)

# Audio Processing
EDGE_TTS_VOICE=zh-CN-XiaoyiNeural
AUDIO_THREADS=5                  # Async concurrency for audio

# Logging
VERBOSE_LOGGING=true             # Detailed progress logs
```

## Performance Optimizations

### Async Processing
- **LLM Calls:** Semaphore-controlled concurrency
- **Audio Generation:** Batch processing with Edge TTS
- **Memory Management:** Aggressive garbage collection for image processing

### Caching and Skipping
- Automatically skips existing files with valid content
- Validates JSON structure before processing
- Progress tracking for interrupted sessions

## Testing Strategy

### Data Flow Validation
```python
# Test complete pipeline
def test_data_flow():
    # 1. Generate storyboard with lensLanguage_en
    # 2. Process prompts to create lensLanguage_end  
    # 3. Verify image generation can access refined prompts
```

### Module Integration
- All modules tested for import compatibility
- Function signatures validated
- Cross-platform path handling verified

## Migration Guide

### From Legacy Code
1. **Update Path Handling:** Replace f-string paths with pathlib
2. **Add Prompt Processing:** Ensure `process_board_files()` is called
3. **Function Renaming:** Update references to renamed functions
4. **Logging Integration:** Add verbose logging to track progress

### Best Practices for New Features
1. Use pathlib for all file operations
2. Add comprehensive logging with progress tracking
3. Implement proper error handling with retries
4. Follow single responsibility principle
5. Add tests for data flow validation

## Troubleshooting Common Issues

### Image Generation Fails
**Problem:** Missing `lensLanguage_end` field
**Solution:** Ensure `process_board_files()` is called before image generation

### Cross-Platform Issues  
**Problem:** Path separator issues (Windows vs Unix)
**Solution:** Use pathlib throughout, avoid manual path string manipulation

### Memory Issues
**Problem:** High memory usage during image processing
**Solution:** Implemented garbage collection and progress batching

This architecture ensures a robust, maintainable, and scalable novel-to-video generation pipeline.