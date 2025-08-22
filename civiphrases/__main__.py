"""CLI interface for civiphrases."""

import logging
import os
import sys
from typing import Optional

import click

from . import __version__
from .config import config
from .civitai import CivitaiClient, load_existing_items, save_items_incrementally, calculate_item_checksum
from .normalize import create_prompt_worklist, filter_empty_prompts
from .classify import LLMClassifier
from .writeout import process_and_write_phrases, generate_dry_run_summary, WildcardWriter


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Create logs directory
    config.ensure_directories()
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(config.logs_dir, 'civiphrases.log'),
                encoding='utf-8'
            )
        ]
    )


@click.group()
@click.version_option(version=__version__)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def cli(verbose: bool):
    """civiphrases - Generate ComfyUI wildcard files from Civitai prompts."""
    setup_logging(verbose)


@cli.command()
@click.option('--user', help='Civitai username to fetch from')
@click.option('--collection', help='Civitai collection ID or URL to fetch from')
@click.option('--max-items', default=200, help='Maximum number of items to fetch')
@click.option('--include-nsfw', is_flag=True, help='Include NSFW content')
@click.option('--dry-run', is_flag=True, help='Print stats without writing files')
@click.option('--replace', is_flag=True, help='Replace existing items instead of incremental update')
def fetch(user: Optional[str], collection: Optional[str], max_items: int, include_nsfw: bool, dry_run: bool, replace: bool):
    """Fetch prompts from Civitai and update local cache."""
    logger = logging.getLogger(__name__)
    
    # Validate input
    if not user and not collection:
        click.echo("Error: Must specify either --user or --collection", err=True)
        sys.exit(1)
    
    if user and collection:
        click.echo("Error: Cannot specify both --user and --collection", err=True)
        sys.exit(1)
    
    config.ensure_directories()
    
    try:
        client = CivitaiClient()
        
        # Load existing items (only if not replacing)
        if not replace:
            existing_items = load_existing_items(config.items_file)
            logger.info(f"Loaded {len(existing_items)} existing items")
        else:
            existing_items = {}
            logger.info("Replace mode: ignoring existing items")
        
        # Fetch new items
        new_items = []
        updated_items = []
        skipped_items = 0
        
        if user:
            source_info = {"type": "user", "identifier": user}
            items_generator = client.fetch_user_images(user, max_items, include_nsfw)
        else:
            source_info = {"type": "collection", "identifier": collection}
            items_generator = client.fetch_collection_images(collection, max_items, include_nsfw)
        
        for item in items_generator:
            item_id = item["item_id"]
            
            # Calculate checksum for this item
            checksum = calculate_item_checksum(item["positive"], item["negative"])
            item["checksum"] = checksum
            
            if not replace and item_id in existing_items:
                # Check if content has changed
                if existing_items[item_id].get("checksum") != checksum:
                    logger.info(f"Item {item_id} has been updated")
                    updated_items.append(item)
                else:
                    skipped_items += 1
            else:
                new_items.append(item)
        
        total_fetched = len(new_items) + len(updated_items)
        
        if not dry_run:
            # Save items
            if replace:
                # Replace entire file
                if new_items:
                    save_items_incrementally(config.items_file, new_items, replace=True)
                    logger.info(f"Replaced items file with {len(new_items)} new items")
            else:
                # Incremental update
                if new_items or updated_items:
                    save_items_incrementally(config.items_file, new_items + updated_items, replace=False)
        
        # Print summary
        click.echo(f"\nFetch Summary:")
        click.echo(f"  New items: {len(new_items)}")
        click.echo(f"  Updated items: {len(updated_items)}")
        click.echo(f"  Skipped (unchanged): {skipped_items}")
        click.echo(f"  Total fetched: {total_fetched}")
        
        if dry_run:
            click.echo("\n(Dry run - no files were written)")
        
    except Exception as e:
        logger.error(f"Error during fetch: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--batch-size', default=10, help='Number of prompts per LLM batch')
@click.option('--dry-run', is_flag=True, help='Print stats without writing files')
@click.option('--overwrite', is_flag=True, help='Rebuild even if outputs exist')
@click.option('--remove-generic', is_flag=True, help='Remove generic quality boosters')
def build(batch_size: int, dry_run: bool, overwrite: bool, remove_generic: bool):
    """Process cached items and generate wildcard files."""
    logger = logging.getLogger(__name__)
    
    config.ensure_directories()
    
    # Check if we have cached items
    if not os.path.exists(config.items_file):
        click.echo("Error: No cached items found. Run 'fetch' command first.", err=True)
        sys.exit(1)
    
    # Check if outputs already exist (unless overwrite is specified)
    if not overwrite and not dry_run and os.path.exists(config.phrases_file):
        click.echo("Error: Output files already exist. Use --overwrite to rebuild.", err=True)
        sys.exit(1)
    
    try:
        # Load cached items
        existing_items = load_existing_items(config.items_file)
        if not existing_items:
            click.echo("Error: No items found in cache.", err=True)
            sys.exit(1)
        
        logger.info(f"Processing {len(existing_items)} cached items")
        
        # Convert to list for processing
        items_list = list(existing_items.values())
        
        # Create worklist
        worklist = create_prompt_worklist(items_list)
        worklist = filter_empty_prompts(worklist)
        
        if not worklist:
            click.echo("Error: No valid prompts found to process.", err=True)
            sys.exit(1)
        
        logger.info(f"Created worklist with {len(worklist)} prompts")
        
        # Initialize LLM classifier
        click.echo("Initializing LLM classifier...")
        classifier = LLMClassifier()
        
        # Classify prompts
        click.echo(f"Classifying {len(worklist)} prompts...")
        classified_phrases = classifier.classify_worklist(worklist, batch_size)
        
        if not classified_phrases:
            click.echo("Error: No phrases were successfully classified.", err=True)
            sys.exit(1)
        
        logger.info(f"Classified {len(classified_phrases)} phrases")
        
        # Determine source info from items
        source_types = set(item["source"]["type"] for item in items_list)
        if len(source_types) == 1:
            source_type = list(source_types)[0]
            identifiers = set(item["source"]["identifier"] for item in items_list)
            source_info = {
                "type": source_type,
                "identifier": list(identifiers)[0] if len(identifiers) == 1 else "multiple"
            }
        else:
            source_info = {"type": "mixed", "identifier": "multiple"}
        
        # Configuration used
        config_used = {
            "batch_size": batch_size,
            "remove_generic": remove_generic,
            "tgw_base_url": config.tgw_base_url,
            "out_dir": config.out_dir
        }
        
        if dry_run:
            # Generate dry run summary
            writer = WildcardWriter()
            deduped_phrases = writer.dedupe_phrases(classified_phrases)
            filtered_phrases = writer.apply_quality_filter(deduped_phrases, remove_generic)
            
            summary = generate_dry_run_summary(filtered_phrases)
            click.echo(summary)
        else:
            # Process and write files
            phrase_counts = process_and_write_phrases(
                classified_phrases=classified_phrases,
                source_info=source_info,
                items_fetched=len(items_list),
                items_skipped=0,
                model_name=classifier.model_name,
                config_used=config_used,
                remove_generic_quality=remove_generic
            )
            
            # Print summary
            click.echo(f"\nBuild Summary:")
            click.echo(f"  Total items processed: {len(items_list)}")
            click.echo(f"  Total phrases classified: {len(classified_phrases)}")
            click.echo(f"  Phrases by category:")
            for category, count in sorted(phrase_counts.items()):
                if category != "prompt_bank":
                    click.echo(f"    {category}: {count}")
            click.echo(f"  Wildcard files written to: {config.wildcards_dir}")
    
    except Exception as e:
        logger.error(f"Error during build: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--user', help='Civitai username to fetch from')
@click.option('--collection', help='Civitai collection ID or URL to fetch from')
@click.option('--max-items', default=200, help='Maximum number of items to fetch')
@click.option('--include-nsfw', is_flag=True, help='Include NSFW content')
@click.option('--batch-size', default=10, help='Number of prompts per LLM batch')
@click.option('--dry-run', is_flag=True, help='Print stats without writing files')
@click.option('--overwrite', is_flag=True, help='Rebuild even if outputs exist')
@click.option('--remove-generic', is_flag=True, help='Remove generic quality boosters')
def refresh(
    user: Optional[str], 
    collection: Optional[str], 
    max_items: int, 
    include_nsfw: bool,
    batch_size: int, 
    dry_run: bool, 
    overwrite: bool, 
    remove_generic: bool
):
    """Fetch from Civitai and build wildcard files in one command."""
    logger = logging.getLogger(__name__)
    
    # Validate input
    if not user and not collection:
        click.echo("Error: Must specify either --user or --collection", err=True)
        sys.exit(1)
    
    if user and collection:
        click.echo("Error: Cannot specify both --user and --collection", err=True)
        sys.exit(1)
    
    try:
        # First run fetch
        click.echo("=== FETCH PHASE ===")
        ctx = click.get_current_context()
        ctx.invoke(fetch, 
                  user=user, 
                  collection=collection, 
                  max_items=max_items, 
                  include_nsfw=include_nsfw,
                  dry_run=dry_run,
                  replace=True)
        
        # Then run build
        click.echo("\n=== BUILD PHASE ===")
        ctx.invoke(build,
                  batch_size=batch_size,
                  dry_run=dry_run,
                  overwrite=overwrite,
                  remove_generic=remove_generic)
        
        if not dry_run:
            click.echo(f"\n✅ Refresh completed! Wildcard files are ready in: {config.wildcards_dir}")
    
    except Exception as e:
        logger.error(f"Error during refresh: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
