#!/bin/bash

# Civiphrases Docker Deployment Script
# Deploys the civiphrases-docker-webui to a remote Docker host

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Cleanup function to remove temporary files
cleanup() {
    if [ -d "./civiphrases" ] || [ -f "./pyproject.toml" ]; then
        echo -e "${YELLOW}ℹ️  Cleaning up temporary files...${NC}"
        rm -rf ./civiphrases ./pyproject.toml 2>/dev/null || true
    fi
}

# Set trap to cleanup on exit (success or failure)
trap cleanup EXIT

# Function to print status
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Configuration
DOCKER_HOST_IP="192.168.73.124"
DOCKER_HOST_USER="root"  # Change this if you use a different user
REMOTE_APP_DIR="/opt/civiphrases-webui"
LOCAL_APP_DIR="$(pwd)"
CONTAINER_NAME="civiphrases-webui"
IMAGE_NAME="civiphrases-webui:latest"

echo -e "${BLUE}🚀 Starting deployment of Civiphrases Docker Web UI${NC}"
echo -e "${BLUE}📍 Target: ${DOCKER_HOST_USER}@${DOCKER_HOST_IP}${NC}"
echo ""

# Function to run commands on remote host
run_remote() {
    ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} "$1"
}

# Check if we can connect to the Docker host
print_info "Testing SSH connection to Docker host..."
if ! ssh -o ConnectTimeout=5 ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} "echo 'SSH connection successful'" > /dev/null 2>&1; then
    print_error "Cannot connect to Docker host at ${DOCKER_HOST_IP}"
    print_error "Please check:"
    print_error "  - IP address is correct"
    print_error "  - SSH key is properly configured"
    print_error "  - Host is reachable"
    exit 1
fi
print_status "SSH connection verified"

# Check if Docker is installed on remote host
print_info "Checking Docker installation on remote host..."
if ! run_remote "command -v docker > /dev/null 2>&1"; then
    print_error "Docker is not installed on the remote host"
    print_error "Please install Docker first"
    exit 1
fi
print_status "Docker found on remote host"

# Check if docker-compose is available
print_info "Checking for docker-compose..."
if run_remote "command -v docker-compose > /dev/null 2>&1 || docker compose version > /dev/null 2>&1"; then
    print_status "docker-compose available"
    # Determine which compose command to use
    if run_remote "docker compose version > /dev/null 2>&1"; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
else
    print_error "docker-compose not found on remote host"
    print_error "Please install docker-compose first"
    exit 1
fi

# Stop and remove existing container if it exists
print_info "Stopping existing container if running..."
run_remote "docker stop ${CONTAINER_NAME} 2>/dev/null || true"
run_remote "docker rm ${CONTAINER_NAME} 2>/dev/null || true"
print_status "Cleaned up existing container"

# Create remote directory
print_info "Creating remote application directory..."
run_remote "mkdir -p ${REMOTE_APP_DIR}"
print_status "Remote directory created: ${REMOTE_APP_DIR}"

# Copy civiphrases source code into webui directory first
print_info "Preparing civiphrases source code..."
if [ -d "../civiphrases" ]; then
    cp -r ../civiphrases ./
    cp ../pyproject.toml ./
    print_status "Civiphrases source copied to webui directory"
else
    print_error "Could not find civiphrases source directory at ../civiphrases"
    print_error "Make sure you're running this from the civiphrases-docker-webui directory"
    print_error "and that the civiphrases package exists in the parent directory"
    exit 1
fi

# Copy application files to remote host
print_info "Copying application files to remote host..."
# Use rsync for efficient transfer, excluding unnecessary files
rsync -avz --delete \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.log' \
    --exclude='node_modules' \
    --exclude='.pytest_cache' \
    --exclude='*.egg-info' \
    "${LOCAL_APP_DIR}/" "${DOCKER_HOST_USER}@${DOCKER_HOST_IP}:${REMOTE_APP_DIR}/"
print_status "Files copied successfully"

# Build Docker image on remote host
print_info "Building Docker image on remote host..."
run_remote "cd ${REMOTE_APP_DIR} && docker build -t ${IMAGE_NAME} ."
print_status "Docker image built successfully"

# Create output directory on host
print_info "Creating output directory structure..."
run_remote "mkdir -p /mnt/user/appdata/civiphrases/{wildcards,state,logs}"
run_remote "chmod 755 /mnt/user/appdata/civiphrases"
print_status "Output directories created"

# Deploy using docker-compose
print_info "Deploying container using docker-compose..."
run_remote "cd ${REMOTE_APP_DIR} && ${COMPOSE_CMD} up -d"
print_status "Container deployed successfully"

# Wait a moment for container to start
sleep 3

# Check if container is running
print_info "Verifying container status..."
if run_remote "docker ps | grep ${CONTAINER_NAME} > /dev/null"; then
    print_status "Container is running successfully"
else
    print_error "Container failed to start"
    print_info "Checking logs..."
    run_remote "docker logs ${CONTAINER_NAME}" || true
    exit 1
fi

# Test health endpoint
print_info "Testing application health..."
sleep 5  # Give the app time to fully start
if run_remote "curl -f http://localhost:5000/health > /dev/null 2>&1"; then
    print_status "Application health check passed"
else
    print_error "Health check failed - app may still be starting"
    print_info "You can check logs with: ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} 'docker logs ${CONTAINER_NAME}'"
fi

# Cleanup will happen automatically via trap

# Show final status
echo ""
echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo ""
echo -e "${BLUE}📋 Deployment Summary:${NC}"
echo -e "   🖥️  Docker Host: ${DOCKER_HOST_IP}"
echo -e "   🐳 Container: ${CONTAINER_NAME}"
echo -e "   🌐 Web UI: http://${DOCKER_HOST_IP}:5000"
echo -e "   📁 Output Path: /mnt/user/appdata/civiphrases/"
echo ""
echo -e "${YELLOW}💡 Useful Commands:${NC}"
echo -e "   View logs: ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} 'docker logs -f ${CONTAINER_NAME}'"
echo -e "   Stop app:  ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} 'cd ${REMOTE_APP_DIR} && ${COMPOSE_CMD} down'"
echo -e "   Restart:   ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} 'cd ${REMOTE_APP_DIR} && ${COMPOSE_CMD} restart'"
echo ""
echo -e "${GREEN}🎨 Ready to generate some wildcards! Visit http://${DOCKER_HOST_IP}:5000${NC}"
