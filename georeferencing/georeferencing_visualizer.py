"""

Visualize georeferencing results on an interactive map.

This script takes the JSON output from georeference_files.py and creates
an interactive HTML visualization with:
- Leaflet map showing georeferenced polygons
- Left sidebar listing papers and figures
- Right sidebar showing details on hover/click
- Navigation buttons to cycle through figures

"""

#%% Imports and constants

import argparse
import json
import os
import random
import shutil
import sys

from pathlib import Path
from typing import Dict, List, Any, Optional

from PIL import Image

from georeferencing.html_template import VISUALIZATION_HTML


#%%  Support functions

def resize_image(input_path: str,
                 output_path: str,
                 max_size: int = 800):
    """
    Resize image to fit within max_size while preserving aspect ratio.

    Args:
        input_path: Path to input image
        output_path: Path to save resized image
        max_size: Maximum dimension (width or height)
    """

    try:

        with Image.open(input_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')

            width, height = img.size

            # Only resize if image is larger than max_size
            if (width > max_size) or (height > max_size):
                if width > height:
                    new_width = max_size
                    new_height = int((height * max_size) / width)
                else:
                    new_height = max_size
                    new_width = int((width * max_size) / height)

                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                resized_img.save(output_path, 'JPEG', quality=85, optimize=True)
            else:
                # Image is already small enough, just copy
                shutil.copy2(input_path, output_path)

        # ...with Image.open(...)

    except Exception as e:

        print(f"  Warning: Failed to resize image {input_path}: {e}")

        # Copy as fallback
        try:
            shutil.copy2(input_path, output_path)
        except:
            pass

        # ...try/catch

# ...def resize_image(...)


def prepare_output_folder(output_folder: str,
                          results_data: Dict[str, Any],
                          max_image_size: int,
                          overwrite_images: bool = False) -> Dict[str, str]:
    """
    Prepare output folder and copy/resize images.

    Args:
        output_folder: Path to output folder
        results_data: Parsed JSON data
        max_image_size: Maximum image dimension
        overwrite_images: If True, overwrite existing images; if False, skip existing images

    Returns:
        Dict mapping original image paths to relative paths in output folder
    """

    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    images_path = output_path / "images"
    images_path.mkdir(exist_ok=True)

    image_mapping = {}
    image_counter = 0
    skipped_count = 0

    print("Copying and resizing images...")

    for pdf_result in results_data['results']:

        for img in pdf_result['images']:

            # Only process images that were georeferenced
            if 'georeferencing' in img and img['georeferencing'].get('success', False):
                original_path = img['image_path']

                if not os.path.exists(original_path):
                    print(f"  Warning: Image not found: {original_path}")
                    continue

                # Create unique filename
                image_counter += 1
                ext = os.path.splitext(original_path)[1] or '.jpg'
                new_filename = f"img_{image_counter:04d}{ext}"
                output_image_path = images_path / new_filename

                # Check if image already exists
                if output_image_path.exists() and not overwrite_images:
                    skipped_count += 1
                    # Store relative path even if skipping
                    image_mapping[original_path] = f"images/{new_filename}"
                    continue

                # Resize and copy
                resize_image(original_path, str(output_image_path), max_image_size)

                # Store relative path
                image_mapping[original_path] = f"images/{new_filename}"

        # ...for each image in this PDF file

    # ...for each PDF file

    if skipped_count > 0:
        print(f"✓ Processed {len(image_mapping)} images ({skipped_count} skipped, already exist)\n")
    else:
        print(f"✓ Processed {len(image_mapping)} images\n")
    return image_mapping

# ...def prepare_output_folder(...)


def generate_html(results_data: Dict[str, Any],
                  image_mapping: Dict[str, str],
                  pdf_base_url: Optional[str] = None) -> str:
    """
    Generate HTML content for the visualization.

    Args:
        results_data: Parsed JSON data
        image_mapping: Dict mapping original paths to relative paths
        pdf_base_url: Optional base URL for PDF files

    Returns:
        HTML content as string
    """

    # Prepare data for JavaScript
    figures_data = []
    failed_figures = []

    for pdf_result in results_data['results']:

        pdf_path = pdf_result['pdf_path']
        pdf_filename = pdf_result['pdf_filename']
        pdf_title = pdf_result.get('title', pdf_filename)
        title_extraction_success = pdf_result.get('title_extraction_success', False)

        for img in pdf_result['images']:

            # Check whether this was identified as a map
            if 'map_identification' not in img:
                continue

            map_id = img['map_identification']
            if not map_id.get('is_map', False):
                continue

            # Check whether georeferencing was successful
            if 'georeferencing' in img and img['georeferencing'].get('success', False):
                georef = img['georeferencing']
                coords = georef.get('coordinates')

                if coords and georef.get('confidence', 0) > 0:
                    # Successful georeferencing
                    image_path = img['image_path']
                    relative_image_path = image_mapping.get(image_path, '')

                    if not relative_image_path:
                        continue

                    # Determine PDF URL or path
                    if pdf_base_url:
                        # Use base URL + filename
                        pdf_url = pdf_base_url.rstrip('/') + '/' + pdf_filename
                    else:
                        # Use original local path
                        pdf_url = pdf_path

                    figure_data = {
                        'pdf_filename': pdf_filename,
                        'pdf_path': pdf_url,
                        'pdf_title': pdf_title,
                        'title_extraction_success': title_extraction_success,
                        'image_filename': img['image_filename'],
                        'image_path': relative_image_path,
                        'page': img['page'],
                        'confidence': georef['confidence'],
                        'explanation': georef['explanation'],
                        'coordinates': coords,
                        'text_context': img.get('text_context', {})
                    }
                    figures_data.append(figure_data)
                else:
                    # Failed georeferencing (confidence 0 or missing coords)
                    failed_figures.append({
                        'pdf_filename': pdf_filename,
                        'pdf_title': pdf_title,
                        'image_filename': img['image_filename'],
                        'page': img['page']
                    })
            else:
                # Map identification succeeded but georeferencing failed
                failed_figures.append({
                    'pdf_filename': pdf_filename,
                    'pdf_title': pdf_title,
                    'image_filename': img['image_filename'],
                    'page': img['page']
                })

        # ...for each image in this PDF file

    # ...for each PDF file

    # Convert to JSON for embedding
    # Use separators to avoid extra whitespace and ensure compact JSON
    figures_json = json.dumps(figures_data, indent=2, separators=(',', ': '))
    failed_json = json.dumps(failed_figures, indent=2, separators=(',', ': '))

    # Load prompts for chat functionality
    prompts_path = Path(__file__).parent / "prompts.json"
    try:
        with open(prompts_path, 'r') as f:
            prompts = json.load(f)
        prompts_json = json.dumps(prompts, indent=2, separators=(',', ': '))
    except Exception as e:
        print(f"  Warning: Could not load prompts.json: {e}")
        prompts_json = json.dumps({
            "suggest_question": "",
            "chat": ""
        }, separators=(',', ': '))

    # Generate HTML from template
    # Use a custom formatter to avoid issues with { } in JSON
    html = VISUALIZATION_HTML.replace('{figures_json}', figures_json)
    html = html.replace('{failed_json}', failed_json)
    html = html.replace('{prompts_json}', prompts_json)

    # Convert {{ and }} to single braces (they were escaped for .format())
    html = html.replace('{{', '{').replace('}}', '}')

    return html

# ...def generate_html(...)


def sample_results(results_data: Dict[str, Any],
                   sample_size: int,
                   random_seed: int) -> Dict[str, Any]:
    """
    Randomly sample georeferenced figures from results data.

    Args:
        results_data: Full results data from JSON
        sample_size: Number of figures to sample
        random_seed: Random seed for reproducibility

    Returns:
        New results_data dict with only sampled figures
    """

    # Extract all successfully georeferenced (pdf_result, image) pairs
    georeferenced_pairs = []

    for pdf_result in results_data['results']:
        for img in pdf_result['images']:
            # Check if this is a successfully georeferenced map
            if ('map_identification' in img and
                img['map_identification'].get('is_map', False) and
                'georeferencing' in img and
                img['georeferencing'].get('success', False)):
                georeferenced_pairs.append((pdf_result, img))

    total_georeferenced = len(georeferenced_pairs)

    if sample_size >= total_georeferenced:
        # No sampling needed, return original data
        return results_data

    # Set random seed and sample
    random.seed(random_seed)
    sampled_pairs = random.sample(georeferenced_pairs, sample_size)

    # Reconstruct results_data with only sampled images
    # Group sampled images by PDF
    pdf_to_images = {}
    for pdf_result, img in sampled_pairs:
        pdf_path = pdf_result['pdf_path']
        if pdf_path not in pdf_to_images:
            pdf_to_images[pdf_path] = {
                'pdf_result': pdf_result,
                'images': []
            }
        pdf_to_images[pdf_path]['images'].append(img)

    # Build new results list
    new_results = []
    for pdf_path, data in pdf_to_images.items():
        pdf_result = data['pdf_result'].copy()
        pdf_result['images'] = data['images']
        new_results.append(pdf_result)

    # Create new results_data
    sampled_results_data = results_data.copy()
    sampled_results_data['results'] = new_results

    return sampled_results_data

# ...def sample_results(...)


#%% Command-line driver

def main():
    """
    Command-line driver
    """

    parser = argparse.ArgumentParser(
        description="Create interactive visualization of georeferencing results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create visualization with default settings
  python -m georeferencing.georeferencing_visualizer results.json --output-folder viz

  # Custom image size
  python -m georeferencing.georeferencing_visualizer results.json --output-folder viz --max-image-size 1024

  # Randomly sample 50 figures for quick preview (uses seed=0 by default)
  python -m georeferencing.georeferencing_visualizer results.json --output-folder viz --sample 50

  # Sample with different random seed
  python -m georeferencing.georeferencing_visualizer results.json --output-folder viz --sample 50 --random-seed 42
        """
    )

    parser.add_argument(
        'input_file',
        help='JSON file from georeference_files.py'
    )
    parser.add_argument(
        '--output-folder', '-o',
        required=True,
        help='Output folder for HTML and images'
    )
    parser.add_argument(
        '--max-image-size',
        type=int,
        default=800,
        help='Maximum image dimension in pixels (default: 800)'
    )
    parser.add_argument(
        '--overwrite-images',
        action='store_true',
        help='Overwrite existing images in output folder (default: skip existing images)'
    )
    parser.add_argument(
        '--sample',
        type=int,
        metavar='N',
        help='Randomly sample N georeferenced figures (default: use all figures)'
    )
    parser.add_argument(
        '--random-seed',
        type=int,
        default=0,
        help='Random seed for sampling (default: 0)'
    )
    parser.add_argument(
        '--pdf-base-url',
        help='Base URL for PDF files (e.g., https://example.com/papers/). If provided, PDF links will use this URL + filename instead of local paths.'
    )

    # Show help if no arguments provided
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Validate input
    if not os.path.exists(args.input_file):
        print(f"❌ Error: Input file not found: {args.input_file}")
        sys.exit(1)

    print("=== Georeferencing Visualizer ===\n")

    try:
        # Load results
        print("Loading results...")
        with open(args.input_file, 'r') as f:
            results_data = json.load(f)
        print(f"✓ Loaded results from {args.input_file}\n")

        # Apply sampling if requested
        if args.sample is not None:
            # Count total georeferenced figures before sampling
            total_georeferenced = sum(
                1 for pdf in results_data['results']
                for img in pdf['images']
                if ('map_identification' in img and
                    img['map_identification'].get('is_map', False) and
                    'georeferencing' in img and
                    img['georeferencing'].get('success', False))
            )

            if args.sample < total_georeferenced:
                print(f"Sampling {args.sample} of {total_georeferenced} georeferenced figures (seed={args.random_seed})...")
                results_data = sample_results(results_data, args.sample, args.random_seed)
                print(f"✓ Sampled {args.sample} figures\n")
            else:
                print(f"Sample size ({args.sample}) >= total georeferenced figures ({total_georeferenced}), using all figures\n")

        # Prepare output folder and copy images
        print("Preparing output folder...")
        image_mapping = prepare_output_folder(args.output_folder, results_data, args.max_image_size, args.overwrite_images)

        # Generate HTML
        print("Generating HTML...")
        html_content = generate_html(results_data, image_mapping, args.pdf_base_url)

        # Write HTML file
        output_html = Path(args.output_folder) / "index.html"
        with open(output_html, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✓ Created {output_html}\n")

        # Summary
        num_georeferenced = sum(
            1 for pdf in results_data['results']
            for img in pdf['images']
            if 'georeferencing' in img and img['georeferencing'].get('success', False)
        )

        print("🎉 Visualization complete!")
        print(f"  Output folder: {args.output_folder}")
        print(f"  Georeferenced figures: {num_georeferenced}")
        print(f"  Open {output_html} in your browser to view")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
