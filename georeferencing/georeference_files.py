"""
Georeference ecology papers using LLMs.

This script processes PDF files of ecology papers, extracts images, identifies which
images are maps, and uses LLMs to georeference those maps.

Workflow:
1. Extract images and text from PDF files
2. Use small model (Gemini 2.5 Flash) to identify which images are maps
3. Use large model (Gemini 2.5 Pro) to georeference the maps
4. Output results to JSON file

Supports both batch and synchronous API modes.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import fitz  # PyMuPDF
import google.generativeai as genai
from google import genai as batch_genai
from PIL import Image


# =============================================================================
# COST ESTIMATION CONSTANTS
# =============================================================================
# Based on Gemini API pricing (January 2025)
# https://ai.google.dev/gemini-api/docs/pricing

# Token estimation assumptions:
# - Map identification prompt: ~300 tokens
# - Map identification response: ~200 tokens
# - Georeferencing prompt: ~1000 tokens (includes multiple pages of text)
# - Georeferencing response: ~200 tokens
# - Image tokens: 258 per 768x768 tile (calculated from dimensions)

MAP_ID_PROMPT_TOKENS = 300
MAP_ID_RESPONSE_TOKENS = 200
GEOREF_PROMPT_TOKENS = 1000
GEOREF_RESPONSE_TOKENS = 200
IMAGE_TOKENS_PER_TILE = 258  # For 768x768 tiles

# Batch API pricing (50% discount)
GEMINI_25_FLASH_BATCH_INPUT_COST = 0.15 / 1_000_000  # per token
GEMINI_25_FLASH_BATCH_OUTPUT_COST = 1.25 / 1_000_000  # per token
GEMINI_25_PRO_BATCH_INPUT_COST = 0.625 / 1_000_000  # per token
GEMINI_25_PRO_BATCH_OUTPUT_COST = 5.00 / 1_000_000  # per token

# Synchronous API pricing (standard)
GEMINI_25_FLASH_SYNC_INPUT_COST = 0.30 / 1_000_000  # per token
GEMINI_25_FLASH_SYNC_OUTPUT_COST = 2.50 / 1_000_000  # per token
GEMINI_25_PRO_SYNC_INPUT_COST = 1.25 / 1_000_000  # per token
GEMINI_25_PRO_SYNC_OUTPUT_COST = 10.00 / 1_000_000  # per token


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def sanitize_filename(path: str) -> str:
    """
    Sanitize a file path for use in a filename.

    Args:
        path: Original file path

    Returns:
        Sanitized string safe for use in filenames
    """
    # Remove file extension
    path_without_ext = os.path.splitext(path)[0]
    # Replace problematic characters with underscores
    sanitized = path_without_ext.replace('/', '_').replace('\\', '_').replace(' ', '_')
    sanitized = sanitized.replace(':', '_').replace('..', '_')
    # Remove leading/trailing underscores and limit length
    sanitized = sanitized.strip('_')[:200]
    return sanitized


def sanitize_model_name(model_name: str) -> str:
    """Sanitize model name for use in filenames."""
    name = model_name.replace('models/', '')
    return name.replace(':', '-').replace('/', '-')


def load_api_key() -> str:
    """Load API key from GEMINI_API_KEY.txt file."""
    try:
        with open("GEMINI_API_KEY.txt", "r") as f:
            api_key = f.read().strip()
            if not api_key:
                raise ValueError("API key file is empty")
            return api_key
    except FileNotFoundError:
        raise FileNotFoundError(
            "GEMINI_API_KEY.txt not found. Please create this file with your Google AI API key."
        )


def load_prompts() -> Dict[str, str]:
    """Load prompts from prompts.json file."""
    prompts_path = Path(__file__).parent / "prompts.json"
    try:
        with open(prompts_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompts file not found at {prompts_path}")


def calculate_image_tokens(width: int, height: int, tile_size: int = 768) -> int:
    """
    Calculate token count for an image based on Gemini's tiling system.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        tile_size: Tile size (default 768)

    Returns:
        Number of tokens
    """
    tiles_x = (width + tile_size - 1) // tile_size
    tiles_y = (height + tile_size - 1) // tile_size
    total_tiles = tiles_x * tiles_y
    return total_tiles * IMAGE_TOKENS_PER_TILE


def estimate_cost(
    num_images: int,
    num_maps: int,
    small_model: str,
    large_model: str,
    use_batch: bool,
    image_size: int = 768
) -> Optional[Dict[str, float]]:
    """
    Estimate cost for processing PDFs.

    Args:
        num_images: Total number of images to process
        num_maps: Expected number of maps (for georeferencing)
        small_model: Model name for map identification
        large_model: Model name for georeferencing
        use_batch: Whether using batch API
        image_size: Image size in pixels

    Returns:
        Dict with cost breakdown, or None if models not supported
    """
    # Only support cost estimation for Gemini 2.5 Flash and Pro
    small_model_lower = small_model.lower()
    large_model_lower = large_model.lower()

    # Determine pricing for small model (map identification)
    if 'gemini-2.5-flash' in small_model_lower or 'gemini-2-5-flash' in small_model_lower:
        if use_batch:
            small_input_cost = GEMINI_25_FLASH_BATCH_INPUT_COST
            small_output_cost = GEMINI_25_FLASH_BATCH_OUTPUT_COST
        else:
            small_input_cost = GEMINI_25_FLASH_SYNC_INPUT_COST
            small_output_cost = GEMINI_25_FLASH_SYNC_OUTPUT_COST
    elif 'gemini-2.5-pro' in small_model_lower or 'gemini-2-5-pro' in small_model_lower:
        if use_batch:
            small_input_cost = GEMINI_25_PRO_BATCH_INPUT_COST
            small_output_cost = GEMINI_25_PRO_BATCH_OUTPUT_COST
        else:
            small_input_cost = GEMINI_25_PRO_SYNC_INPUT_COST
            small_output_cost = GEMINI_25_PRO_SYNC_OUTPUT_COST
    else:
        return None

    # Determine pricing for large model (georeferencing)
    if 'gemini-2.5-flash' in large_model_lower or 'gemini-2-5-flash' in large_model_lower:
        if use_batch:
            large_input_cost = GEMINI_25_FLASH_BATCH_INPUT_COST
            large_output_cost = GEMINI_25_FLASH_BATCH_OUTPUT_COST
        else:
            large_input_cost = GEMINI_25_FLASH_SYNC_INPUT_COST
            large_output_cost = GEMINI_25_FLASH_SYNC_OUTPUT_COST
    elif 'gemini-2.5-pro' in large_model_lower or 'gemini-2-5-pro' in large_model_lower:
        if use_batch:
            large_input_cost = GEMINI_25_PRO_BATCH_INPUT_COST
            large_output_cost = GEMINI_25_PRO_BATCH_OUTPUT_COST
        else:
            large_input_cost = GEMINI_25_PRO_SYNC_INPUT_COST
            large_output_cost = GEMINI_25_PRO_SYNC_OUTPUT_COST
    else:
        return None

    # Calculate tokens for images (assuming they're resized to image_size)
    image_tokens = calculate_image_tokens(image_size, image_size)

    # Map identification cost (all images)
    map_id_input_tokens = (MAP_ID_PROMPT_TOKENS + image_tokens) * num_images
    map_id_output_tokens = MAP_ID_RESPONSE_TOKENS * num_images
    map_id_cost = (map_id_input_tokens * small_input_cost +
                   map_id_output_tokens * small_output_cost)

    # Georeferencing cost (estimated number of maps)
    georef_input_tokens = (GEOREF_PROMPT_TOKENS + image_tokens) * num_maps
    georef_output_tokens = GEOREF_RESPONSE_TOKENS * num_maps
    georef_cost = (georef_input_tokens * large_input_cost +
                   georef_output_tokens * large_output_cost)

    return {
        'map_identification_cost': map_id_cost,
        'georeferencing_cost': georef_cost,
        'total_cost': map_id_cost + georef_cost
    }


# =============================================================================
# IMAGE PROCESSING
# =============================================================================

class ImageProcessor:
    """Handles image loading, resizing, and encoding."""

    @staticmethod
    def resize_image_to_bytes(image_path: str, max_size: int = 768) -> bytes:
        """
        Resize image to specified max dimension and return as JPEG bytes.

        Args:
            image_path: Path to image file
            max_size: Maximum dimension for long side

        Returns:
            JPEG image as bytes
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                width, height = img.size

                # Resize to max_size on long side while preserving aspect ratio
                if width > height:
                    new_width = max_size
                    new_height = int((height * max_size) / width)
                else:
                    new_height = max_size
                    new_width = int((width * max_size) / height)

                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                img_byte_arr = io.BytesIO()
                resized_img.save(img_byte_arr, format='JPEG', quality=85, optimize=True)
                return img_byte_arr.getvalue()

        except Exception as e:
            raise Exception(f"Failed to process image {image_path}: {str(e)}")

    @staticmethod
    def get_image_dimensions(image_path: str) -> Tuple[int, int]:
        """Get image dimensions without loading full image."""
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            raise Exception(f"Failed to get dimensions for {image_path}: {str(e)}")


# =============================================================================
# PDF PROCESSING
# =============================================================================

class PDFProcessor:
    """Handles PDF text and image extraction."""

    def __init__(self, temp_folder: str, min_image_size: int = 100):
        """
        Initialize PDF processor.

        Args:
            temp_folder: Folder for temporary image storage
            min_image_size: Minimum size (in pixels) for image extraction
        """
        self.temp_folder = Path(temp_folder)
        self.temp_folder.mkdir(parents=True, exist_ok=True)
        self.min_image_size = min_image_size
        self.image_hashes = set()  # For deduplication

    def compute_image_hash(self, image_bytes: bytes) -> str:
        """Compute hash of image bytes for deduplication."""
        return hashlib.md5(image_bytes).hexdigest()

    def extract_images_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract images from PDF with deduplication and filtering.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of dicts with image info (path, page, hash, dimensions)
        """
        images = []
        sanitized_base = sanitize_filename(pdf_path)

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img in enumerate(image_list):
                    xref = img[0]

                    try:
                        # Extract image
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]

                        # Check for duplicates
                        img_hash = self.compute_image_hash(image_bytes)
                        if img_hash in self.image_hashes:
                            continue

                        # Check image size
                        img_pil = Image.open(io.BytesIO(image_bytes))
                        width, height = img_pil.size

                        if width < self.min_image_size or height < self.min_image_size:
                            continue

                        # Save image
                        self.image_hashes.add(img_hash)
                        image_filename = f"{sanitized_base}_page{page_num+1:03d}_img{img_index+1:03d}.jpg"
                        image_path = self.temp_folder / image_filename

                        # Convert and save as JPEG
                        if img_pil.mode != 'RGB':
                            img_pil = img_pil.convert('RGB')
                        img_pil.save(image_path, 'JPEG', quality=95)

                        images.append({
                            'path': str(image_path),
                            'page': page_num,
                            'width': width,
                            'height': height,
                            'hash': img_hash
                        })

                    except Exception as e:
                        print(f"  Warning: Failed to extract image {img_index} from page {page_num}: {e}")
                        continue

            doc.close()
            return images

        except Exception as e:
            raise Exception(f"Failed to process PDF {pdf_path}: {str(e)}")

    def extract_text_from_page(self, pdf_path: str, page_num: int) -> str:
        """
        Extract text from a specific page.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-indexed)

        Returns:
            Extracted text
        """
        try:
            doc = fitz.open(pdf_path)
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                text = page.get_text()
                doc.close()
                return text
            else:
                doc.close()
                return ""
        except Exception as e:
            print(f"  Warning: Failed to extract text from page {page_num}: {e}")
            return ""

    def extract_text_context(self, pdf_path: str, image_page: int) -> Dict[str, str]:
        """
        Extract text context for an image: first page, image page, and adjacent pages.

        Args:
            pdf_path: Path to PDF file
            image_page: Page number where image was found (0-indexed)

        Returns:
            Dict with text fields: first_page, page_before, image_page, page_after
        """
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            context = {
                'first_page': '',
                'page_before': '',
                'image_page': '',
                'page_after': ''
            }

            # First page
            if total_pages > 0:
                context['first_page'] = doc[0].get_text()

            # Image page
            if 0 <= image_page < total_pages:
                context['image_page'] = doc[image_page].get_text()

            # Page before (if different from first page and image page)
            if image_page > 0:
                if image_page == 1:
                    # Page before is first page, mark as same
                    context['page_before'] = "[Same as first_page]"
                else:
                    context['page_before'] = doc[image_page - 1].get_text()

            # Page after
            if image_page < total_pages - 1:
                context['page_after'] = doc[image_page + 1].get_text()

            # Special case: if image is on first page, mark as same
            if image_page == 0:
                context['image_page'] = "[Same as first_page]"

            doc.close()
            return context

        except Exception as e:
            print(f"  Warning: Failed to extract text context: {e}")
            return {
                'first_page': '',
                'page_before': '',
                'image_page': '',
                'page_after': ''
            }

    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Process a single PDF: extract images and text context.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dict with PDF info, images, and text content
        """
        print(f"  Processing: {os.path.basename(pdf_path)}")

        # Extract images
        images = self.extract_images_from_pdf(pdf_path)
        print(f"    Extracted {len(images)} images")

        # For each image, extract text context
        for img in images:
            img['text_context'] = self.extract_text_context(pdf_path, img['page'])

        return {
            'pdf_path': pdf_path,
            'pdf_filename': os.path.basename(pdf_path),
            'num_images': len(images),
            'images': images
        }


# =============================================================================
# LLM PROCESSING
# =============================================================================

class GeminiProcessor:
    """Handles both batch and synchronous Gemini API processing."""

    def __init__(
        self,
        api_key: str,
        small_model: str,
        large_model: str,
        prompts: Dict[str, str],
        image_size: int = 768,
        use_batch: bool = False
    ):
        """
        Initialize Gemini processor.

        Args:
            api_key: Google AI API key
            small_model: Model for map identification
            large_model: Model for georeferencing
            prompts: Dict with 'map_identification' and 'georeferencing' prompts
            image_size: Image size for resizing
            use_batch: Whether to use batch API
        """
        self.api_key = api_key
        self.small_model = small_model
        self.large_model = large_model
        self.prompts = prompts
        self.image_size = image_size
        self.use_batch = use_batch

        # Configure APIs
        genai.configure(api_key=api_key)
        if use_batch:
            self.batch_client = batch_genai.Client(api_key=api_key)
            # Ensure model names start with "models/" for batch API
            if not self.small_model.startswith("models/"):
                self.small_model = f"models/{self.small_model}"
            if not self.large_model.startswith("models/"):
                self.large_model = f"models/{self.large_model}"
        else:
            # Ensure model names don't start with "models/" for sync API
            self.small_model = self.small_model.replace("models/", "")
            self.large_model = self.large_model.replace("models/", "")
            self.small_model_obj = genai.GenerativeModel(self.small_model)
            self.large_model_obj = genai.GenerativeModel(self.large_model)

    # -------------------------------------------------------------------------
    # Map Identification (Small Model)
    # -------------------------------------------------------------------------

    def identify_maps_sync(
        self,
        images: List[Dict[str, Any]],
        checkpoint_callback: Optional[callable] = None,
        checkpoint_interval: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Identify maps using synchronous API.

        Args:
            images: List of image dicts with 'path' field
            checkpoint_callback: Function to call for checkpointing
            checkpoint_interval: How often to checkpoint

        Returns:
            List of results with map identification
        """
        results = []
        prompt = self.prompts['map_identification']

        print(f"Identifying maps using {self.small_model} (synchronous)...")

        for i, image in enumerate(images):
            print(f"  [{i+1}/{len(images)}] {os.path.basename(image['path'])}...", end=" ", flush=True)

            try:
                # Load and resize image
                image_bytes = ImageProcessor.resize_image_to_bytes(image['path'], self.image_size)
                image_data = {'mime_type': 'image/jpeg', 'data': image_bytes}

                # Generate response
                response = self.small_model_obj.generate_content([image_data, prompt])
                response_text = response.text.strip()

                # Parse JSON
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

                result_json = json.loads(response_text)

                result = {
                    'image_path': image['path'],
                    'is_map': result_json.get('is_map', False),
                    'confidence': result_json.get('confidence', 0.0),
                    'reasoning': result_json.get('reasoning', ''),
                    'success': True
                }

                print(f"✓ is_map={result['is_map']}, confidence={result['confidence']:.2f}")

            except Exception as e:
                print(f"✗ Error: {str(e)}")
                result = {
                    'image_path': image['path'],
                    'is_map': False,
                    'confidence': 0.0,
                    'reasoning': '',
                    'success': False,
                    'error': str(e)
                }

            results.append(result)

            # Checkpoint
            if checkpoint_callback and (i + 1) % checkpoint_interval == 0:
                checkpoint_callback(results)

            # Rate limiting
            if (i + 1) % 10 == 0 and i < len(images) - 1:
                time.sleep(2)

        return results

    def identify_maps_batch(
        self,
        images: List[Dict[str, Any]],
        poll_interval: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Identify maps using batch API.

        Args:
            images: List of image dicts with 'path' field
            poll_interval: Seconds between polls

        Returns:
            List of results with map identification
        """
        print(f"Identifying maps using {self.small_model} (batch)...")

        # Prepare requests
        print(f"  Preparing {len(images)} requests...")
        batch_requests = []
        for image in images:
            try:
                image_bytes = ImageProcessor.resize_image_to_bytes(image['path'], self.image_size)
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')

                request = {
                    'contents': [{
                        'parts': [
                            {
                                'inline_data': {
                                    'mime_type': 'image/jpeg',
                                    'data': image_b64
                                }
                            },
                            {'text': self.prompts['map_identification']}
                        ],
                        'role': 'user'
                    }]
                }
                batch_requests.append(request)
            except Exception as e:
                print(f"  Warning: Failed to prepare request for {image['path']}: {e}")
                batch_requests.append(None)

        # Submit batch job
        print(f"  Submitting batch job...")
        batch_job = self.batch_client.batches.create(
            model=self.small_model,
            src=[r for r in batch_requests if r is not None],
            config={'display_name': f"map-identification-{datetime.now().strftime('%Y%m%d-%H%M%S')}"}
        )
        print(f"  ✓ Batch job created: {batch_job.name}")

        # Poll for completion
        batch_job = self._poll_batch_completion(batch_job, poll_interval)

        # Process results
        print(f"  Processing results...")
        results = []
        responses = batch_job.dest.inlined_responses

        for i, (image, response) in enumerate(zip(images, responses)):
            try:
                if response.response and hasattr(response.response, 'text') and response.response.text:
                    response_text = response.response.text.strip()

                    if response_text.startswith('```json'):
                        response_text = response_text[7:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()

                    result_json = json.loads(response_text)

                    result = {
                        'image_path': image['path'],
                        'is_map': result_json.get('is_map', False),
                        'confidence': result_json.get('confidence', 0.0),
                        'reasoning': result_json.get('reasoning', ''),
                        'success': True
                    }
                else:
                    result = {
                        'image_path': image['path'],
                        'is_map': False,
                        'confidence': 0.0,
                        'reasoning': '',
                        'success': False,
                        'error': 'No response from model'
                    }
            except Exception as e:
                result = {
                    'image_path': image['path'],
                    'is_map': False,
                    'confidence': 0.0,
                    'reasoning': '',
                    'success': False,
                    'error': str(e)
                }

            results.append(result)

        return results

    # -------------------------------------------------------------------------
    # Georeferencing (Large Model)
    # -------------------------------------------------------------------------

    def georeference_maps_sync(
        self,
        map_images: List[Dict[str, Any]],
        checkpoint_callback: Optional[callable] = None,
        checkpoint_interval: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Georeference maps using synchronous API.

        Args:
            map_images: List of image dicts with 'path' and 'text_context' fields
            checkpoint_callback: Function to call for checkpointing
            checkpoint_interval: How often to checkpoint

        Returns:
            List of results with georeferencing
        """
        results = []
        base_prompt = self.prompts['georeferencing']

        print(f"Georeferencing maps using {self.large_model} (synchronous)...")

        for i, image in enumerate(map_images):
            print(f"  [{i+1}/{len(map_images)}] {os.path.basename(image['path'])}...", end=" ", flush=True)

            try:
                # Load and resize image
                image_bytes = ImageProcessor.resize_image_to_bytes(image['path'], self.image_size)
                image_data = {'mime_type': 'image/jpeg', 'data': image_bytes}

                # Build prompt with text context
                text_context = image.get('text_context', {})
                context_text = self._format_text_context(text_context)
                full_prompt = f"{base_prompt}\n\n{context_text}"

                # Generate response
                response = self.large_model_obj.generate_content([image_data, full_prompt])
                response_text = response.text.strip()

                # Parse JSON
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

                result_json = json.loads(response_text)

                result = {
                    'image_path': image['path'],
                    'confidence': result_json.get('confidence', 0.0),
                    'explanation': result_json.get('explanation', ''),
                    'success': True
                }

                # Add coordinates if confidence > 0
                if result['confidence'] > 0:
                    result['coordinates'] = {
                        'upper_left': {
                            'lat': result_json.get('upper_left_lat'),
                            'lon': result_json.get('upper_left_lon')
                        },
                        'upper_right': {
                            'lat': result_json.get('upper_right_lat'),
                            'lon': result_json.get('upper_right_lon')
                        },
                        'lower_left': {
                            'lat': result_json.get('lower_left_lat'),
                            'lon': result_json.get('lower_left_lon')
                        },
                        'lower_right': {
                            'lat': result_json.get('lower_right_lat'),
                            'lon': result_json.get('lower_right_lon')
                        }
                    }

                print(f"✓ confidence={result['confidence']:.2f}")

            except Exception as e:
                print(f"✗ Error: {str(e)}")
                result = {
                    'image_path': image['path'],
                    'confidence': 0.0,
                    'explanation': '',
                    'success': False,
                    'error': str(e)
                }

            results.append(result)

            # Checkpoint
            if checkpoint_callback and (i + 1) % checkpoint_interval == 0:
                checkpoint_callback(results)

            # Rate limiting
            if (i + 1) % 10 == 0 and i < len(map_images) - 1:
                time.sleep(2)

        return results

    def georeference_maps_batch(
        self,
        map_images: List[Dict[str, Any]],
        poll_interval: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Georeference maps using batch API.

        Args:
            map_images: List of image dicts with 'path' and 'text_context' fields
            poll_interval: Seconds between polls

        Returns:
            List of results with georeferencing
        """
        print(f"Georeferencing maps using {self.large_model} (batch)...")

        # Prepare requests
        print(f"  Preparing {len(map_images)} requests...")
        batch_requests = []
        base_prompt = self.prompts['georeferencing']

        for image in map_images:
            try:
                image_bytes = ImageProcessor.resize_image_to_bytes(image['path'], self.image_size)
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')

                # Build prompt with text context
                text_context = image.get('text_context', {})
                context_text = self._format_text_context(text_context)
                full_prompt = f"{base_prompt}\n\n{context_text}"

                request = {
                    'contents': [{
                        'parts': [
                            {
                                'inline_data': {
                                    'mime_type': 'image/jpeg',
                                    'data': image_b64
                                }
                            },
                            {'text': full_prompt}
                        ],
                        'role': 'user'
                    }]
                }
                batch_requests.append(request)
            except Exception as e:
                print(f"  Warning: Failed to prepare request for {image['path']}: {e}")
                batch_requests.append(None)

        # Submit batch job
        print(f"  Submitting batch job...")
        batch_job = self.batch_client.batches.create(
            model=self.large_model,
            src=[r for r in batch_requests if r is not None],
            config={'display_name': f"georeferencing-{datetime.now().strftime('%Y%m%d-%H%M%S')}"}
        )
        print(f"  ✓ Batch job created: {batch_job.name}")

        # Poll for completion
        batch_job = self._poll_batch_completion(batch_job, poll_interval)

        # Process results
        print(f"  Processing results...")
        results = []
        responses = batch_job.dest.inlined_responses

        for i, (image, response) in enumerate(zip(map_images, responses)):
            try:
                if response.response and hasattr(response.response, 'text') and response.response.text:
                    response_text = response.response.text.strip()

                    if response_text.startswith('```json'):
                        response_text = response_text[7:]
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()

                    result_json = json.loads(response_text)

                    result = {
                        'image_path': image['path'],
                        'confidence': result_json.get('confidence', 0.0),
                        'explanation': result_json.get('explanation', ''),
                        'success': True
                    }

                    # Add coordinates if confidence > 0
                    if result['confidence'] > 0:
                        result['coordinates'] = {
                            'upper_left': {
                                'lat': result_json.get('upper_left_lat'),
                                'lon': result_json.get('upper_left_lon')
                            },
                            'upper_right': {
                                'lat': result_json.get('upper_right_lat'),
                                'lon': result_json.get('upper_right_lon')
                            },
                            'lower_left': {
                                'lat': result_json.get('lower_left_lat'),
                                'lon': result_json.get('lower_left_lon')
                            },
                            'lower_right': {
                                'lat': result_json.get('lower_right_lat'),
                                'lon': result_json.get('lower_right_lon')
                            }
                        }
                else:
                    result = {
                        'image_path': image['path'],
                        'confidence': 0.0,
                        'explanation': '',
                        'success': False,
                        'error': 'No response from model'
                    }
            except Exception as e:
                result = {
                    'image_path': image['path'],
                    'confidence': 0.0,
                    'explanation': '',
                    'success': False,
                    'error': str(e)
                }

            results.append(result)

        return results

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _format_text_context(self, text_context: Dict[str, str]) -> str:
        """Format text context for inclusion in prompt."""
        parts = []

        if text_context.get('first_page'):
            if text_context['first_page'] == "[Same as first_page]":
                parts.append("TEXT FROM FIRST PAGE: [Same as image page]")
            else:
                parts.append(f"TEXT FROM FIRST PAGE:\n{text_context['first_page']}")

        if text_context.get('page_before'):
            parts.append(f"\nTEXT FROM PAGE BEFORE IMAGE:\n{text_context['page_before']}")

        if text_context.get('image_page'):
            if text_context['image_page'] != "[Same as first_page]":
                parts.append(f"\nTEXT FROM IMAGE PAGE:\n{text_context['image_page']}")

        if text_context.get('page_after'):
            parts.append(f"\nTEXT FROM PAGE AFTER IMAGE:\n{text_context['page_after']}")

        return "\n".join(parts)

    def _poll_batch_completion(self, batch_job: Any, poll_interval: int) -> Any:
        """Poll batch job until completion."""
        print(f"  Polling for completion (interval: {poll_interval}s)...")

        start_time = time.time()
        poll_count = 0
        completed_states = {
            'JOB_STATE_SUCCEEDED',
            'JOB_STATE_FAILED',
            'JOB_STATE_CANCELLED',
            'JOB_STATE_EXPIRED',
        }

        while True:
            try:
                current_job = self.batch_client.batches.get(name=batch_job.name)
                poll_count += 1
                elapsed = time.time() - start_time

                status_info = f"Status = {current_job.state.name}"
                print(f"    Poll #{poll_count} ({elapsed/3600:.1f}h elapsed): {status_info}")

                if current_job.state.name in completed_states:
                    if current_job.state.name == "JOB_STATE_SUCCEEDED":
                        print(f"  ✓ Batch job completed successfully!")
                        return current_job
                    elif current_job.state.name == "JOB_STATE_FAILED":
                        raise Exception(f"Batch job failed: {getattr(current_job, 'error', 'Unknown error')}")
                    elif current_job.state.name == "JOB_STATE_CANCELLED":
                        raise Exception("Batch job was cancelled")
                    elif current_job.state.name == "JOB_STATE_EXPIRED":
                        raise Exception("Batch job expired")

                time.sleep(poll_interval)

            except KeyboardInterrupt:
                print(f"\n⚠️  Polling interrupted. Job is still running: {batch_job.name}")
                raise

            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['cancelled', 'expired', 'failed']):
                    raise
                else:
                    print(f"  ⚠️  Error during polling: {e}")
                    print(f"  Will retry in {poll_interval} seconds...")
                    time.sleep(poll_interval)


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def main():
    """Main workflow for georeferencing ecology papers."""

    parser = argparse.ArgumentParser(
        description="Georeference figures in ecology papers using LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process PDFs with batch API (default)
  python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json

  # Process PDFs with synchronous API
  python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json --sync

  # Test with first 5 PDFs
  python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json --max-pdfs 5

  # Recursive search for PDFs
  python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json --recursive

  # Resume from checkpoint
  python -m georeferencing.georeference_files --resume /path/to/georeferencing_20250109_status.json
        """
    )

    parser.add_argument(
        'input_folder',
        nargs='?',
        help='Folder containing PDF files to process'
    )
    parser.add_argument(
        '--output-file', '-o',
        help='Output JSON file for results (required unless using --resume)'
    )
    parser.add_argument(
        '--temporary-folder',
        help='Folder for temporary image storage (default: system temp)'
    )
    parser.add_argument(
        '--small-model',
        default='gemini-2.5-flash',
        help='Model for map identification (default: gemini-2.5-flash)'
    )
    parser.add_argument(
        '--large-model',
        default='gemini-2.5-pro',
        help='Model for georeferencing (default: gemini-2.5-pro)'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Use batch API (50%% cost discount, but slower)'
    )
    parser.add_argument(
        '--image-size',
        type=int,
        default=768,
        help='Maximum dimension for resized images (default: 768)'
    )
    parser.add_argument(
        '--checkpoint-interval',
        type=int,
        default=10,
        help='Save checkpoint every N queries (default: 10)'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=60,
        help='Seconds between batch job polls (default: 60)'
    )
    parser.add_argument(
        '--resume',
        help='Resume from status JSON file'
    )
    parser.add_argument(
        '--recursive', '-r',
        action='store_true',
        help='Recursively search for PDF files'
    )
    parser.add_argument(
        '--auto-confirm', '-y',
        action='store_true',
        help='Skip cost confirmation prompt'
    )
    parser.add_argument(
        '--max-pdfs',
        type=int,
        help='Maximum number of PDFs to process (for testing)'
    )

    # Show help if no arguments provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Validate arguments
    if args.resume:
        # Resume mode - input folder and output file come from status file
        # Model settings should be locked in from the status file
        if args.small_model != 'gemini-2.5-flash' or args.large_model != 'gemini-2.5-pro':
            print("❌ Error: Cannot change model settings when resuming. Models are locked from original job.")
            sys.exit(1)
        if args.image_size != 768:
            print("❌ Error: Cannot change --image-size when resuming. Size is locked from original job.")
            sys.exit(1)
    else:
        # New job mode
        if not args.input_folder:
            parser.print_help()
            sys.exit(1)
        if not args.output_file:
            print("❌ Error: --output-file is required unless using --resume")
            sys.exit(1)
        if not os.path.exists(args.input_folder):
            print(f"❌ Error: Input folder does not exist: {args.input_folder}")
            sys.exit(1)

    mode_str = "Batch" if args.batch else "Synchronous"
    print(f"=== Ecology Paper Georeferencing ({mode_str} API) ===\n")

    try:
        # Load API key
        print("1. Loading API key...")
        api_key = load_api_key()
        print("✓ API key loaded\n")

        # Load prompts
        print("2. Loading prompts...")
        prompts = load_prompts()
        print("✓ Prompts loaded\n")

        # Handle resume or new job
        if args.resume:
            print("3. Resuming from checkpoint...")
            with open(args.resume, 'r') as f:
                status = json.load(f)

            # Extract parameters from status file
            params = status['parameters']
            args.input_folder = params['input_folder']
            args.output_file = params['output_file']
            args.small_model = params['small_model']
            args.large_model = params['large_model']
            args.image_size = params['image_size']
            args.batch = params['use_batch']
            temp_folder = params['temporary_folder']

            pdf_results = status['pdf_processing']
            map_id_results = status.get('map_identification', {})
            georef_results = status.get('georeferencing', {})

            print(f"✓ Loaded checkpoint from {args.resume}")
            print(f"  PDFs processed: {len(pdf_results)}")
            print(f"  Map identification: {len(map_id_results)} complete")
            print(f"  Georeferencing: {len(georef_results)} complete\n")
        else:
            # New job - enumerate and process PDFs
            print("3. Enumerating PDF files...")
            pdf_files = []
            if args.recursive:
                for root, dirs, files in os.walk(args.input_folder):
                    for filename in files:
                        if filename.lower().endswith('.pdf'):
                            pdf_files.append(os.path.join(root, filename))
            else:
                for filename in os.listdir(args.input_folder):
                    if filename.lower().endswith('.pdf'):
                        pdf_files.append(os.path.join(args.input_folder, filename))

            pdf_files.sort()

            # Apply max-pdfs limit if specified
            if args.max_pdfs:
                pdf_files = pdf_files[:args.max_pdfs]
                print(f"✓ Found {len(pdf_files)} PDF files (limited to {args.max_pdfs})\n")
            else:
                print(f"✓ Found {len(pdf_files)} PDF files\n")

            if not pdf_files:
                print("❌ No PDF files found!")
                sys.exit(1)

            if len(pdf_files) > 1000:
                print(f"⚠️  Warning: Found {len(pdf_files)} PDFs. This script supports up to 1000 files.")
                response = input("Continue anyway? (y/N): ")
                if response.lower() != 'y':
                    sys.exit(1)

            # Set up temporary folder
            if args.temporary_folder:
                temp_folder = args.temporary_folder
            else:
                temp_folder = tempfile.mkdtemp(prefix='georef_')

            print(f"4. Processing PDF files...")
            print(f"  Temporary folder: {temp_folder}\n")

            pdf_processor = PDFProcessor(temp_folder)
            pdf_results = {}

            for i, pdf_path in enumerate(pdf_files):
                print(f"  [{i+1}/{len(pdf_files)}]", end=" ")
                try:
                    result = pdf_processor.process_pdf(pdf_path)
                    pdf_results[pdf_path] = result
                except Exception as e:
                    print(f"  ❌ Error processing {pdf_path}: {e}")
                    pdf_results[pdf_path] = {
                        'pdf_path': pdf_path,
                        'pdf_filename': os.path.basename(pdf_path),
                        'num_images': 0,
                        'images': [],
                        'error': str(e)
                    }

            total_images = sum(r['num_images'] for r in pdf_results.values())
            print(f"\n✓ Processed {len(pdf_files)} PDFs")
            print(f"✓ Extracted {total_images} images\n")

            map_id_results = {}
            georef_results = {}

        # Create status file path
        if args.resume:
            status_file = args.resume
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            status_filename = f"georeferencing_{timestamp}_status.json"
            if os.path.isdir(args.input_folder):
                status_file = os.path.join(args.input_folder, status_filename)
            else:
                status_file = status_filename

        # Initialize processor
        processor = GeminiProcessor(
            api_key=api_key,
            small_model=args.small_model,
            large_model=args.large_model,
            prompts=prompts,
            image_size=args.image_size,
            use_batch=args.batch
        )

        # Collect all images that need map identification
        all_images = []
        for pdf_result in pdf_results.values():
            for img in pdf_result['images']:
                # Add PDF path to image dict for later association
                img['pdf_path'] = pdf_result['pdf_path']
                all_images.append(img)

        # Filter to images not yet processed for map identification
        images_needing_map_id = [
            img for img in all_images
            if img['path'] not in map_id_results
        ]

        # Estimate cost
        if not args.resume:
            print("5. Estimating cost...")
            num_images = len(all_images)
            num_maps_estimate = len(pdf_results)  # Assume 1 map per paper

            cost_breakdown = estimate_cost(
                num_images=num_images,
                num_maps=num_maps_estimate,
                small_model=args.small_model,
                large_model=args.large_model,
                use_batch=args.batch,
                image_size=args.image_size
            )

            if cost_breakdown:
                print(f"  Map identification ({args.small_model}): ${cost_breakdown['map_identification_cost']:.4f}")
                print(f"  Georeferencing ({args.large_model}): ${cost_breakdown['georeferencing_cost']:.4f}")
                print(f"  Total estimated cost: ${cost_breakdown['total_cost']:.4f}")
                if args.image_size != 768:
                    print(f"  ⚠️  Estimate based on {args.image_size}px images")
            else:
                print(f"  ⚠️  Cannot estimate cost for models: {args.small_model}, {args.large_model}")
                print(f"     Cost estimation only supports Gemini 2.5 Flash and Pro")

            if not args.auto_confirm:
                response = input("\nContinue with processing? (y/N): ")
                if response.lower() != 'y':
                    print("Cancelled by user")
                    sys.exit(0)
            print()

        # Define checkpoint callback
        def save_checkpoint(stage: str, results: Dict):
            """Save checkpoint with current progress."""
            status_data = {
                'parameters': {
                    'input_folder': args.input_folder,
                    'output_file': args.output_file,
                    'temporary_folder': temp_folder,
                    'small_model': args.small_model,
                    'large_model': args.large_model,
                    'image_size': args.image_size,
                    'use_batch': args.batch,
                    'checkpoint_interval': args.checkpoint_interval
                },
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stage': stage,
                'pdf_processing': pdf_results,
                'map_identification': results.get('map_identification', {}),
                'georeferencing': results.get('georeferencing', {})
            }

            with open(status_file, 'w') as f:
                json.dump(status_data, f, indent=2)

        # Stage 1: Map identification
        if images_needing_map_id:
            step_num = 6 if not args.resume else 4
            print(f"{step_num}. Identifying maps ({len(images_needing_map_id)} images)...\n")

            if args.batch:
                new_results = processor.identify_maps_batch(
                    images_needing_map_id,
                    poll_interval=args.poll_interval
                )
            else:
                checkpoint_data = {'map_identification': map_id_results, 'georeferencing': georef_results}

                def checkpoint_callback(results):
                    for r in results:
                        map_id_results[r['image_path']] = r
                    checkpoint_data['map_identification'] = map_id_results
                    save_checkpoint('map_identification', checkpoint_data)

                new_results = processor.identify_maps_sync(
                    images_needing_map_id,
                    checkpoint_callback=checkpoint_callback,
                    checkpoint_interval=args.checkpoint_interval
                )

            # Update map_id_results
            for result in new_results:
                map_id_results[result['image_path']] = result

            print(f"\n✓ Map identification complete")
            maps_found = sum(1 for r in map_id_results.values() if r.get('is_map', False))
            print(f"✓ Found {maps_found} maps out of {len(map_id_results)} images\n")

            # Save checkpoint
            save_checkpoint('map_identification', {
                'map_identification': map_id_results,
                'georeferencing': georef_results
            })
        else:
            print("✓ All images already processed for map identification\n")

        # Stage 2: Georeferencing
        # Collect maps that need georeferencing
        maps_needing_georef = []
        for img in all_images:
            img_path = img['path']
            if img_path in map_id_results:
                map_result = map_id_results[img_path]
                if map_result.get('is_map', False) and map_result.get('confidence', 0) > 0.5:
                    if img_path not in georef_results:
                        maps_needing_georef.append(img)

        if maps_needing_georef:
            step_num = 7 if not args.resume else (5 if images_needing_map_id else 4)
            print(f"{step_num}. Georeferencing maps ({len(maps_needing_georef)} maps)...\n")

            if args.batch:
                new_results = processor.georeference_maps_batch(
                    maps_needing_georef,
                    poll_interval=args.poll_interval
                )
            else:
                checkpoint_data = {'map_identification': map_id_results, 'georeferencing': georef_results}

                def checkpoint_callback(results):
                    for r in results:
                        georef_results[r['image_path']] = r
                    checkpoint_data['georeferencing'] = georef_results
                    save_checkpoint('georeferencing', checkpoint_data)

                new_results = processor.georeference_maps_sync(
                    maps_needing_georef,
                    checkpoint_callback=checkpoint_callback,
                    checkpoint_interval=args.checkpoint_interval
                )

            # Update georef_results
            for result in new_results:
                georef_results[result['image_path']] = result

            successful_georef = sum(1 for r in georef_results.values()
                                   if r.get('confidence', 0) > 0.5)
            print(f"\n✓ Georeferencing complete")
            print(f"✓ Successfully georeferenced {successful_georef} out of {len(georef_results)} maps\n")

            # Save checkpoint
            save_checkpoint('georeferencing', {
                'map_identification': map_id_results,
                'georeferencing': georef_results
            })
        else:
            print("✓ All maps already georeferenced\n")

        # Stage 3: Build final output
        print("Building final output...\n")

        # Organize results by PDF
        final_results = []
        for pdf_path, pdf_result in pdf_results.items():
            pdf_output = {
                'pdf_path': pdf_path,
                'pdf_filename': pdf_result['pdf_filename'],
                'num_images_extracted': pdf_result['num_images'],
                'images': []
            }

            for img in pdf_result['images']:
                img_path = img['path']
                img_output = {
                    'image_path': img_path,
                    'image_filename': os.path.basename(img_path),
                    'page': img['page'],
                    'dimensions': {'width': img['width'], 'height': img['height']}
                }

                # Add map identification results
                if img_path in map_id_results:
                    map_result = map_id_results[img_path]
                    img_output['map_identification'] = {
                        'is_map': map_result.get('is_map', False),
                        'confidence': map_result.get('confidence', 0.0),
                        'reasoning': map_result.get('reasoning', ''),
                        'success': map_result.get('success', False)
                    }

                    # Add georeferencing results if available
                    if img_path in georef_results:
                        georef_result = georef_results[img_path]
                        img_output['georeferencing'] = {
                            'confidence': georef_result.get('confidence', 0.0),
                            'explanation': georef_result.get('explanation', ''),
                            'success': georef_result.get('success', False)
                        }
                        if 'coordinates' in georef_result:
                            img_output['georeferencing']['coordinates'] = georef_result['coordinates']

                pdf_output['images'].append(img_output)

            final_results.append(pdf_output)

        # Save final output
        output_data = {
            'parameters': {
                'input_folder': args.input_folder,
                'temporary_folder': temp_folder,
                'small_model': args.small_model,
                'large_model': args.large_model,
                'image_size': args.image_size,
                'use_batch': args.batch,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'summary': {
                'total_pdfs': len(pdf_results),
                'total_images': len(all_images),
                'total_maps_identified': sum(1 for r in map_id_results.values() if r.get('is_map', False)),
                'total_maps_georeferenced': sum(1 for r in georef_results.values() if r.get('confidence', 0) > 0.5)
            },
            'results': final_results
        }

        with open(args.output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"✓ Results saved to: {args.output_file}")
        print(f"\n🎉 Georeferencing complete!")
        print(f"  PDFs processed: {len(pdf_results)}")
        print(f"  Images extracted: {len(all_images)}")
        print(f"  Maps identified: {output_data['summary']['total_maps_identified']}")
        print(f"  Maps georeferenced: {output_data['summary']['total_maps_georeferenced']}")

        # Clean up status file
        if os.path.exists(status_file) and not args.resume:
            try:
                os.remove(status_file)
                print(f"  Cleaned up status file: {status_file}")
            except:
                pass

    except KeyboardInterrupt:
        print("\n⚠️  Process interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
