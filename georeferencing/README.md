# Georeferencing Tools

This folder contains a demonstration implementation of map georeferencing in ecology research papers using multimodal LLMs.  Sample output from this library, for 15 randomly-selected papers from our benchmark dataset, is available [here](https://dmorris.net/misc/georeferencing/benchmark-visualization_20251009_15/).

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Setup](#setup)
- [Georeferencing](#georeferencing)
- [Visualization](#visualization)
- [Future work](#future-work)
- [Contributing](#contributing)

## Overview

This package provides tools to:

1. Extract images from PDF files of ecology papers
2. Identify which images are maps using a "small" LLM (Gemini 2.5 Flash by default)
3. Georeference those maps using a "large" LLM (Gemini 2.5 Pro by default), using the images themselves, as well as surrounding text context from the PDF file
4. Output structured results with geographic coordinates
5. Visualize those results on a map

## Installation

From the repository root:

```bash
pip install -e .
```

## Setup

Create a file named `GEMINI_API_KEY.txt` in your working directory containing your Google AI API key:

```bash
echo "YOUR_API_KEY_HERE" > GEMINI_API_KEY.txt
```

## Georeferencing

### Basic usage

Process PDFs with default settings (synchronous API, Gemini 2.5 Flash for map ID, Gemini 2.5 Pro for georeferencing):

```bash
python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json
```

### Using the Gemini Batch API (~50% less expensive than the synchronous API)

Use the Gemini batch API for large jobs:

```bash
python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json --batch
```

Batch jobs can take several hours to complete but cost ~50% less than synchronous API.

### To test on a small set

Process only the first N PDFs for testing:

```bash
python -m georeferencing.georeference_files /path/to/pdfs --output-file results.json --max-pdfs 5
```

### Resume interrupted jobs

If a job is interrupted, resume from the checkpoint file:

```bash
python -m georeferencing.georeference_files --resume georeferencing_20250109_120000_status.json
```

### Command-line options

#### Required arguments

- `input_folder` - Folder containing PDF files to process
- `--output-file`, `-o` - Output JSON file for results

#### Optional arguments

##### Model configuration

- `--small-model` - Model for map identification (default: `gemini-2.5-flash`)
- `--large-model` - Model for georeferencing (default: `gemini-2.5-pro`)
- `--image-size` - Max dimension for resized images in pixels (default: 768)

##### API configuration

- `--batch` - Use batch API instead of synchronous (50% discount, but slower)
- `--poll-interval` - Seconds between batch job polls (default: 60)

##### Processing options

- `--recursive`, `-r` - Recursively search for PDF files
- `--max-pdfs` - Maximum number of PDFs to process (for testing)
- `--temporary-folder` - Folder for temporary image storage (default: system temp)

##### Job management

- `--checkpoint-interval` - Save checkpoint every N queries (default: 10)
- `--resume` - Resume from status JSON file

##### Other

- `--auto-confirm`, `-y` - Skip cost confirmation prompt

### Workflow

The script performs these steps:

1. **PDF Enumeration** - Finds all PDF files in the input folder
2. **Image and Title Extraction** - Extracts images and title from each PDF
   - Uses heuristics to extract paper titles from PDF metadata or the first page of the PDF
   - Deduplicates images using MD5 hashes
   - Filters out images smaller than 100px on either dimension
   - Extracts text from first page, image page, and adjacent pages
3. **Cost Estimation** - Estimates API costs and asks for confirmation
4. **Map Identification** - Uses small model to classify which images are maps
5. **Georeferencing** - Uses large model to georeference maps with text context (currently the first page of the PDF file, the page on which the map occurs, and the pages before and after the map)
6. **Results Generation** - Outputs structured JSON with all results

### Output format

The output JSON file contains:

```json
{
  "parameters": {
    "input_folder": "/path/to/pdfs",
    "temporary_folder": "/tmp/georef_xyz",
    "small_model": "gemini-2.5-flash",
    "large_model": "gemini-2.5-pro",
    "image_size": 768,
    "use_batch": false,
    "timestamp": "2025-01-09 12:00:00"
  },
  "summary": {
    "total_pdfs": 50,
    "total_images": 423,
    "total_maps_identified": 87,
    "total_maps_georeferenced": 62
  },
  "results": [
    {
      "pdf_path": "/path/to/paper.pdf",
      "pdf_filename": "paper.pdf",
      "num_images_extracted": 8,
      "images": [
        {
          "image_path": "/tmp/georef_xyz/paper_page003_img001.jpg",
          "image_filename": "paper_page003_img001.jpg",
          "page": 2,
          "dimensions": {"width": 1024, "height": 768},
          "map_identification": {
            "is_map": true,
            "confidence": 0.95,
            "reasoning": "This is a satellite image showing a study area...",
            "success": true
          },
          "georeferencing": {
            "confidence": 0.85,
            "explanation": "Identified from visible coordinates and paper abstract mentioning Yellowstone...",
            "success": true,
            "coordinates": {
              "upper_left": {"lat": 45.123, "lon": -110.456},
              "upper_right": {"lat": 45.123, "lon": -110.123},
              "lower_left": {"lat": 44.789, "lon": -110.456},
              "lower_right": {"lat": 44.789, "lon": -110.123}
            }
          }
        }
      ]
    }
  ]
}
```

### Cost estimation

The script estimates costs before processing (for Gemini 2.5 Flash and Pro only).

The assumptions used for cost estimation are:

- Map identification prompt: ~300 tokens
- Map identification response: ~200 tokens
- Georeferencing prompt: ~1000 tokens (includes text from multiple pages)
- Georeferencing response: ~200 tokens
- Image tokens: 258 per 768×768 tile
- Gemini 2.5 Flash/Pro pricing as of October 2025

### Checkpointing and resuming

The script creates status files (`georeferencing_TIMESTAMP_status.json`) that allow resuming interrupted jobs:

- Saves progress after every N queries (configurable with `--checkpoint-interval`)
- Status file contains all extracted images, map identification results, and georeferencing results
- Resume with: `python -m georeferencing.georeference_files --resume <status-file>`
- Status file is automatically cleaned up on successful completion

When resuming, model settings and image size are locked from the original job.

### Prompts

Prompts for map identification and georeferencing are stored in `prompts.json`. You can customize them by editing this file.

**Map identification prompt:**

- Distinguishes maps from charts, graphs, photos, etc.
- Returns JSON with `is_map`, `confidence`, and `reasoning`

**Georeferencing prompt:**

- Uses map image + text context from paper
- Returns JSON with four-corner coordinates, confidence, and explanation
- Handles insets (uses smallest area as AOI)
- Provides coordinates only if confidence > 0

### Troubleshooting

**"GEMINI_API_KEY.txt not found"**
- Create the file in your working directory with your API key

**"No PDF files found"**
- Check that the input folder contains PDF files
- Try `--recursive` if PDFs are in subdirectories

**Cost estimate shows wrong amount**
- Cost estimation only works for Gemini 2.5 Flash and Pro, and is hard-coded to 2025 pricing
- Estimate assumes the default image submission size of 768px on the long side; actual cost varies with `--image-size`
- Estimate assumes 1 map per paper; actual may differ

**Batch job takes too long**
- Batch jobs can take several hours for large datasets
- Use synchronous API for faster results (2x cost)
- Monitor progress with status file timestamps

### Advanced usage

#### Custom models

Use different Gemini models (must be from Gemini family):

```bash
python -m georeferencing.georeference_files /path/to/pdfs \
  --output-file results.json \
  --small-model gemini-2.0-flash \
  --large-model gemini-2.0-pro-exp
```

#### Custom temporary folder

Specify where extracted images should be stored:

```bash
python -m georeferencing.georeference_files /path/to/pdfs \
  --output-file results.json \
  --temporary-folder /scratch/georef_temp
```

#### Auto-confirm for scripting

Skip the cost confirmation prompt (useful for scripts/automation):

```bash
python -m georeferencing.georeference_files /path/to/pdfs \
  --output-file results.json \
  --auto-confirm
```

## Visualization

The `georeferencing_visualizer.py` script creates an interactive HTML map visualization of georeferencing results.

### Basic usage

Create visualization from georeferencing output:

```bash
python -m georeferencing.georeferencing_visualizer results.json --output-folder viz
```

This creates a self-contained visualization in the `viz/` folder with:
- `index.html` - Interactive map visualization
- `images/` - Resized copies of georeferenced map images

Open `viz/index.html` in any web browser to view the results.

### Command-line options

#### Required arguments

- `input_file` - JSON file from georeference_files.py
- `--output-folder`, `-o` - Output folder for HTML and images

#### Optional arguments

- `--max-image-size` - Maximum image dimension in pixels (default: 800)

### Features

The visualization provides an interactive interface with three main areas:

**Left sidebar: figure list**

- Lists all successfully georeferenced figures
- Each entry shows: paper filename, page number, confidence percentage
- Click any figure to view on map
- Separate "Failed Georeferencing" section shows maps that couldn't be georeferenced

**Center panel: interactive Map**

- OpenStreetMap basemap with standard pan/zoom controls
- Blue polygons show georeferenced areas (4-corner coordinates)
- Hover over polygon to see details in right sidebar
- Click polygon to select and navigate
- Map automatically fits to show all georeferenced areas on load

**Right sidebar: details view**

- Appears when hovering over or clicking a figure
- Shows:
  - Paper title (currently uses filename)
  - Link to original PDF file
  - Map image (scaled to fit sidebar)
  - Page number and image filename
  - Georeferencing confidence score
  - Model's explanation of how it georeferenced the map

**Navigation**

- Previous/Next buttons appear at bottom after selecting a figure
- Cycle through all georeferenced figures sequentially
- Map automatically pans and zooms to each figure

**Multiple maps per paper**

- Each georeferenced map gets its own entry in the list
- Papers with multiple maps appear multiple times
- Example: "paper.pdf - Page 3" and "paper.pdf - Page 7"

### Output structure

The output folder contains:

```
root/
├── index.html          # Main visualization file (open in browser)
└── images/             # Resized map images
    ├── img_0001.jpg
    ├── img_0002.jpg
    └── ...
```

All images are referenced by relative path.

Images are automatically resized to `--max-image-size` (default 800px) to reduce file size while maintaining quality for visualization.

## Future work

* Track actual tokens submitted for real jobs, use that to update cost estimation constants (e.g. the typical number of maps per PDF file)
* Timeout/rate errors are handled gracefully, but not retried; add a retry mechanism
* Parallelize PDF processing and LLM submission
* Support local LLMs via Ollama
* Add validation against ground truth, when run on the benchmark dataset

### Chat interface improvements

* Add support for multi-turn conversation history (currently each question is independent)
* Pre-generate suggested questions during the visualization step (currently generated on-demand)
* Include full PDF content instead of just text context for better question answering
* Add server-side API key management to avoid requiring users to enter their own key (currently keys are stored in browser localStorage)

## Contributing

This is part of the [ecology georeferencing benchmark dataset project](https://github.com/google-research/ecology-georeferencing). For issues and contributions, see the main repository README.
