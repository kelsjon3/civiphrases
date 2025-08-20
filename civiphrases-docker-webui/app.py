#!/usr/bin/env python3
"""
Flask web interface for civiphrases CLI tool.
Provides a simple web GUI to run civiphrases commands.
"""

import os
import subprocess
import threading
import time
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

def clear_logs():
    """Clear the job logs and reset state."""
    global job_state
    job_state = {
        'running': False,
        'logs': [],
        'start_time': None,
        'end_time': None,
        'success': None,
        'command': None
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
