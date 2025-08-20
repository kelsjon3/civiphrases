#!/bin/bash

# Local Build and Test Script for Civiphrases Docker Web UI
# Tests the Docker build locally before remote deployment

set -e  # Exit on any error

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Cleanup function
cleanup() {
    if [ -d "./civiphrases" ] || [ -f "./pyproject.toml" ]; then
        echo -e "${YELLOW}ℹ️  Cleaning up temporary files...${NC}"
        rm -rf ./civiphrases ./pyproject.toml 2>/dev/null || true
    fi
}

# Set trap to cleanup on exit
trap cleanup EXIT

echo -e "${BLUE}🏗️  Local Build Test for Civiphrases Docker Web UI${NC}"
echo ""

# Copy civiphrases source code
echo -e "${YELLOW}ℹ️  Preparing civiphrases source code...${NC}"
if [ -d "../civiphrases" ]; then
    cp -r ../civiphrases ./
    cp ../pyproject.toml ./
    echo -e "${GREEN}✅ Civiphrases source copied${NC}"
else
    echo -e "${RED}❌ Could not find civiphrases source directory at ../civiphrases${NC}"
    echo -e "${RED}Make sure you're running this from the civiphrases-docker-webui directory${NC}"
    exit 1
fi

# Build Docker image
echo -e "${YELLOW}ℹ️  Building Docker image locally...${NC}"
docker build -t civiphrases-webui:test .
echo -e "${GREEN}✅ Docker image built successfully${NC}"

# Test run (optional)
echo ""
echo -e "${BLUE}📋 Build completed successfully!${NC}"
echo ""
echo -e "${YELLOW}💡 To test the container locally:${NC}"
echo -e "   docker run -p 5000:5000 -v \$(pwd)/output:/output civiphrases-webui:test"
echo ""
echo -e "${YELLOW}💡 To deploy to remote host:${NC}"
echo -e "   ./deploy_to_docker.sh"
echo ""
echo -e "${GREEN}🎉 Ready for deployment!${NC}"
