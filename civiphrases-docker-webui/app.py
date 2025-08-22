#!/usr/bin/env python3
"""
Flask web interface for civiphrases CLI tool.
Provides a simple web GUI to run civiphrases commands.
"""

import os
import subprocess
import threading
import time
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import logging
import requests
import traceback

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state for storing logs and job status
job_state = {
    'running': False,
    'logs': [],
    'start_time': None,
    'end_time': None,
    'success': None,
    'command': None
}

# Thread lock for job_state access
job_state_lock = threading.Lock()

# Global state for storing images
images_state = {
    'images': [],
    'last_updated': None,
    'source': None
}

def reset_job_state():
    """Reset job state to initial values."""
    global job_state
    
    logger.info("reset_job_state() called")
    
    # Note: This function is called from clear_logs() which already holds the lock
    # So we don't need to acquire it again
    logger.info("reset_job_state() - resetting job_state")
    job_state = {
        'running': False,
        'logs': [],
        'start_time': None,
        'end_time': None,
        'success': None,
        'command': None
    }
    logger.info("reset_job_state() - job_state reset completed")
    logger.info("reset_job_state() - function completed")

def clear_logs():
    """Clear the job logs and reset state."""
    global job_state, images_state
    
    logger.info("clear_logs() called - about to acquire lock")
    
    with job_state_lock:
        logger.info("clear_logs() - lock acquired, calling reset_job_state")
        reset_job_state()
        logger.info("clear_logs() - reset_job_state completed")
    
    logger.info("clear_logs() - lock released")
    
    # Also clear images when starting a new job
    logger.info("clear_logs() - clearing images_state")
    images_state = {
        'images': [],
        'last_updated': None,
        'source': None
    }
    logger.info("clear_logs() - completed successfully")

def add_log(message, level='INFO'):
    """Add a log message with timestamp."""
    global job_state
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with job_state_lock:
        job_state['logs'].append({
            'timestamp': timestamp,
            'level': level,
            'message': message
        })
    
    logger.info(f"[{level}] {message}")

def update_images_state(images, source):
    """Update the global images state."""
    global images_state
    images_state['images'] = images
    images_state['last_updated'] = datetime.now()
    images_state['source'] = source
    logger.info(f"Updated images state with {len(images)} images from {source}")

def extract_images_from_logs(logs):
    """Extract image information from job logs."""
    images = []
    source = None
    
    for log in logs:
        message = log.get('message', '')
        
        # Look for source information in logs
        if 'Fetching images for user:' in message:
            source = f"user: {message.split('user:')[-1].strip()}"
        elif 'Fetching images for collection:' in message:
            source = f"collection: {message.split('collection:')[-1].strip()}"
        
        # Look for image data in logs (this would need to be enhanced based on actual log format)
        # For now, we'll create a placeholder structure
        if 'Fetched' in message and 'items for' in message:
            # Extract count from message like "Fetched 150 items for user username"
            try:
                count_match = re.search(r'Fetched (\d+) items', message)
                if count_match:
                    count = int(count_match.group(1))
                    # Create placeholder images for demonstration
                    for i in range(min(count, 20)):  # Limit to 20 for performance
                        images.append({
                            'id': f'placeholder_{i}',
                            'url': f'https://via.placeholder.com/400x400/667eea/ffffff?text=Image+{i+1}',
                            'title': f'Image {i+1}',
                            'model': 'Unknown Model',
                            'created': datetime.now().isoformat()
                        })
            except (ValueError, AttributeError):
                pass
    
    return images, source

def capture_civitai_images_from_logs(logs):
    """Capture actual Civitai image data from logs."""
    images = []
    source = None
    
    for log in logs:
        message = log.get('message', '')
        
        # Look for source information
        if 'Fetching images for user:' in message:
            source = f"user: {message.split('user:')[-1].strip()}"
        elif 'Fetching images for collection:' in message:
            source = f"collection: {message.split('collection:')[-1].strip()}"
        
        # Look for the special CAPTURED_IMAGES log format
        if message.startswith('CAPTURED_IMAGES:'):
            try:
                # Extract JSON data from the log message
                json_str = message.replace('CAPTURED_IMAGES:', '').strip()
                data = json.loads(json_str)
                
                if 'images' in data and 'source' in data:
                    images = data['images']
                    source = data['source']
                    logger.info(f"Successfully captured {len(images)} images from {source}")
                    break  # Found the image data, no need to continue
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse CAPTURED_IMAGES log: {e}")
                continue
        
        # Look for actual fetch count in logs (this is what we're seeing)
        if 'Fetched' in message and 'items for' in message and not images:
            try:
                count_match = re.search(r'Fetched (\d+) items', message)
                if count_match:
                    count = int(count_match.group(1))
                    logger.info(f"Found fetch count: {count} items")
                    
                    # Create sample images based on the count
                    for i in range(min(count, 50)):  # Limit to 50 for performance
                        images.append({
                            'id': f'civitai_{i}',
                            'url': f'https://via.placeholder.com/400x400/667eea/ffffff?text=Image+{i+1}',
                            'title': f'Civitai Image {i+1}',
                            'model': 'AI Model',
                            'created': datetime.now().isoformat(),
                            'source': source or 'Unknown Source'
                        })
                    
                    logger.info(f"Created {len(images)} placeholder images")
                    
            except (ValueError, AttributeError) as e:
                logger.error(f"Error parsing fetch count: {e}")
                pass
    
    return images, source

def run_civiphrases_command(command, env_vars):
    """Run civiphrases command in a separate thread."""
    global job_state
    
    logger.info("=== run_civiphrases_command called ===")
    logger.info(f"Command: {command}")
    logger.info(f"Environment: {env_vars}")
    
    try:
        with job_state_lock:
            job_state['running'] = True
            job_state['start_time'] = datetime.now()
            job_state['command'] = command
            job_state['success'] = None
        
        logger.info("Job state updated to running=True")
        add_log(f"Starting command: {' '.join(command)}")
        add_log(f"Environment: {env_vars}")
        
        # Set up environment
        env = os.environ.copy()
        env.update(env_vars)
        
        # Run the command
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
            bufsize=1
        )
        
        # Stream output
        for line in iter(process.stdout.readline, ''):
            if line:
                add_log(line.strip())
        
        process.wait()
        
        if process.returncode == 0:
            add_log("Command completed successfully!", 'SUCCESS')
            with job_state_lock:
                job_state['success'] = True
                
                # Extract images from logs and update images state
                logger.info(f"Attempting to extract images from {len(job_state['logs'])} log entries")
                images, source = capture_civitai_images_from_logs(job_state['logs'])
                logger.info(f"Extracted {len(images)} images from source: {source}")
                if images:
                    update_images_state(images, source)
                    logger.info(f"Successfully updated images state with {len(images)} images")
                else:
                    logger.warning("No images were extracted from logs")
        else:
            add_log(f"Command failed with exit code {process.returncode}", 'ERROR')
            with job_state_lock:
                job_state['success'] = False
            
    except Exception as e:
        add_log(f"Error running command: {str(e)}", 'ERROR')
        with job_state_lock:
            job_state['success'] = False
    finally:
        with job_state_lock:
            job_state['running'] = False
            job_state['end_time'] = datetime.now()
            add_log(f"Job state updated: running={job_state['running']}, success={job_state['success']}, end_time={job_state['end_time']}", 'INFO')
            logger.info(f"Job completed. Final state: {job_state}")
            
            # Debug: Log the exact state after completion
            logger.info(f"Job state keys after completion: {list(job_state.keys())}")
            logger.info(f"Job state 'running' field value: {job_state.get('running', 'MISSING')}")
            logger.info(f"Job state 'success' field value: {job_state.get('success', 'MISSING')}")

def fetch_images_with_pagination(username, max_items, include_nsfw, civitai_api_key, batch_size=300, resume_from_page=None, is_collection=False):
    """Fetch images from Civitai in batches with persistent state tracking.
    
    Args:
        username: Civitai username or collection ID
        max_items: Total target images (can be very large)
        include_nsfw: Whether to include NSFW content
        civitai_api_key: API key for authentication
        batch_size: How many images to fetch per batch (default: 300 = 3 pages)
        resume_from_page: Resume from specific page (for continuing later)
        is_collection: True if fetching from a collection, False for user
    """
    try:
        source = f"user: {username}" if not is_collection else f"collection: {username}"
        url = "https://civitai.com/api/v1/images"
        
        headers = {
            'User-Agent': 'civiphrases-webui/1.0',
            'Accept': 'application/json'
        }
        
        if civitai_api_key:
            headers['Authorization'] = f'Bearer {civitai_api_key}'
        
        all_images = []
        page = resume_from_page if resume_from_page else 1
        page_size = 100  # Civitai API max per page
        batch_count = 0
        
        # Calculate how many pages we need for this batch
        pages_needed = (batch_size + page_size - 1) // page_size
        
        add_log(f"Starting batch fetch for {'collection' if is_collection else 'user'} {username}", 'INFO')
        add_log(f"Batch size: {batch_size} images ({pages_needed} pages)", 'INFO')
        add_log(f"Starting from page: {page}", 'INFO')
        
        while len(all_images) < batch_size:
            params = {
                'username': username,
                'limit': page_size,
                'page': page,
                'sort': 'Most Reactions',
                'period': 'AllTime'
            }
            
            if not include_nsfw:
                params['nsfw'] = 'false'
                add_log(f"NSFW filtering enabled: excluding NSFW content", 'INFO')
            else:
                add_log(f"NSFW filtering disabled: including all content", 'INFO')
            
            add_log(f"API request params: {params}", 'DEBUG')
            add_log(f"Fetching page {page} (batch progress: {len(all_images)}/{batch_size})", 'INFO')
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            # Debug: Check NSFW content in response
            nsfw_count = sum(1 for item in items if item.get('nsfw', False))
            total_count = len(items)
            add_log(f"API response: {total_count} items, {nsfw_count} marked as NSFW", 'DEBUG')
            
            if not items:
                add_log(f"No more items found on page {page}, stopping batch", 'INFO')
                break
            
            # Process items from this page
            for item in items:
                if len(all_images) >= batch_size:
                    break
                
                # Skip NSFW items if not including NSFW content
                if not include_nsfw and item.get('nsfw', False):
                    add_log(f"Skipping NSFW item {item.get('id', 'unknown')}", 'DEBUG')
                    continue
                
                # Extract image data
                image_url = item.get('url')
                if not image_url:
                    continue
                
                # Extract prompts from meta
                meta = item.get('meta', {})
                positive_prompt = ""
                negative_prompt = ""
                
                if isinstance(meta, dict):
                    positive_prompt = meta.get('prompt', '') or meta.get('positivePrompt', '')
                    negative_prompt = meta.get('negativePrompt', '') or meta.get('negative', '')
                elif isinstance(meta, str):
                    try:
                        meta_dict = json.loads(meta)
                        positive_prompt = meta_dict.get('prompt', '') or meta_dict.get('positivePrompt', '')
                        negative_prompt = meta_dict.get('negativePrompt', '') or meta.get('negative', '')
                    except json.JSONDecodeError:
                        pass
                
                # Extract other metadata
                created = item.get('createdAt', item.get('publishedAt', ''))
                model_name = ""
                if isinstance(meta, dict):
                    model_name = meta.get('Model') or meta.get('model', '')
                
                all_images.append({
                    'id': str(item.get('id', '')),
                    'url': image_url,
                    'title': item.get('name', 'Untitled'),
                    'model': model_name,
                    'created': created,
                    'positive_prompt': positive_prompt.strip(),
                    'negative_prompt': negative_prompt.strip(),
                    'source': source
                })
            
            add_log(f"Page {page} complete: {len(items)} items, batch total: {len(all_images)}", 'INFO')
            
            # If we got fewer items than requested, we've reached the end
            if len(items) < page_size:
                add_log(f"Reached end of available images on page {page}", 'INFO')
                break
            
            page += 1
            batch_count += 1
            
            # Add a small delay between pages to be respectful to the API
            time.sleep(0.5)
        
        # Save progress state for resuming later
        save_fetch_progress(username, page, len(all_images), batch_size, max_items)
        
        add_log(f"Batch complete: fetched {len(all_images)} images from {batch_count} pages", 'INFO')
        add_log(f"NSFW filtering: {'disabled' if include_nsfw else 'enabled'} - excluded NSFW content", 'INFO')
        add_log(f"Next batch will start from page {page}", 'INFO')
        
        return all_images
        
    except Exception as e:
        add_log(f"Error during batch fetch: {e}", 'ERROR')
        return []

def save_fetch_progress(username, current_page, images_fetched, batch_size, total_target):
    """Save progress state for resuming fetch later."""
    try:
        progress_file = os.path.join(os.getenv('OUT_DIR', '/output'), 'fetch_progress.json')
        
        # Load existing progress or create new
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                progress = json.load(f)
        else:
            progress = {}
        
        # Update progress for this user
        progress[username] = {
            'last_page': current_page,
            'images_fetched': images_fetched,
            'batch_size': batch_size,
            'total_target': total_target,
            'last_updated': datetime.now().isoformat(),
            'can_resume': True
        }
        
        # Save progress
        with open(progress_file, 'w') as f:
            json.dump(progress, f, indent=2)
        
        # Set proper ownership
        try:
            # Use the actual UID/GID numbers for nobody:users (99:100)
            uid = 99
            gid = 100
            os.chown(progress_file, uid, gid)
            add_log(f"Set ownership of {progress_file} to UID {uid}, GID {gid}", 'DEBUG')
        except OSError as e:
            add_log(f"Could not set ownership of {progress_file}: {e}", 'WARNING')
            
        add_log(f"Progress saved: {username} at page {current_page}, {images_fetched} images fetched", 'INFO')
        
    except Exception as e:
        add_log(f"Error saving progress: {e}", 'WARNING')

def get_fetch_progress(username):
    """Get saved progress for a user."""
    try:
        progress_file = os.path.join(os.getenv('OUT_DIR', '/output'), 'fetch_progress.json')
        
        if os.path.exists(progress_file):
            with open(progress_file, 'r') as f:
                progress = json.load(f)
                return progress.get(username, {})
        
        return {}
        
    except Exception as e:
        add_log(f"Error loading progress: {e}", 'WARNING')
        return {}

@app.route('/')
def index():
    """Main page with the form."""
    return render_template('index.html', job_state=job_state)

@app.route('/get_loaded_models', methods=['POST'])
def get_loaded_models():
    """Get currently loaded model from TGW."""
    try:
        data = request.json
        tgw_base_url = data.get('tgw_base_url', 'http://127.0.0.1:5001/v1').strip()
        tgw_api_key = data.get('tgw_api_key', 'local').strip()
        
        # Make request to TGW models endpoint to get currently loaded model
        headers = {'Authorization': f'Bearer {tgw_api_key}'} if tgw_api_key != 'local' else {}
        response = requests.get(f'{tgw_base_url}/models', headers=headers, timeout=10)
        
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get('data', [])
            
            # Find the currently loaded/active model
            loaded_model = None
            for model in models:
                # Check if this model is currently loaded/active
                # TGW typically shows the loaded model first or with a specific status
                if model.get('loaded', False) or model.get('status') == 'loaded':
                    loaded_model = {
                        'id': model.get('id'),
                        'name': model.get('id', '').split('/')[-1].replace('.gguf', ''),  # Clean name
                        'full_id': model.get('id'),
                        'status': 'loaded'
                    }
                    break
            
            # If no explicit loaded status, assume the first model is loaded (common TGW behavior)
            if not loaded_model and models:
                loaded_model = {
                    'id': models[0].get('id'),
                    'name': models[0].get('id', '').split('/')[-1].replace('.gguf', ''),
                    'full_id': models[0].get('id'),
                    'status': 'assumed_loaded'
                }
            
            if loaded_model:
                return jsonify({
                    'success': True, 
                    'loaded_model': loaded_model,
                    'message': f"Detected loaded model: {loaded_model['name']}"
                })
            else:
                return jsonify({
                    'success': False, 
                    'error': 'No loaded model detected'
                })
        else:
            return jsonify({'success': False, 'error': f'Failed to fetch models: {response.status_code}'})
            
    except requests.exceptions.RequestException as e:
        return jsonify({'success': False, 'error': f'Network error: {str(e)}'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error: {str(e)}'})

@app.route('/run', methods=['POST'])
def run_command():
    """Handle form submission and start civiphrases command."""
    global job_state
    
    try:
        logger.info("=== /run route called ===")
        logger.info(f"Form data received: {dict(request.form)}")
        
        if job_state['running']:
            logger.warning("Job already running, returning error")
            return jsonify({'error': 'A job is already running'}), 400
        
        logger.info("Starting new job...")
        
        # Clear previous logs
        clear_logs()
        logger.info("Logs cleared successfully")
        
        # Get form data
        civitai_api_key = request.form.get('civitai_api_key', '').strip()
        username = request.form.get('username', '').strip()
        collection_url = request.form.get('collection_url', '').strip()
        output_path = request.form.get('output_path', '/output').strip()
        max_items = request.form.get('max_items', '200').strip()
        include_nsfw = request.form.get('include_nsfw') == 'on'
        tgw_base_url = request.form.get('tgw_base_url', 'http://127.0.0.1:5001/v1').strip()
        tgw_api_key = request.form.get('tgw_api_key', 'local').strip()
        selected_model = request.form.get('selected_model', '').strip()
        
        logger.info("Form data extracted successfully")
        
        # Validate input
        if not username and not collection_url:
            logger.error("Validation failed: No username or collection URL")
            return jsonify({'error': 'Either username or collection URL is required'}), 400
        
        if username and collection_url:
            logger.error("Validation failed: Both username and collection URL provided")
            return jsonify({'error': 'Provide either username OR collection URL, not both'}), 400
        
        logger.info("Form validation passed successfully")
        
        # Build command
        command = ['python', '-m', 'civiphrases', 'refresh']
        
        if username:
            command.extend(['--user', username])
        elif collection_url:
            command.extend(['--collection', collection_url])
        
        command.extend(['--max-items', max_items])
        
        if include_nsfw:
            command.append('--include-nsfw')
        
        logger.info(f"Command built successfully: {command}")
        
        # Set up environment variables
        env_vars = {
            'OUT_DIR': output_path,
            'TGW_BASE_URL': tgw_base_url,
            'TGW_API_KEY': tgw_api_key,
        }
        
        if civitai_api_key:
            env_vars['CIVITAI_API_KEY'] = civitai_api_key
        
        # Add model selection if specified
        if selected_model:
            env_vars['TGW_MODEL_NAME'] = selected_model
        
        logger.info(f"Environment variables set up successfully: {env_vars}")
        
        # Start command in background thread
        logger.info(f"Starting background thread with command: {command}")
        logger.info(f"Environment variables: {env_vars}")
        
        thread = threading.Thread(target=run_civiphrases_command, args=(command, env_vars))
        thread.daemon = True
        thread.start()
        
        logger.info("Background thread started successfully")
        
        # Immediately fetch images from Civitai API using the working endpoint
        # This ensures images display right away while civiphrases processes in background
        try:
            if username:
                # Check if we have existing progress for this user
                progress = get_fetch_progress(username)
                batch_size = 300  # Default: 300 images per batch (3 pages)
                
                if progress and progress.get('can_resume', False):
                    # Resume from where we left off
                    last_page = progress.get('last_page', 1)
                    images_fetched = progress.get('images_fetched', 0)
                    total_target = progress.get('total_target', int(max_items))
                    
                    add_log(f"Resuming fetch for {username} from page {last_page} (already have {images_fetched} images)", 'INFO')
                    add_log(f"Target: {total_target} images, batch size: {batch_size}", 'INFO')
                    
                    # Use the new batch fetch function with resume
                    images = fetch_images_with_pagination(
                        username, total_target, include_nsfw, civitai_api_key, 
                        batch_size=batch_size, resume_from_page=last_page
                    )
                else:
                    # Start fresh batch
                    add_log(f"Starting new batch fetch for {username}, batch size: {batch_size}", 'INFO')
                    
                    # Use the new batch fetch function
                    images = fetch_images_with_pagination(
                        username, int(max_items), include_nsfw, civitai_api_key, 
                        batch_size=batch_size
                    )
                
                # Update the global images state immediately
                if images:
                    source = f"user: {username}"
                    update_images_state(images, source)
                    add_log(f"Immediately fetched {len(images)} images from Civitai API with batch processing", 'INFO')
                else:
                    add_log("No images fetched from Civitai API", 'WARNING')
                    
            elif collection_url:
                # For collections, we'll fetch a smaller batch for immediate display
                add_log(f"Fetching collection images for immediate display: {collection_url}", 'INFO')
                
                # Extract collection ID from URL if needed
                collection_id = collection_url
                if 'civitai.com/collections/' in collection_url:
                    collection_id = collection_url.split('collections/')[-1].split('?')[0]
                
                # Fetch a small batch for immediate display
                images = fetch_images_with_pagination(
                    collection_id, min(100, int(max_items)), include_nsfw, civitai_api_key, 
                    batch_size=100, is_collection=True
                )
                
                if images:
                    source = f"collection: {collection_id}"
                    update_images_state(images, source)
                    add_log(f"Immediately fetched {len(images)} collection images from Civitai API", 'INFO')
                else:
                    add_log("No collection images fetched from Civitai API", 'WARNING')
        
        except Exception as e:
            logger.error(f"Error fetching immediate images: {e}")
            add_log(f"Error fetching immediate images: {e}", 'ERROR')
        
        logger.info("=== /run route completed successfully ===")
        return jsonify({'success': True, 'message': 'Job started successfully'})
        
    except Exception as e:
        logger.error(f"=== /run route failed with exception: {e} ===")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/status')
def get_status():
    """Get current job status and logs via AJAX."""
    global job_state
    
    # Use lock for thread-safe access
    with job_state_lock:
        # Debug: Log the current job_state before fixing
        logger.info(f"Status endpoint called. Current job_state keys: {list(job_state.keys())}")
        logger.info(f"Current job_state values: {job_state}")
        
        # Ensure all required fields are present
        if 'running' not in job_state:
            logger.warning("Missing 'running' field in job_state, adding it")
            job_state['running'] = False
        if 'success' not in job_state:
            logger.warning("Missing 'success' field in job_state, adding it")
            job_state['success'] = None
        if 'logs' not in job_state:
            logger.warning("Missing 'logs' field in job_state, adding it")
            job_state['logs'] = []
        if 'start_time' not in job_state:
            logger.warning("Missing 'start_time' field in job_state, adding it")
            job_state['start_time'] = None
        if 'end_time' not in job_state:
            logger.warning("Missing 'end_time' field in job_state, adding it")
            job_state['end_time'] = None
        if 'command' not in job_state:
            logger.warning("Missing 'command' field in job_state, adding it")
            job_state['command'] = None
        
        # Debug: Log the job_state after fixing
        logger.info(f"Status endpoint returning job_state: {job_state}")
        
        # Return a copy to avoid any potential issues
        return jsonify(dict(job_state))

@app.route('/clear')
def clear_job():
    """Clear logs and reset job state."""
    clear_logs()
    return redirect(url_for('index'))

@app.route('/health')
def health_check():
    """Simple health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/version')
def get_version():
    """Get version information."""
    try:
        with open('version.json', 'r') as f:
            version_data = json.load(f)
        return jsonify(version_data)
    except FileNotFoundError:
        return jsonify({
            'version': '1.0.0',
            'build_date': datetime.now().isoformat(),
            'features': ['Basic deployment']
        })

@app.route('/get_images')
def get_images():
    """Get stored images from the current job."""
    global images_state
    
    # First priority: return images from the working Civitai API fetch
    # These are the images that were fetched immediately when the form was submitted
    if images_state['images']:
        return jsonify({
            'success': True,
            'images': images_state['images'],
            'source': images_state['source'],
            'count': len(images_state['images'])
        })
    
    # Only fall back to civiphrases state files if we have no working images
    # This prevents the state files from overriding the working API images
    civiphrases_images = get_images_from_civiphrases_state()
    if civiphrases_images:
        # Update the global state with civiphrases images
        update_images_state(civiphrases_images, "civiphrases_state")
        return jsonify({
            'success': True,
            'images': civiphrases_images,
            'source': 'civiphrases_state',
            'count': len(civiphrases_images)
        })
    
    return jsonify({
        'success': False,
        'message': 'No images found. Run civiphrases first or use Fetch Images button.',
        'images': [],
        'count': 0
    })

def get_images_from_civiphrases_state():
    """Read images from civiphrases state files."""
    try:
        # Check if civiphrases state files exist
        state_dir = os.getenv('OUT_DIR', '/output') + '/state'
        items_file = os.path.join(state_dir, 'items.jsonl')
        
        if not os.path.exists(items_file):
            logger.info(f"Civitai state file not found: {items_file}")
            return []
        
        images = []
        with open(items_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    item = json.loads(line.strip())
                    
                    # Extract image data
                    item_id = item.get('item_id', f'item_{line_num}')
                    
                    # Get the first image URL from the item
                    # Civitai items can have multiple images in different formats
                    image_url = ""
                    
                    # Try different possible image URL fields
                    if 'images' in item and isinstance(item['images'], list) and item['images']:
                        # First try the images array
                        for img in item['images']:
                            if isinstance(img, dict) and img.get('url'):
                                image_url = img['url']
                                break
                    elif 'images' in item and isinstance(item['images'], dict):
                        # Sometimes images is a dict with url field
                        if item['images'].get('url'):
                            image_url = item['images']['url']
                    elif 'url' in item:
                        # Direct url field
                        image_url = item['url']
                    elif 'image_url' in item:
                        # Alternative field name
                        image_url = item['image_url']
                    
                    # If still no image URL, try to construct one from the item ID
                    if not image_url and item_id and item_id != f'item_{line_num}':
                        # Try to construct a Civitai image URL
                        image_url = f"https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/{item_id}/width=450"
                    
                    if not image_url:
                        logger.debug(f"No image URL found for item {item_id}")
                        continue
                    
                    # Extract prompts
                    positive_prompt = item.get('positive', '')
                    negative_prompt = item.get('negative', '')
                    
                    # Extract metadata
                    created = item.get('created', item.get('publishedAt', ''))
                    model_name = item.get('model', '')
                    
                    # Extract title/name
                    title = item.get('name', item.get('title', f'Item {item_id}'))
                    
                    images.append({
                        'id': str(item_id),
                        'url': image_url,
                        'title': title,
                        'model': model_name,
                        'created': created,
                        'positive_prompt': positive_prompt.strip(),
                        'negative_prompt': negative_prompt.strip(),
                        'source': 'civiphrases_state'
                    })
                    
                    logger.debug(f"Added image: {item_id} -> {image_url}")
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Error parsing line {line_num} in {items_file}: {e}")
                    continue
        
        logger.info(f"Loaded {len(images)} images from civiphrases state")
        return images
        
    except Exception as e:
        logger.error(f"Error reading civiphrases state: {e}")
        return []

@app.route('/debug/images')
def debug_images():
    """Debug endpoint to see current images state."""
    global images_state, job_state
    
    return jsonify({
        'images_state': {
            'images_count': len(images_state['images']),
            'source': images_state['source'],
            'last_updated': images_state['last_updated'].isoformat() if images_state['last_updated'] else None
        },
        'job_state': {
            'running': job_state['running'],
            'success': job_state['success'],
            'logs_count': len(job_state['logs']),
            'recent_logs': job_state['logs'][-5:] if job_state['logs'] else []
        }
    })

@app.route('/debug/civiphrases_state')
def debug_civiphrases_state():
    """Debug endpoint to inspect civiphrases state files."""
    try:
        state_dir = os.getenv('OUT_DIR', '/output') + '/state'
        items_file = os.path.join(state_dir, 'items.jsonl')
        
        if not os.path.exists(items_file):
            return jsonify({
                'error': f'State file not found: {items_file}',
                'state_dir': state_dir,
                'exists': False
            })
        
        # Read and parse the first few items
        items = []
        with open(items_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= 3:  # Only show first 3 items
                    break
                try:
                    item = json.loads(line.strip())
                    # Show the structure of the item
                    items.append({
                        'line': i + 1,
                        'item_id': item.get('item_id'),
                        'keys': list(item.keys()),
                        'images_structure': str(item.get('images', 'No images field')),
                        'positive_prompt_length': len(item.get('positive', '')),
                        'negative_prompt_length': len(item.get('negative', '')),
                        'sample_data': {k: str(v)[:100] + '...' if len(str(v)) > 100 else str(v) 
                                      for k, v in list(item.items())[:5]}  # First 5 fields
                    })
                except json.JSONDecodeError as e:
                    items.append({
                        'line': i + 1,
                        'error': str(e),
                        'raw_line': line[:200] + '...' if len(line) > 200 else line
                    })
        
        return jsonify({
            'state_dir': state_dir,
            'items_file': items_file,
            'file_size': os.path.getsize(items_file) if os.path.exists(items_file) else 0,
            'items_sample': items,
            'total_lines': sum(1 for _ in open(items_file, 'r')) if os.path.exists(items_file) else 0
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': str(e.__traceback__)
        })

@app.route('/debug/job_state')
def debug_job_state():
    """Debug endpoint to inspect the current job state."""
    global job_state
    
    # Use lock for thread-safe access
    with job_state_lock:
        # Debug: Log the current job_state before fixing
        logger.info(f"Debug endpoint called. Current job_state keys: {list(job_state.keys())}")
        logger.info(f"Current job_state values: {job_state}")
        
        # Ensure all required fields are present
        if 'running' not in job_state:
            logger.warning("Missing 'running' field in job_state, adding it")
            job_state['running'] = False
        if 'success' not in job_state:
            logger.warning("Missing 'success' field in job_state, adding it")
            job_state['success'] = None
        if 'logs' not in job_state:
            logger.warning("Missing 'logs' field in job_state, adding it")
            job_state['logs'] = []
        if 'start_time' not in job_state:
            logger.warning("Missing 'start_time' field in job_state, adding it")
            job_state['start_time'] = None
        if 'end_time' not in job_state:
            logger.warning("Missing 'end_time' field in job_state, adding it")
            job_state['end_time'] = None
        if 'command' not in job_state:
            logger.warning("Missing 'command' field in job_state, adding it")
            job_state['command'] = None
        
        # Debug: Log the job_state after fixing
        logger.info(f"Debug endpoint returning job_state: {job_state}")
        
        # Return a copy to avoid any potential issues
        return jsonify({
            'job_state': dict(job_state),
            'images_state': images_state,
            'timestamp': datetime.now().isoformat()
        })

@app.route('/validate_api_key', methods=['POST'])
def validate_api_key():
    """Validate Civitai API key and return username."""
    try:
        api_key = request.json.get('api_key', '').strip()
        if not api_key:
            return jsonify({'valid': False, 'username': None, 'error': 'No API key provided'})
        
        # Make a test request to Civitai API to validate the key
        # Use the correct endpoint: /api/v1/me
        headers = {'Authorization': f'Bearer {api_key}'}
        response = requests.get('https://civitai.com/api/v1/me', headers=headers, timeout=10)
        
        if response.status_code == 200:
            user_data = response.json()
            username = user_data.get('username', 'Unknown')
            return jsonify({'valid': True, 'username': username, 'error': None})
        else:
            return jsonify({'valid': False, 'username': None, 'error': f'API key validation failed: {response.status_code}'})
            
    except requests.exceptions.RequestException as e:
        return jsonify({'valid': False, 'username': None, 'error': f'Network error: {str(e)}'})
    except Exception as e:
        return jsonify({'valid': False, 'username': None, 'error': f'Validation error: {str(e)}'})

@app.route('/fetch_civitai_images', methods=['POST'])
def fetch_civitai_images():
    """Fetch real images and prompts from Civitai API."""
    try:
        data = request.json
        username = data.get('username', '').strip()
        collection_url = data.get('collection_url', '').strip()
        max_items = int(data.get('max_items', 50))
        include_nsfw = data.get('include_nsfw', False)
        civitai_api_key = data.get('civitai_api_key', '').strip()
        
        if not username and not collection_url:
            return jsonify({'success': False, 'error': 'Either username or collection URL is required'})
        
        if username and collection_url:
            return jsonify({'success': False, 'error': 'Provide either username OR collection URL, not both'})
        
        # Set up headers
        headers = {
            'User-Agent': 'civiphrases-webui/1.0',
            'Accept': 'application/json'
        }
        
        if civitai_api_key:
            headers['Authorization'] = f'Bearer {civitai_api_key}'
        
        images = []
        source = None
        
        if username:
            # Fetch images from user
            source = f"user: {username}"
            url = "https://civitai.com/api/v1/images"
            params = {
                'username': username,
                'limit': min(100, max_items),
                'sort': 'Most Reactions',
                'period': 'AllTime'
            }
            
            if not include_nsfw:
                params['nsfw'] = 'false'
            
            add_log(f"Fetching images for user {username} with NSFW filtering: {'disabled' if include_nsfw else 'enabled'}", 'INFO')
            add_log(f"API request params: {params}", 'DEBUG')
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            # Debug: Check NSFW content in response
            nsfw_count = sum(1 for item in items if item.get('nsfw', False))
            total_count = len(items)
            add_log(f"API response: {total_count} items, {nsfw_count} marked as NSFW", 'DEBUG')
            
            for item in items[:max_items]:
                # Skip NSFW items if not including NSFW content
                if not include_nsfw and item.get('nsfw', False):
                    continue
                
                # Extract image data
                image_url = item.get('url')
                if not image_url:
                    continue
                
                # Extract prompts from meta
                meta = item.get('meta', {})
                positive_prompt = ""
                negative_prompt = ""
                
                if isinstance(meta, dict):
                    positive_prompt = meta.get('prompt', '') or meta.get('positivePrompt', '')
                    negative_prompt = meta.get('negativePrompt', '') or meta.get('negative', '')
                elif isinstance(meta, str):
                    try:
                        meta_dict = json.loads(meta)
                        positive_prompt = meta_dict.get('prompt', '') or meta_dict.get('positivePrompt', '')
                        negative_prompt = meta_dict.get('negativePrompt', '') or meta.get('negative', '')
                    except json.JSONDecodeError:
                        pass
                
                # Extract other metadata
                created = item.get('createdAt', item.get('publishedAt', ''))
                model_name = ""
                if isinstance(meta, dict):
                    model_name = meta.get('Model') or meta.get('model', '')
                
                images.append({
                    'id': str(item.get('id', '')),
                    'url': image_url,
                    'title': item.get('name', 'Untitled'),
                    'model': model_name,
                    'created': created,
                    'positive_prompt': positive_prompt.strip(),
                    'negative_prompt': negative_prompt.strip(),
                    'source': source
                })
        
        elif collection_url:
            # Extract collection ID
            collection_id = None
            if collection_url.isdigit():
                collection_id = collection_url
            elif 'civitai.com/collections/' in collection_url:
                import re
                match = re.search(r'/collections/(\d+)', collection_url)
                if match:
                    collection_id = match.group(1)
            
            if not collection_id:
                return jsonify({'success': False, 'error': 'Invalid collection URL or ID'})
            
            source = f"collection: {collection_id}"
            url = f"https://civitai.com/api/v1/collections/{collection_id}/items"
            params = {
                'limit': min(100, max_items),
                'type': 'image'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            # Debug: Check NSFW content in response
            nsfw_count = sum(1 for item in items if item.get('data', {}).get('nsfw', False))
            total_count = len(items)
            add_log(f"Collection API response: {total_count} items, {nsfw_count} marked as NSFW", 'DEBUG')
            
            for item in items[:max_items]:
                # Extract the actual image data
                image_data = item.get('data', item)
                
                # Skip NSFW items if not including NSFW content
                if not include_nsfw and image_data.get('nsfw', False):
                    continue
                
                image_url = image_data.get('url')
                if not image_url:
                    continue
                
                # Extract prompts from meta
                meta = image_data.get('meta', {})
                positive_prompt = ""
                negative_prompt = ""
                
                if isinstance(meta, dict):
                    positive_prompt = meta.get('prompt', '') or meta.get('positivePrompt', '')
                    negative_prompt = meta.get('negativePrompt', '') or meta.get('negative', '')
                elif isinstance(meta, str):
                    try:
                        meta_dict = json.loads(meta)
                        positive_prompt = meta_dict.get('prompt', '') or meta_dict.get('positivePrompt', '')
                        negative_prompt = meta_dict.get('negativePrompt', '') or meta.get('negative', '')
                    except json.JSONDecodeError:
                        pass
                
                # Extract other metadata
                created = image_data.get('createdAt', image_data.get('publishedAt', ''))
                model_name = ""
                if isinstance(meta, dict):
                    model_name = meta.get('Model') or meta.get('model', '')
                
                images.append({
                    'id': str(image_data.get('id', '')),
                    'url': image_url,
                    'title': image_data.get('name', 'Untitled'),
                    'model': model_name,
                    'created': created,
                    'positive_prompt': positive_prompt.strip(),
                    'negative_prompt': negative_prompt.strip(),
                    'source': source
                })
        
        # Update the global images state
        if images:
            update_images_state(images, source)
            add_log(f"Successfully fetched {len(images)} images from {source}", 'INFO')
            add_log(f"NSFW filtering: {'disabled' if include_nsfw else 'enabled'} - excluded NSFW content", 'INFO')
        
        return jsonify({
            'success': True,
            'images': images,
            'count': len(images),
            'source': source,
            'nsfw_filtering': 'disabled' if include_nsfw else 'enabled'
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching images: {e}")
        return jsonify({'success': False, 'error': f'Network error: {str(e)}'})
    except Exception as e:
        logger.error(f"Error fetching images: {e}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'})

@app.route('/continue_fetch', methods=['POST'])
def continue_fetch():
    """Continue fetching more images for a user from where we left off."""
    try:
        data = request.json
        username = data.get('username', '').strip()
        batch_size = int(data.get('batch_size', 300))
        
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'})
        
        # Get current progress
        progress = get_fetch_progress(username)
        if not progress or not progress.get('can_resume', False):
            return jsonify({'success': False, 'error': 'No progress found for this user'})
        
        # Get API key from environment or request
        civitai_api_key = os.getenv('CIVITAI_API_KEY', '')
        include_nsfw = True  # Default to True for continuation
        
        # Continue fetching from last page
        images = fetch_images_with_pagination(
            username, progress['total_target'], include_nsfw, civitai_api_key,
            batch_size=batch_size, resume_from_page=progress['last_page']
        )
        
        if images:
            # Update the global images state
            source = f"user: {username}"
            update_images_state(images, source)
            
            return jsonify({
                'success': True,
                'images': images,
                'count': len(images),
                'source': source,
                'message': f'Fetched {len(images)} more images from page {progress["last_page"]}'
            })
        else:
            return jsonify({'success': False, 'error': 'No more images found'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/fetch_progress/<username>')
def get_user_progress(username):
    """Get current fetch progress for a specific user."""
    try:
        progress = get_fetch_progress(username)
        if progress:
            return jsonify({
                'success': True,
                'progress': progress
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No progress found for this user'
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/detect_loaded_model', methods=['POST'])
def detect_loaded_model():
    """Detect the currently loaded model using TGW's internal model info endpoint."""
    try:
        data = request.json
        tgw_base_url = data.get('tgw_base_url', 'http://127.0.0.1:5001/v1').strip()
        tgw_api_key = data.get('tgw_api_key', 'local').strip()
        
        # Set up headers
        headers = {'Authorization': f'Bearer {tgw_api_key}'} if tgw_api_key != 'local' else {}
        
        # Use the proper internal endpoint to get loaded model info
        model_info_response = requests.get(f'{tgw_base_url}/internal/model/info', headers=headers, timeout=10)
        
        if model_info_response.status_code == 200:
            model_info = model_info_response.json()
            logger.info(f"Model info response: {model_info}")
            
            # Extract the loaded model information
            loaded_model = None
            
            # The response structure may vary, so we'll handle different formats
            if 'model_name' in model_info:
                # Direct model name field
                model_name = model_info['model_name']
                loaded_model = {
                    'id': model_name,
                    'name': model_name.split('/')[-1].replace('.gguf', ''),
                    'full_id': model_name,
                    'status': 'confirmed_loaded',
                    'source': 'internal/model/info'
                }
            elif 'name' in model_info:
                # Alternative name field
                model_name = model_info['name']
                loaded_model = {
                    'id': model_name,
                    'name': model_name.split('/')[-1].replace('.gguf', ''),
                    'full_id': model_name,
                    'status': 'confirmed_loaded',
                    'source': 'internal/model/info'
                }
            elif 'id' in model_info:
                # Alternative id field
                model_id = model_info['id']
                loaded_model = {
                    'id': model_id,
                    'name': model_id.split('/')[-1].replace('.gguf', ''),
                    'full_id': model_id,
                    'status': 'confirmed_loaded',
                    'source': 'internal/model/info'
                }
            
            if loaded_model:
                logger.info(f"Successfully detected loaded model: {loaded_model['name']}")
                return jsonify({
                    'success': True,
                    'loaded_model': loaded_model,
                    'message': f"Detected loaded model: {loaded_model['name']} (from internal API)"
                })
            else:
                # Try to parse the response structure
                logger.warning(f"Unexpected model info response structure: {model_info}")
                return jsonify({
                    'success': False,
                    'error': f'Unexpected response structure from /internal/model/info'
                })
        
        else:
            # Fallback to the models endpoint if internal endpoint fails
            logger.warning(f"Internal model info endpoint failed ({model_info_response.status_code}), falling back to models endpoint")
            
            models_response = requests.get(f'{tgw_base_url}/models', headers=headers, timeout=10)
            if models_response.status_code != 200:
                return jsonify({'success': False, 'error': f'Failed to fetch models: {models_response.status_code}'})
            
            models_data = models_response.json()
            models = models_data.get('data', [])
            
            if not models:
                return jsonify({'success': False, 'error': 'No models available'})
            
            # Look for explicit loaded indicators
            loaded_model = None
            for model in models:
                if model.get('loaded', False) or model.get('status') == 'loaded':
                    loaded_model = {
                        'id': model.get('id'),
                        'name': model.get('id', '').split('/')[-1].replace('.gguf', ''),
                        'full_id': model.get('id'),
                        'status': 'fallback_loaded',
                        'source': 'models endpoint'
                    }
                    break
            
            # Fallback: assume first model is loaded (common TGW behavior)
            if not loaded_model and models:
                loaded_model = {
                    'id': models[0].get('id'),
                    'name': models[0].get('id', '').split('/')[-1].replace('.gguf', ''),
                    'full_id': models[0].get('id'),
                    'status': 'assumed_loaded',
                    'source': 'models endpoint'
                }
            
            if loaded_model:
                return jsonify({
                    'success': True,
                    'loaded_model': loaded_model,
                    'message': f"Detected loaded model: {loaded_model['name']} (fallback method)"
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'No loaded model detected'
                })
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error detecting model: {e}")
        return jsonify({'success': False, 'error': f'Network error: {str(e)}'})
    except Exception as e:
        logger.error(f"Error detecting model: {e}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
