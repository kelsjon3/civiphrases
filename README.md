# civiphrases

A Python CLI tool that fetches Stable Diffusion prompts from Civitai, uses a local LLM to intelligently categorize phrases, and generates wildcard files for ComfyUI Dynamic Prompts.

## Features

- **Fetch prompts** from Civitai users or collections via API
- **Intelligent phrase categorization** using local LLM (Text Generation WebUI)
- **Generate wildcard files** for ComfyUI Dynamic Prompts
- **Offline-friendly** with local caching and processing
- **Robust error handling** with retry logic and rate limiting
- **Incremental updates** - only processes new/changed content

## Prerequisites

1. **Text Generation WebUI** running with OpenAI-compatible API enabled
2. **Python 3.8+**
3. Optional: **Civitai API key** for higher rate limits

## Installation

```bash
# Clone or download the project
cd prompt_generator

# Install the package
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Setup

### 1. Configure Text Generation WebUI

Start Text Generation WebUI with OpenAI-compatible API:

```bash
# Example command (adjust paths as needed)
python server.py --api --api-port 5001 --listen
```

The API should be accessible at `http://127.0.0.1:5001/v1`

### 2. Environment Variables

Create a `.env` file or set environment variables:

```bash
# Text Generation WebUI settings
export TGW_BASE_URL=http://127.0.0.1:5001/v1
export TGW_API_KEY=local

# Optional: Civitai API key for higher rate limits
export CIVITAI_API_KEY=your_api_key_here

# Optional: Custom output directory
export OUT_DIR=./out
```

## Usage

### Basic Commands

```bash
# Fetch prompts from a user and generate wildcards
python -m civiphrases refresh --user someUsername --max-items 300

# Fetch from a collection
python -m civiphrases refresh --collection https://civitai.com/collections/12345

# Or use collection ID directly
python -m civiphrases refresh --collection 12345

# Just fetch without processing
python -m civiphrases fetch --user someUsername --max-items 500

# Process already-fetched data
python -m civiphrases build --batch-size 15

# Dry run to see what would be generated
python -m civiphrases refresh --user someUsername --dry-run
```

### Command Options

#### Global Options
- `--verbose, -v`: Enable verbose logging

#### Fetch/Refresh Options
- `--user <username>`: Fetch from specific Civitai user
- `--collection <id_or_url>`: Fetch from Civitai collection
- `--max-items <N>`: Maximum items to fetch (default: 200)
- `--include-nsfw`: Include NSFW content (default: false)

#### Build/Refresh Options
- `--batch-size <N>`: Prompts per LLM request (default: 10)
- `--dry-run`: Show preview without writing files
- `--overwrite`: Rebuild even if outputs exist
- `--remove-generic`: Remove generic quality boosters

## Output Structure

The tool creates the following output structure:

```
out/
  wildcards/              # ComfyUI wildcard files
    subjects.txt          # People, creatures, objects, characters
    styles.txt            # Art movements, render engines, mediums
    aesthetics.txt        # Lighting, mood, colors, atmosphere
    techniques.txt        # Camera terms, composition, lens settings
    quality_boosters.txt  # "masterpiece", "best quality", etc.
    negatives.txt         # Undesirable features
    modifiers.txt         # Generic adjectives
    prompt_bank.txt       # All non-negative phrases combined
  
  state/                  # Internal state files
    items.jsonl           # Cached Civitai items
    phrases.jsonl         # Processed phrases with metadata
    manifest.json         # Run metadata and statistics
  
  logs/                   # Log files
    civiphrases.log       # Application logs
```

## ComfyUI Integration

1. In ComfyUI, install the **ComfyUI Dynamic Prompts** extension
2. Point the wildcards directory to your output: `out/wildcards/`
3. Use wildcards in your prompts:
   - `__subjects__` - Random subject
   - `__styles__` - Random style
   - `__aesthetics__` - Random aesthetic element
   - `__techniques__` - Random technique
   - `__prompt_bank__` - Any non-negative phrase

Example ComfyUI prompt:
```
__subjects__, __styles__, __aesthetics__, __techniques__, masterpiece, highly detailed
Negative: __negatives__
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TGW_BASE_URL` | `http://127.0.0.1:5001/v1` | Text Generation WebUI API URL |
| `TGW_API_KEY` | `local` | API key for TGW |
| `CIVITAI_API_KEY` | None | Optional Civitai API key |
| `OUT_DIR` | `./out` | Output directory path |

### Rate Limiting

The tool includes built-in rate limiting and retry logic:
- 1 second delay between API requests
- Exponential backoff on errors (429, 5xx)
- Maximum 3 retry attempts

## How It Works

1. **Fetch**: Downloads prompts and metadata from Civitai API
2. **Normalize**: Cleans up text, handles long prompts by chunking
3. **Classify**: Uses local LLM to split prompts into categorized phrases
4. **Deduplicate**: Removes duplicates while preserving casing
5. **Output**: Writes organized wildcard files for ComfyUI

The LLM categorizes phrases into:
- **subjects**: People, creatures, objects, characters, props
- **styles**: Art movements, render engines, mediums, franchises
- **aesthetics**: Lighting, mood, colors, atmosphere  
- **techniques**: Camera terms, composition, lens settings
- **quality_boosters**: Enhancement terms like "masterpiece"
- **negatives**: Undesirable features like "blurry"
- **modifiers**: Generic adjectives like "intricate"

## Troubleshooting

### Common Issues

**"No models available"**
- Ensure Text Generation WebUI is running with `--api` flag
- Check that `TGW_BASE_URL` points to the correct endpoint

**"Rate limited" errors**
- Add `CIVITAI_API_KEY` to your environment
- Reduce `--max-items` or add delays

**"No valid prompts found"**
- Try different users/collections
- Use `--include-nsfw` if appropriate
- Check logs for specific errors

### Debugging

```bash
# Enable verbose logging
python -m civiphrases refresh --user someUser --verbose

# Check logs
tail -f out/logs/civiphrases.log

# Test with small batch
python -m civiphrases refresh --user someUser --max-items 10 --dry-run
```

## Development

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black civiphrases/

# Lint code  
flake8 civiphrases/
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

