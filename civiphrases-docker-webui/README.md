# Civiphrases Docker Web UI

A beautiful web interface for the Civiphrases CLI tool, packaged in Docker for easy deployment on Unraid and other container platforms.

## Features

- 🎨 **Modern Web UI** - Clean, responsive interface with real-time log streaming
- 🐳 **Docker Ready** - Optimized for Unraid deployment with proper volume mapping
- 🔄 **Real-time Logs** - Watch the processing progress live in your browser
- ⚙️ **Easy Configuration** - All settings available through the web form
- 🔒 **Secure** - Runs as non-root user with proper permissions

## Quick Start

### For Local Testing

1. **Test the build locally first:**
   ```bash
   cd civiphrases-docker-webui
   ./build-local.sh
   ```

2. **For local docker-compose deployment:**
   ```bash
   ./build-and-run.sh
   ```

### For Remote/Unraid Deployment

1. **Deploy to remote Docker host:**
   ```bash
   ./deploy_to_docker.sh
   ```

2. **Access the web interface:**
   - Navigate to `http://your-docker-host-ip:5000`
   - Fill in the form and start generating wildcards!

### Manual Docker Run

```bash
docker run -d \
  --name civiphrases-webui \
  -p 5000:5000 \
  -v /mnt/user/appdata/civiphrases:/output \
  -e TGW_BASE_URL=http://host.docker.internal:5001/v1 \
  --add-host host.docker.internal:host-gateway \
  civiphrases-webui:latest
```

## Prerequisites

### Text Generation WebUI Setup

You need a running Text Generation WebUI instance with OpenAI-compatible API enabled:

1. **Install Text Generation WebUI** (if not already installed)
2. **Enable OpenAI API** by adding these flags when starting:
   ```bash
   python server.py --listen --api --extensions openai
   ```
3. **Default URL**: `http://127.0.0.1:5001/v1`

### Civitai API Key (Optional)

- Required for private content or to avoid rate limits
- Get your API key from [Civitai Settings](https://civitai.com/user/account)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OUT_DIR` | `/output` | Directory where wildcard files are saved |
| `TGW_BASE_URL` | `http://127.0.0.1:5001/v1` | Text Generation WebUI API URL |
| `TGW_API_KEY` | `local` | API key for Text Generation WebUI |
| `CIVITAI_API_KEY` | (none) | Optional Civitai API key |

### Volume Mapping

| Container Path | Description | Recommended Host Path |
|----------------|-------------|----------------------|
| `/output` | Generated wildcard files | `/mnt/user/appdata/civiphrases` |
| `/app/logs` | Application logs (optional) | `/mnt/user/appdata/civiphrases/logs` |

## Usage

1. **Access the web interface** at `http://your-server:5000`

2. **Configure your settings:**
   - **Civitai API Key**: Optional, for private content
   - **Source**: Choose either Username OR Collection URL
   - **Output Path**: Leave as `/output` (mapped to your host directory)
   - **Max Items**: Number of items to process (default: 200)
   - **TGW Settings**: Configure your Text Generation WebUI connection

3. **Click "Run Civiphrases"** and watch the logs in real-time

4. **Find your wildcards** in the mapped output directory:
   ```
   /mnt/user/appdata/civiphrases/
   ├── wildcards/
   │   ├── subjects.txt
   │   ├── styles.txt
   │   ├── aesthetics.txt
   │   ├── techniques.txt
   │   ├── quality_boosters.txt
   │   ├── negatives.txt
   │   ├── modifiers.txt
   │   └── prompt_bank.txt
   └── state/
       ├── items.jsonl
       ├── phrases.jsonl
       └── manifest.json
   ```

## Unraid Integration

### Using Community Applications

If you want to add this to Unraid's Community Applications, create a template:

1. Save the provided XML template (see comments in `docker-compose.yml`)
2. Submit to CA repository or use as a local template

### Unraid Docker Settings

- **Network Type**: Bridge
- **Console shell command**: bash
- **Privileged**: No
- **WebUI**: `http://[IP]:[PORT:5000]`

## Troubleshooting

### Common Issues

1. **"Connection refused" to Text Generation WebUI**
   - Ensure TGW is running with `--api` and `--extensions openai` flags
   - Check the `TGW_BASE_URL` in the web form
   - For Docker: Use `host.docker.internal:5001` instead of `localhost:5001`

2. **Permission errors with output directory**
   - Ensure the mapped directory has proper permissions
   - The container runs as user ID 1000

3. **Civitai API rate limits**
   - Add your Civitai API key in the web form
   - Reduce `max_items` for testing

### Logs

View container logs:
```bash
docker logs civiphrases-webui
```

### Health Check

The container includes a health check endpoint:
```bash
curl http://localhost:5000/health
```

## Development

To modify and rebuild:

```bash
# Make changes to app.py or templates/
docker build -t civiphrases-webui:latest .
docker-compose down && docker-compose up -d
```

## Remote Deployment

### Quick Deploy to Remote Docker Host

If you have a remote Docker host (like Unraid), use the provided deployment script:

```bash
# Deploy to remote host (edit IP in script if needed)
./deploy_to_docker.sh
```

This script will:
- Copy all files to the remote host
- Build the Docker image remotely
- Deploy using docker-compose
- Verify the deployment

### Remote Management

Use the management script to control your remote deployment:

```bash
# Show available commands
./manage_remote.sh

# Common operations
./manage_remote.sh status    # Check container status
./manage_remote.sh logs      # View live logs
./manage_remote.sh restart   # Restart the container
./manage_remote.sh files     # List generated wildcard files
```

## File Structure

```
civiphrases-docker-webui/
├── app.py                # Flask web application
├── templates/
│   └── index.html        # Web UI template
├── requirements.txt      # Python dependencies
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose configuration
├── build-local.sh        # Local build and test script
├── build-and-run.sh      # Local deployment script
├── deploy_to_docker.sh   # Remote deployment script
├── manage_remote.sh      # Remote management utilities
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## License

Same as the civiphrases CLI tool this is based on.

---

🎉 **Happy wildcard generating!** Drop your generated wildcards into ComfyUI's Dynamic Prompts extension and start creating amazing art!
