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

# Global state for storing images
images_state = {
    'images': [],
    'last_updated': None,
    'source': None
}

def clear_logs():
    """Clear the job logs and reset state."""
    global job_state, images_state
    job_state = {
        'running': False,
        'logs': [],
        'start_time': None,
        'end_time': None,
        'success': None,
        'command': None
    }
    # Also clear images when starting a new job
    images_state = {
        'images': [],
        'last_updated': None,
        'source': None
    }

def add_log(message, level='INFO'):
    """Add a log message with timestamp."""
    global job_state
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
    
    try:
        job_state['running'] = True
        job_state['start_time'] = datetime.now()
        job_state['command'] = command
        job_state['success'] = None
        
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
            job_state['success'] = False
            
    except Exception as e:
        add_log(f"Error running command: {str(e)}", 'ERROR')
        job_state['success'] = False
    finally:
        job_state['running'] = False
        job_state['end_time'] = datetime.now()

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
    
    if job_state['running']:
        return jsonify({'error': 'A job is already running'}), 400
    
    # Clear previous logs
    clear_logs()
    
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
    
    # Validate input
    if not username and not collection_url:
        return jsonify({'error': 'Either username or collection URL is required'}), 400
    
    if username and collection_url:
        return jsonify({'error': 'Provide either username OR collection URL, not both'}), 400
    
    # Build command
    command = ['python', '-m', 'civiphrases', 'refresh']
    
    if username:
        command.extend(['--user', username])
    elif collection_url:
        command.extend(['--collection', collection_url])
    
    command.extend(['--max-items', max_items])
    
    if include_nsfw:
        command.append('--include-nsfw')
    
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
    
    # Start command in background thread
    thread = threading.Thread(target=run_civiphrases_command, args=(command, env_vars))
    thread.daemon = True
    thread.start()
    
    return redirect(url_for('index'))

@app.route('/status')
def get_status():
    """Get current job status and logs via AJAX."""
    return jsonify(job_state)

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
    
    # First try to get images from civiphrases state files
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
    
    # Fall back to the stored images state
    if images_state['images']:
        return jsonify({
            'success': True,
            'images': images_state['images'],
            'source': images_state['source'],
            'count': len(images_state['images'])
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
                    
                    # Get the first image URL from the item (civitai items can have multiple images)
                    image_url = ""
                    if 'images' in item and item['images']:
                        image_url = item['images'][0].get('url', '')
                    elif 'url' in item:
                        image_url = item['url']
                    
                    if not image_url:
                        continue
                    
                    # Extract prompts
                    positive_prompt = item.get('positive', '')
                    negative_prompt = item.get('negative', '')
                    
                    # Extract metadata
                    created = item.get('created', item.get('publishedAt', ''))
                    model_name = item.get('model', '')
                    
                    images.append({
                        'id': str(item_id),
                        'url': image_url,
                        'title': item.get('name', f'Item {item_id}'),
                        'model': model_name,
                        'created': created,
                        'positive_prompt': positive_prompt.strip(),
                        'negative_prompt': negative_prompt.strip(),
                        'source': 'civiphrases_state'
                    })
                    
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
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            for item in items[:max_items]:
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
                        negative_prompt = meta_dict.get('negativePrompt', '') or meta_dict.get('negative', '')
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
            
            for item in items[:max_items]:
                # Extract the actual image data
                image_data = item.get('data', item)
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
                        negative_prompt = meta_dict.get('negativePrompt', '') or meta_dict.get('negative', '')
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
            logger.info(f"Successfully fetched {len(images)} images from {source}")
        
        return jsonify({
            'success': True,
            'images': images,
            'source': source,
            'count': len(images)
        })
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching images: {e}")
        return jsonify({'success': False, 'error': f'Network error: {str(e)}'})
    except Exception as e:
        logger.error(f"Error fetching images: {e}")
        return jsonify({'success': False, 'error': f'Error: {str(e)}'})

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
