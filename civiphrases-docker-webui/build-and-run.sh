#!/bin/bash

# Build and run script for Civiphrases Docker Web UI
# This script builds the Docker image and starts the container

echo "🏗️  Building Civiphrases Docker Web UI..."

# Build the Docker image
docker build -t civiphrases-webui:latest .

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    
    # Stop existing container if running
    echo "🛑 Stopping existing container..."
    docker-compose down 2>/dev/null || true
    
    # Start the new container
    echo "🚀 Starting container..."
    docker-compose up -d
    
    if [ $? -eq 0 ]; then
        echo "✅ Container started successfully!"
        echo "🌐 Web UI available at: http://localhost:5000"
        echo "📊 Check status with: docker-compose logs -f"
    else
        echo "❌ Failed to start container"
        exit 1
    fi
else
    echo "❌ Build failed"
    exit 1
fi
