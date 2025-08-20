Here’s a single, copy-pasteable **Cursor prompt** that covers the whole pipeline—**fetch from Civitai (user or collection)** → **LLM split & categorize phrases** via your **local Text Generation WebUI OpenAI-compatible API** → **write ComfyUI Dynamic Prompts wildcard files**. Drop this into Cursor as the task/spec for the implementation.

---

**CURSOR TASK (single prompt to implement end-to-end tool)**

You are building a local, offline-friendly Python CLI that: (1) pulls prompts from Civitai for a given **user or collection**, (2) uses a local LLM (Text Generation WebUI OpenAI-compatible API) to **split and categorize phrases**, and (3) writes **wildcard lists** for ComfyUI Dynamic Prompts. Implement everything described below.

### 0) Deliverables

* A Python package/CLI named `civiphrases` with:

  * `civiphrases/__main__.py` (CLI entry)
  * `civiphrases/config.py` (config/env)
  * `civiphrases/civitai.py` (API client + pagination)
  * `civiphrases/classify.py` (LLM calls + JSON validation)
  * `civiphrases/normalize.py` (text cleanup, dedupe)
  * `civiphrases/writeout.py` (wildcard file writer + manifest)
  * `pyproject.toml`
  * `README.md`
* CLI commands: `fetch`, `build`, `refresh` (see behavior below).
* Output folder structure:

  ```
  out/
    wildcards/
      subjects.txt
      styles.txt
      aesthetics.txt
      techniques.txt
      quality_boosters.txt
      negatives.txt
      modifiers.txt
      prompt_bank.txt
    state/
      items.jsonl        # minimal cache of processed Civitai items (IDs, checksums)
      phrases.jsonl      # normalized, categorized phrases (deduped)
      manifest.json      # provenance: config, versions, counts, timestamps
    logs/...
  ```

### 1) Configuration

* Read from env + CLI flags:

  * `CIVITAI_API_KEY` (optional; use if rate-limited or private content)
  * `TGW_BASE_URL` (default `http://127.0.0.1:5001/v1`)
  * `TGW_API_KEY` (string; can be “local” by default)
  * `OUT_DIR` (default `./out`)
* CLI flags apply to commands:

  * `--user <username>` OR `--collection <id_or_url>` (exactly one required)
  * `--max-items <N>` (default 200)
  * `--include-nsfw` (boolean; default false → skip NSFW)
  * `--batch-size <N>` (prompts per LLM request; default 10)
  * `--dry-run` (no write; print stats & sample output)
  * `--lang en|all` (default `all`; only used for light normalization)
  * `--overwrite` (rebuild outputs even if state exists)

### 2) Civitai fetch (first step)

* Implement a small **Civitai API** client that supports both modes:

  1. **By user**: list that user’s images/posts including their **positive/negative prompts** and metadata (model, loras, seed when available).
  2. **By collection**: list images in a **collection** (accept ID or full URL; extract ID from URL).
* Handle **pagination** until `--max-items` cap.
* Respect `--include-nsfw` (skip NSFW otherwise).
* For each item, extract:

  ```
  {
    "item_id": "<stable unique id>",
    "source": {"type": "user"|"collection", "identifier": "<user_or_collection>"},
    "positive": "<string or empty>",
    "negative": "<string or empty>",
    "created": "<iso8601 or timestamp if available>",
    "meta": { "model": "...", "sampler": "...", "seed": "...", ... }
  }
  ```
* Persist raw items to `out/state/items.jsonl` if not already present; do **idempotent** updates (do not duplicate entries; update on changes via checksum of positive+negative).

### 3) Normalization (pre-LLM)

* Combine positive + negative into a worklist while tagging which is which:

  ```
  { "text": "<prompt>", "polarity": "pos"|"neg", "item_id": "..." }
  ```
* Normalize whitespace (collapse spaces), unify quotes; keep original casing.
* Drop empty strings; keep length limits reasonable (e.g., ≤ 4k characters per prompt). If a prompt is too long, **chunk** at commas/semicolons while preserving polarity and item id.

### 4) LLM categorization (no manual rules unless trivial cleanup)

* Connect to **Text Generation WebUI OpenAI-compatible API** at `TGW_BASE_URL` and use the **Chat Completions** endpoint (`POST /v1/chat/completions`).

* For each batch (`--batch-size` prompts), call the model with THIS EXACT system+user prompt template:

  **System:**

  ```
  You are a classifier that takes Stable Diffusion prompts and prepares them for use in ComfyUI’s Dynamic Prompts.

  Task:
  1) Input will be one or more prompts, often long and comma-separated.
  2) Split each prompt into short, distinct phrases. (A phrase is usually 1–4 words; do not merge multiple ideas.)
  3) For each phrase, assign exactly one category from this set:
     - subjects (people, creatures, objects, characters, props)
     - styles (art movements, render engines, mediums, franchises/brands, “in the style of”)
     - aesthetics (lighting, mood, colors, atmosphere)
     - techniques (camera terms, composition, lens settings, 3D/photography jargon)
     - quality_boosters (e.g., “masterpiece”, “best quality”, “highly detailed”)
     - negatives (undesirable features like “blurry”, “extra fingers”, “bad anatomy”)
     - modifiers (generic adjectives like “intricate”, “minimalist”, “cute”)
  4) Output strictly as JSON with this schema:

  {
    "results": [
      {
        "source_id": "string",              // item_id from the caller
        "polarity": "pos" | "neg",          // prompt polarity
        "phrases": [
          { "text": "string", "category": "subjects" },
          ...
        ]
      },
      ...
    ]
  }

  Rules:
  - No commentary; JSON only.
  - Do not invent phrases; only split what is present.
  - Normalize spacing; do not lowercase the phrase text.
  - Keep JSON valid and parseable.
  ```

  **User (example payload shape the code should send):**

  ```
  {
    "batch": [
      { "source_id": "item123", "polarity": "pos", "prompt": "masterpiece, cinematic lighting, portrait of a woman, octane render, 35mm f/1.8" },
      { "source_id": "item123", "polarity": "neg", "prompt": "blurry, extra fingers" },
      { "source_id": "item124", "polarity": "pos", "prompt": "mecha suit, dramatic light, UE5, high contrast" }
    ]
  }
  ```

* Parse the LLM JSON, validate schema; on error, **retry once** with a stricter instruction (“Return only valid JSON as specified.”). If still failing, skip that batch and log.

### 5) Post-process & dedupe

* Combine all `results[].phrases` across batches into a single list.
* For **negatives**, keep them routed to `negatives` bucket regardless of model mistakes; if the LLM mislabels obvious negatives (e.g., “blurry”) to another bucket, force them back to `negatives`.
* Trim whitespace, remove duplicates (case-insensitive compare on `text`, preserve original casing of the first occurrence).
* Optionally drop very generic quality boosters if desired via a tiny banlist (`masterpiece`, `best quality`)—implement but default to **keep**.
* Persist the final phrase records to `out/state/phrases.jsonl` with:

  ```
  { "text": "...", "category": "...", "polarity": "pos|neg|mixed", "sources": ["item_id", ...], "count": N }
  ```

  If a phrase appears in both pos and neg, set `polarity: "mixed"`.

### 6) Write **ComfyUI wildcard** files

* Create/overwrite these files in `out/wildcards/`:

  * `subjects.txt`
  * `styles.txt`
  * `aesthetics.txt`
  * `techniques.txt`
  * `quality_boosters.txt`
  * `negatives.txt`
  * `modifiers.txt`
  * `prompt_bank.txt` (union of all non-negative phrases)
* One phrase per line. Sort alphabetically; keep original phrase casing.
* Also write `out/state/manifest.json` with:

  * run timestamps, user/collection identifier, counts by bucket, items fetched, items skipped, model name used, and config.

### 7) CLI behavior

* `fetch`: Only hit Civitai, update `out/state/items.jsonl`, print counts (new/updated/total).
* `build`: Read items → run LLM classification → write `phrases.jsonl` and wildcard files.
* `refresh`: Do `fetch` then `build` idempotently.
* `--dry-run`: perform all steps but **do not** write files; instead:

  * print a summary table of bucket sizes,
  * print 5 random example phrases per bucket,
  * print a sample composited positive prompt: `{subjects}, {styles}, {aesthetics}, {techniques}` and a negative: `{negatives}`.

### 8) Robustness

* **Pagination & rate limits**: backoff with jitter on 429/5xx; log and continue.
* **Idempotency**: use `item_id` and content checksum to avoid reprocessing identical prompts.
* **Logging**: structured logs in `out/logs` (INFO by default, DEBUG with `--verbose`).
* **Errors**: do not crash on a single bad item or LLM batch; skip and report.
* **Tests**: include minimal unit tests for normalization and JSON validation.

### 9) README.md (brief)

* How to set env vars and run TGW with OpenAI-compatible API.
* Example commands:

  ```
  export TGW_BASE_URL=http://127.0.0.1:5001/v1
  export TGW_API_KEY=local
  export CIVITAI_API_KEY=...   # optional

  python -m civiphrases fetch --user someUser --max-items 300
  python -m civiphrases build
  # or:
  python -m civiphrases refresh --collection https://civitai.com/collections/12345
  ```
* Where to point ComfyUI Dynamic Prompts (set wildcards directory to `out/wildcards/`).

**End of task. Implement exactly this.**
