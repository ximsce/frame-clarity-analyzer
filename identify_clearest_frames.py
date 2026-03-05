#!/usr/bin/env python3
from __future__ import annotations

"""
Script to identify the clearest frames from video frames using AI.
Processes frames in batches and uses AI vision models to assess image clarity.
"""

import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import base64
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from openai import OpenAI
    from openai import RateLimitError, APIError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    RateLimitError = Exception
    APIError = Exception

try:
    import torch
    from transformers import CLIPProcessor, CLIPModel
    from PIL import Image
    import torch.nn.functional as F
    CLIP_AVAILABLE = True
except Exception as e:
    CLIP_AVAILABLE = False
    print(f"Warning: Error loading CLIP libraries: {e}")

# Default frame filename prefix used to extract numeric frame indices
FRAME_PREFIX = os.getenv("FRAME_PREFIX", "rawFrames")


@dataclass
class FrameScore:
    """Stores frame filename and its clarity score."""
    filename: str
    score: float
    reasoning: str = ""


class CLIPFrameAnalyzer:
    """Analyzes frame clarity using local CLIP model."""
    
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        """
        Initialize the CLIP analyzer.
        
        Args:
            model_name: Hugging Face model name (default: openai/clip-vit-base-patch32)
        """
        if not CLIP_AVAILABLE:
            raise ImportError(
                "CLIP libraries required. Install with: pip install torch transformers pillow"
            )
        
        print(f"Loading CLIP model: {model_name}...")
        print("  (This may take 30-60 seconds on first run)")
        
        # Determine device
        if torch.cuda.is_available():
            self.device = "cuda"
            print(f"  Using GPU: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            self.device = "mps"  # Apple Silicon
            print("  Using Apple Silicon GPU (MPS)")
        else:
            self.device = "cpu"
            print("  Using CPU (this will be slower)")
        
        # Load model and processor
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.model.eval()  # Set to evaluation mode
        
        # Define quality-related text prompts for scoring
        self.quality_prompts = [
            "a sharp, clear, in-focus photograph with good detail",
            "a blurry, out-of-focus, motion-blurred image",
            "a high quality professional photograph",
            "a low quality, pixelated, grainy image",
            "a well-composed, visually appealing photo",
            "a poorly composed, unappealing image"
        ]
        
        print("  ✓ Model loaded successfully")
    
    def analyze_frame_clarity(self, image_path: str) -> Tuple[float, str]:
        """
        Analyze a single frame for clarity using CLIP.
        
        Returns:
            Tuple of (score, reasoning) where score is 0-100
        """
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert("RGB")
            
            # Process image and text prompts
            inputs = self.processor(
                text=self.quality_prompts,
                images=image,
                return_tensors="pt",
                padding=True
            ).to(self.device)
            
            # Get model predictions
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits_per_image = outputs.logits_per_image
                probs = F.softmax(logits_per_image, dim=1)
            
            # Extract probabilities for quality indicators
            sharp_prob = probs[0][0].item()  # Sharp, clear, in-focus
            blur_prob = probs[0][1].item()   # Blurry, out-of-focus
            high_quality_prob = probs[0][2].item()  # High quality
            low_quality_prob = probs[0][3].item()   # Low quality
            well_composed_prob = probs[0][4].item()  # Well composed
            poorly_composed_prob = probs[0][5].item()  # Poorly composed
            
            # Calculate composite score
            # Positive indicators
            positive_score = (sharp_prob * 0.4 + 
                            high_quality_prob * 0.3 + 
                            well_composed_prob * 0.3) * 100
            
            # Negative indicators
            negative_score = (blur_prob * 0.5 + 
                            low_quality_prob * 0.3 + 
                            poorly_composed_prob * 0.2) * 100
            
            # Final score: positive - negative, scaled to 0-100
            final_score = (positive_score - negative_score + 50)
            final_score = max(0, min(100, final_score))
            
            # Generate reasoning
            reasoning = (
                f"Sharp: {sharp_prob*100:.1f}%, Blur: {blur_prob*100:.1f}%, "
                f"Quality: {high_quality_prob*100:.1f}%, Composition: {well_composed_prob*100:.1f}%"
            )
            
            return final_score, reasoning
            
        except Exception as e:
            print(f"  ✗ Error analyzing {os.path.basename(image_path)}: {e}")
            return 50.0, f"Error: {str(e)}"
    
    def analyze_batch(self, image_paths: List[str], max_workers: int = 1, sequential: bool = False) -> List[FrameScore]:
        """
        Analyze a batch of frames.
        
        Args:
            image_paths: List of paths to image files
            max_workers: Not used for CLIP (always sequential for GPU efficiency)
            sequential: Not used for CLIP
            
        Returns:
            List of FrameScore objects sorted by score (highest first)
        """
        results = []
        
        # CLIP processes sequentially for GPU efficiency
        for path in image_paths:
            filename = os.path.basename(path)
            try:
                score, reasoning = self.analyze_frame_clarity(path)
                results.append(FrameScore(filename=filename, score=score, reasoning=reasoning))
                print(f"  ✓ Analyzed {filename}: {score:.1f}/100")
            except Exception as e:
                print(f"  ✗ Error processing {path}: {e}")
                results.append(FrameScore(filename=filename, score=0.0, reasoning=f"Error: {str(e)}"))
        
        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def test_api_connection(self) -> bool:
        """Test if CLIP model is working."""
        try:
            # Create a simple test image
            test_image = Image.new('RGB', (224, 224), color='red')
            score, reasoning = self.analyze_frame_clarity_from_image(test_image)
            print("  ✓ CLIP model test successful")
            return True
        except Exception as e:
            print(f"  ✗ CLIP model test failed: {e}")
            return False
    
    def analyze_frame_clarity_from_image(self, image: Image.Image) -> Tuple[float, str]:
        """Internal method to analyze from PIL Image object."""
        inputs = self.processor(
            text=self.quality_prompts,
            images=image,
            return_tensors="pt",
            padding=True
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = F.softmax(logits_per_image, dim=1)
        
        sharp_prob = probs[0][0].item()
        blur_prob = probs[0][1].item()
        high_quality_prob = probs[0][2].item()
        low_quality_prob = probs[0][3].item()
        well_composed_prob = probs[0][4].item()
        poorly_composed_prob = probs[0][5].item()
        
        positive_score = (sharp_prob * 0.4 + high_quality_prob * 0.3 + well_composed_prob * 0.3) * 100
        negative_score = (blur_prob * 0.5 + low_quality_prob * 0.3 + poorly_composed_prob * 0.2) * 100
        
        final_score = (positive_score - negative_score + 50)
        final_score = max(0, min(100, final_score))
        
        reasoning = (
            f"Sharp: {sharp_prob*100:.1f}%, Blur: {blur_prob*100:.1f}%, "
            f"Quality: {high_quality_prob*100:.1f}%, Composition: {well_composed_prob*100:.1f}%"
        )
        
        return final_score, reasoning


class FrameClarityAnalyzer:
    """Analyzes frame clarity using AI vision models."""
    
    def __init__(
        self, 
        api_key: str = None, 
        model: str = "gpt-4o",
        requests_per_minute: int = 3,
        delay_between_requests: float = 20.0,
        max_retries: int = 5
    ):
        """
        Initialize the analyzer.
        
        Args:
            api_key: OpenAI API key. If None, will try to get from OPENAI_API_KEY env var.
            model: Model to use for analysis (default: gpt-4o)
            requests_per_minute: Rate limit for requests per minute (free tier: 3-5)
            delay_between_requests: Seconds to wait between requests (free tier: ~20s)
            max_retries: Maximum retry attempts for rate limit errors
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library is required. Install with: pip install openai")
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key parameter.")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.requests_per_minute = requests_per_minute
        self.delay_between_requests = delay_between_requests
        self.max_retries = max_retries
        self.last_request_time = 0.0
        self.request_times = []  # Track request times for rate limiting
    
    def test_api_connection(self) -> bool:
        """Test if API key is valid and account has access."""
        try:
            # Make a minimal test request
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Cheaper model for testing
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            print("✓ API connection successful")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            print(f"✗ API connection failed: {e}")
            if "insufficient_quota" in error_msg or "billing" in error_msg or "quota" in error_msg:
                print("  💳 Your account has no credits. Please add credits to your OpenAI account.")
            elif "invalid_api_key" in error_msg or "authentication" in error_msg or "api key" in error_msg:
                print("  🔑 Your API key is invalid. Please check your OPENAI_API_KEY.")
            elif "rate_limit" in error_msg:
                print("  ⚠️  Rate limit hit on test request. Your account may have very strict limits.")
            return False
    
    def encode_image(self, image_path: str) -> str:
        """Encode image to base64 string."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        
        # Remove request times older than 1 minute
        self.request_times = [t for t in self.request_times if current_time - t < 60]
        
        # If we've hit the rate limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            oldest_request = min(self.request_times)
            wait_time = 60 - (current_time - oldest_request) + 1  # Add 1 second buffer
            if wait_time > 0:
                print(f"  ⏳ Rate limit reached. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                # Update current_time after waiting
                current_time = time.time()
        
        # Always wait the delay between requests (for free tier safety)
        # Skip delay on first request (when last_request_time is 0)
        if self.last_request_time > 0:
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.delay_between_requests:
                wait_time = self.delay_between_requests - time_since_last
                if wait_time > 0:
                    time.sleep(wait_time)
                    # Update current_time after waiting
                    current_time = time.time()
        
        # Record this request AFTER all waiting is done
        self.last_request_time = current_time
        self.request_times.append(self.last_request_time)
    
    def analyze_frame_clarity(self, image_path: str) -> Tuple[float, str]:
        """
        Analyze a single frame for clarity using AI with retry logic.
        
        Returns:
            Tuple of (score, reasoning) where score is 0-100
        """
        base64_image = self.encode_image(image_path)
        filename = os.path.basename(image_path)
        
        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit before making request
                self._wait_for_rate_limit()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this image and rate its clarity/sharpness on a scale of 0-100. 
                                    Consider factors like:
                                    - Focus sharpness (are subjects in focus?)
                                    - Motion blur (is there blur from movement?)
                                    - Overall image quality
                                    - Whether it would make a good photo
                                    
                                    Respond with a JSON object containing:
                                    {
                                        "score": <number 0-100>,
                                        "reasoning": "<brief explanation>"
                                    }"""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=200,
                    temperature=0.3
                )
                
                content = response.choices[0].message.content.strip()
                
                # Try to parse JSON from response
                try:
                    # Extract JSON if wrapped in markdown code blocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    
                    result = json.loads(content)
                    score = float(result.get("score", 50))
                    reasoning = result.get("reasoning", "No reasoning provided")
                    
                    return score, reasoning
                except json.JSONDecodeError:
                    # Fallback: try to extract score from text
                    import re
                    score_match = re.search(r'["\']?score["\']?\s*:\s*(\d+(?:\.\d+)?)', content, re.IGNORECASE)
                    if score_match:
                        score = float(score_match.group(1))
                    else:
                        score = 50
                    
                    reasoning = content[:200]  # First 200 chars as reasoning
                    return score, reasoning
                    
            except RateLimitError as e:
                error_msg = str(e)
                print(f"  ⚠️  Rate limit error for {filename}: {error_msg}")
                # Check if this is actually a rate limit or something else
                error_lower = error_msg.lower()
                if "insufficient_quota" in error_lower or "billing" in error_lower or "quota" in error_lower:
                    print(f"  💳 This looks like a billing/quota issue, not a rate limit!")
                    print(f"  Please add credits to your OpenAI account at https://platform.openai.com/account/billing")
                    return 50.0, f"Quota error: {error_msg}"
                if attempt < self.max_retries - 1:
                    # Exponential backoff: wait 2^attempt * 60 seconds
                    wait_time = (2 ** attempt) * 60
                    print(f"  Retrying in {wait_time} seconds... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  ✗ Max retries exceeded for {filename}: {e}")
                    return 50.0, f"Rate limit error: {error_msg}"
            except APIError as e:
                error_msg = str(e)
                error_lower = error_msg.lower()
                print(f"  ⚠️  API error for {filename}: {error_msg}")
                # Check for quota/billing issues
                if "insufficient_quota" in error_lower or "billing" in error_lower or "quota" in error_lower:
                    print(f"  💳 This is a billing/quota issue!")
                    print(f"  Please add credits to your OpenAI account at https://platform.openai.com/account/billing")
                    return 50.0, f"Quota error: {error_msg}"
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * 10
                    print(f"  Retrying in {wait_time} seconds... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  ✗ Max retries exceeded for {filename}: {e}")
                    return 50.0, f"API error: {error_msg}"
            except Exception as e:
                print(f"  ✗ Error analyzing {filename}: {e}")
                return 50.0, f"Error: {str(e)}"
        
        return 50.0, "Max retries exceeded"
    
    def analyze_batch(self, image_paths: List[str], max_workers: int = 1, sequential: bool = False) -> List[FrameScore]:
        """
        Analyze a batch of frames (sequentially or in parallel).
        
        Args:
            image_paths: List of paths to image files
            max_workers: Maximum number of parallel API calls (1 for sequential)
            sequential: If True, process frames one at a time (recommended for free tier)
            
        Returns:
            List of FrameScore objects sorted by score (highest first)
        """
        results = []
        
        if sequential or max_workers == 1:
            # Sequential processing (safer for free tier)
            for path in image_paths:
                filename = os.path.basename(path)
                try:
                    score, reasoning = self.analyze_frame_clarity(path)
                    results.append(FrameScore(filename=filename, score=score, reasoning=reasoning))
                    print(f"  ✓ Analyzed {filename}: {score:.1f}/100")
                except Exception as e:
                    print(f"  ✗ Error processing {path}: {e}")
                    results.append(FrameScore(filename=filename, score=0.0, reasoning=f"Error: {str(e)}"))
        else:
            # Parallel processing (for paid tiers)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {
                    executor.submit(self.analyze_frame_clarity, path): path 
                    for path in image_paths
                }
                
                for future in as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        score, reasoning = future.result()
                        filename = os.path.basename(path)
                        results.append(FrameScore(filename=filename, score=score, reasoning=reasoning))
                        print(f"  ✓ Analyzed {filename}: {score:.1f}/100")
                    except Exception as e:
                        print(f"  ✗ Error processing {path}: {e}")
                        filename = os.path.basename(path)
                        results.append(FrameScore(filename=filename, score=0.0, reasoning=f"Error: {str(e)}"))
        
        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results


def get_frame_files(frames_dir: str) -> List[str]:
    """Get all frame files sorted by frame number."""
    frames_path = Path(frames_dir)
    frame_files = sorted(
        frames_path.glob("*.png"),
        key=lambda x: int(x.stem.replace(FRAME_PREFIX, ""))
    )
    return [str(f) for f in frame_files]


def load_progress(progress_file: Path) -> Dict:
    """Load progress from previous run."""
    if progress_file.exists():
        try:
            with open(progress_file, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_progress(progress_file: Path, processed_frames: Dict, all_scores: List[FrameScore]):
    """Save progress to resume later."""
    progress_data = {
        "processed_frames": processed_frames,
        "scores": [
            {
                "filename": fs.filename,
                "score": fs.score,
                "reasoning": fs.reasoning
            }
            for fs in all_scores
        ],
        "timestamp": datetime.now().isoformat()
    }
    with open(progress_file, "w") as f:
        json.dump(progress_data, f, indent=2)


def process_frames(
    frames_dir: str,
    output_dir: str = None,
    batch_size: int = 5,
    top_n: int = 50,
    api_key: str = None,
    model: str = "gpt-4o",
    max_workers: int = 1,
    save_results: bool = True,
    free_tier: bool = True,
    requests_per_minute: int = 3,
    delay_between_requests: float = 20.0,
    resume: bool = True,
    analyzer_type: str = "clip",
    clip_model: str = "openai/clip-vit-base-patch32"
):
    """
    Process frames in batches to identify the clearest ones.
    
    Args:
        frames_dir: Directory containing frame images
        output_dir: Directory to save clearest frames (if None, creates 'clearest_frames' subdirectory)
        batch_size: Number of frames to process in each batch
        top_n: Number of top clearest frames to save
        api_key: OpenAI API key (if None, uses OPENAI_API_KEY env var)
        model: Model to use for analysis
        max_workers: Maximum parallel API calls per batch (1 for free tier)
        save_results: Whether to copy clearest frames to output directory
        free_tier: Enable free tier optimizations (sequential processing, longer delays)
        requests_per_minute: Rate limit for requests per minute
        delay_between_requests: Seconds to wait between requests
        resume: Resume from previous progress if available
        analyzer_type: Type of analyzer to use ("clip" or "openai", default: "clip")
        clip_model: CLIP model name if using CLIP analyzer (default: "openai/clip-vit-base-patch32")
    """
    import shutil
    
    # Get all frame files
    print(f"Scanning frames in {frames_dir}...")
    all_frame_files = get_frame_files(frames_dir)
    total_frames = len(all_frame_files)
    print(f"Found {total_frames} frames total")
    
    if total_frames == 0:
        print("No frames found!")
        return
    
    # Check for existing progress
    progress_file = Path(frames_dir).parent / "frame_analysis_progress.json"
    processed_frames = {}
    all_scores = []
    frame_files = all_frame_files  # Will be filtered if resuming
    
    if resume and progress_file.exists():
        print(f"\n📂 Found previous progress file: {progress_file}")
        progress_data = load_progress(progress_file)
        processed_frames = progress_data.get("processed_frames", {})
        existing_scores = progress_data.get("scores", [])
        all_scores = [
            FrameScore(filename=s["filename"], score=s["score"], reasoning=s.get("reasoning", ""))
            for s in existing_scores
        ]
        print(f"  Resuming: {len(processed_frames)} frames already processed")
        
        # Filter out already processed frames
        frame_files = [f for f in all_frame_files if os.path.basename(f) not in processed_frames]
        print(f"  Remaining: {len(frame_files)} frames to process")
    
    if len(frame_files) == 0:
        print("\n✓ All frames already processed!")
    else:
        # Initialize analyzer
        print(f"\nInitializing {analyzer_type.upper()} analyzer...")
        
        if analyzer_type.lower() == "clip":
            if not CLIP_AVAILABLE:
                print("\n❌ CLIP libraries not available!")
                print("  Install with: pip install torch transformers pillow")
                return
            
            analyzer = CLIPFrameAnalyzer(model_name=clip_model)
            
            # Test CLIP model
            print("  Testing CLIP model...")
            if not analyzer.test_api_connection():
                print("\n❌ CLIP model test failed. Please check the error above.")
                return
            
            # CLIP doesn't need rate limiting, but we'll process sequentially for GPU efficiency
            max_workers = 1
            free_tier = False  # No rate limits for local processing
            
        elif analyzer_type.lower() == "openai":
            if not OPENAI_AVAILABLE:
                print("\n❌ OpenAI library not available!")
                print("  Install with: pip install openai")
                return
            
            if free_tier:
                print("  🆓 Free tier mode: Sequential processing with rate limiting")
                max_workers = 1  # Force sequential for free tier
            
            analyzer = FrameClarityAnalyzer(
                api_key=api_key, 
                model=model,
                requests_per_minute=requests_per_minute,
                delay_between_requests=delay_between_requests
            )
            
            # Test API connection before processing
            print("  Testing API connection...")
            if not analyzer.test_api_connection():
                print("\n❌ API connection test failed. Please fix the issue above before continuing.")
                return
        else:
            print(f"\n❌ Unknown analyzer type: {analyzer_type}")
            print("  Valid options: 'clip' or 'openai'")
            return
        
        # Process in batches
        num_batches = (len(frame_files) + batch_size - 1) // batch_size
        
        print(f"\nProcessing {len(frame_files)} frames in {num_batches} batches of {batch_size}...")
        if analyzer_type.lower() == "clip":
            # Estimate time for CLIP (varies by device)
            if hasattr(analyzer, 'device'):
                if analyzer.device == "cuda":
                    time_per_frame = 0.5
                elif analyzer.device == "mps":
                    time_per_frame = 1.0
                else:
                    time_per_frame = 5.0
                estimated_time = (len(frame_files) * time_per_frame) / 60
                print(f"  ⏱️  Estimated time: ~{estimated_time:.1f} minutes (CLIP on {analyzer.device})")
        elif free_tier:
            estimated_time = (len(frame_files) * delay_between_requests) / 60
            print(f"  ⏱️  Estimated time: ~{estimated_time:.1f} minutes (free tier)")
        print("=" * 60)
        
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(frame_files))
            batch_files = frame_files[start_idx:end_idx]
            
            print(f"\nBatch {batch_num + 1}/{num_batches} (frames {start_idx + 1}-{end_idx})")
            batch_scores = analyzer.analyze_batch(
                batch_files, 
                max_workers=max_workers,
                sequential=(free_tier or max_workers == 1)
            )
            all_scores.extend(batch_scores)
            
            # Update processed frames
            for fs in batch_scores:
                processed_frames[fs.filename] = True
            
            # Save progress after each batch
            if resume:
                save_progress(progress_file, processed_frames, all_scores)
            
            # Show top 3 from this batch
            if len(batch_scores) > 0:
                print(f"  Top 3 in this batch:")
                for i, frame_score in enumerate(batch_scores[:3], 1):
                    print(f"    {i}. {frame_score.filename}: {frame_score.score:.1f}/100")
            
            # Delay between batches (extra safety for free tier)
            if free_tier and batch_num < num_batches - 1:
                print(f"  ⏸️  Waiting 5 seconds before next batch...")
                time.sleep(5)
    
    # Sort all results
    all_scores.sort(key=lambda x: x.score, reverse=True)
    
    # Get top N
    top_frames = all_scores[:top_n]
    
    print("\n" + "=" * 60)
    print(f"\nTop {top_n} clearest frames:")
    print("-" * 60)
    for i, frame_score in enumerate(top_frames, 1):
        print(f"{i:3d}. {frame_score.filename:30s} - Score: {frame_score.score:5.1f}/100")
        print(f"     Reasoning: {frame_score.reasoning[:80]}...")
    
    # Save results to JSON
    results_file = Path(frames_dir).parent / "frame_analysis_results.json"
    results_data = {
        "total_frames": total_frames,
        "top_n": top_n,
        "frames": [
            {
                "filename": fs.filename,
                "score": fs.score,
                "reasoning": fs.reasoning
            }
            for fs in all_scores
        ]
    }
    
    with open(results_file, "w") as f:
        json.dump(results_data, f, indent=2)
    print(f"\n✓ Saved full results to {results_file}")
    
    # Copy top frames to output directory
    if save_results:
        if output_dir is None:
            output_dir = Path(frames_dir).parent / "clearest_frames"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(exist_ok=True)
        
        print(f"\nCopying top {top_n} frames to {output_dir}...")
        frames_path = Path(frames_dir)
        
        for i, frame_score in enumerate(top_frames, 1):
            src = frames_path / frame_score.filename
            # Add rank prefix to filename
            dst = output_dir / f"{i:03d}_{frame_score.filename}"
            shutil.copy2(src, dst)
        
        print(f"✓ Copied {len(top_frames)} frames to {output_dir}")
    
    return all_scores


def main():
    parser = argparse.ArgumentParser(
        description="Identify clearest frames from video frames using AI"
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        default="dancingFrames",
        help="Directory containing frame images (default: dancingFrames)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save clearest frames (default: clearest_frames in parent dir)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of frames to process per batch (default: 10 for CLIP, 5 for OpenAI free tier)"
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top clearest frames to save (default: 50)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenAI API key (or set OPENAI_API_KEY env var)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="OpenAI model to use (default: gpt-4o)"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum parallel API calls per batch (default: 1 for free tier, use 5+ for paid)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't copy frames to output directory, only generate JSON report"
    )
    parser.add_argument(
        "--free-tier",
        action="store_true",
        default=True,
        help="Enable free tier optimizations (default: True)"
    )
    parser.add_argument(
        "--no-free-tier",
        action="store_false",
        dest="free_tier",
        help="Disable free tier optimizations (for paid accounts)"
    )
    parser.add_argument(
        "--requests-per-minute",
        type=int,
        default=3,
        help="Rate limit: requests per minute (default: 3 for free tier)"
    )
    parser.add_argument(
        "--delay-between-requests",
        type=float,
        default=20.0,
        help="Seconds to wait between requests (default: 20.0 for free tier)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Don't resume from previous progress"
    )
    parser.add_argument(
        "--analyzer",
        type=str,
        default="clip",
        choices=["clip", "openai"],
        help="Analyzer to use: 'clip' for local CLIP model (free) or 'openai' for OpenAI API (default: clip)"
    )
    parser.add_argument(
        "--clip-model",
        type=str,
        default="openai/clip-vit-base-patch32",
        help="CLIP model to use (default: openai/clip-vit-base-patch32)"
    )
    
    args = parser.parse_args()
    
    try:
        process_frames(
            frames_dir=args.frames_dir,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            top_n=args.top_n,
            api_key=args.api_key,
            model=args.model,
            max_workers=args.max_workers,
            save_results=not args.no_save,
            free_tier=args.free_tier,
            requests_per_minute=args.requests_per_minute,
            delay_between_requests=args.delay_between_requests,
            resume=args.resume,
            analyzer_type=args.analyzer,
            clip_model=args.clip_model
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
