#!/bin/bash

# Remote Management Script for Civiphrases Docker Web UI
# Provides easy commands to manage the deployed application

# Configuration
DOCKER_HOST_IP="192.168.73.124"
DOCKER_HOST_USER="root"
REMOTE_APP_DIR="/opt/civiphrases-webui"
CONTAINER_NAME="civiphrases-webui"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to run commands on remote host
run_remote() {
    ssh ${DOCKER_HOST_USER}@${DOCKER_HOST_IP} "$1"
}

show_usage() {
    echo -e "${BLUE}Civiphrases Remote Management${NC}"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status     - Show container status"
    echo "  logs       - Show container logs (follow mode)"
    echo "  restart    - Restart the container"
    echo "  stop       - Stop the container"
    echo "  start      - Start the container"
    echo "  rebuild    - Rebuild and restart container"
    echo "  shell      - Open shell in container"
    echo "  files      - List output files"
    echo "  cleanup    - Clean up old containers and images"
    echo "  health     - Check application health"
    echo ""
}

case "$1" in
    status)
        echo -e "${YELLOW}📊 Container Status:${NC}"
        run_remote "docker ps -a | grep ${CONTAINER_NAME} || echo 'Container not found'"
        echo ""
        echo -e "${YELLOW}🐳 Docker System Info:${NC}"
        run_remote "docker system df"
        ;;
    
    logs)
        echo -e "${YELLOW}📝 Following logs for ${CONTAINER_NAME}...${NC}"
        echo -e "${BLUE}Press Ctrl+C to exit${NC}"
        run_remote "docker logs -f ${CONTAINER_NAME}"
        ;;
    
    restart)
        echo -e "${YELLOW}🔄 Restarting container...${NC}"
        run_remote "cd ${REMOTE_APP_DIR} && docker-compose restart"
        echo -e "${GREEN}✅ Container restarted${NC}"
        ;;
    
    stop)
        echo -e "${YELLOW}🛑 Stopping container...${NC}"
        run_remote "cd ${REMOTE_APP_DIR} && docker-compose stop"
        echo -e "${GREEN}✅ Container stopped${NC}"
        ;;
    
    start)
        echo -e "${YELLOW}▶️  Starting container...${NC}"
        run_remote "cd ${REMOTE_APP_DIR} && docker-compose start"
        echo -e "${GREEN}✅ Container started${NC}"
        ;;
    
    rebuild)
        echo -e "${YELLOW}🏗️  Rebuilding and restarting...${NC}"
        run_remote "cd ${REMOTE_APP_DIR} && docker-compose down"
        run_remote "cd ${REMOTE_APP_DIR} && docker build -t civiphrases-webui:latest ."
        run_remote "cd ${REMOTE_APP_DIR} && docker-compose up -d"
        echo -e "${GREEN}✅ Container rebuilt and restarted${NC}"
        ;;
    
    shell)
        echo -e "${YELLOW}🐚 Opening shell in container...${NC}"
        run_remote "docker exec -it ${CONTAINER_NAME} /bin/bash"
        ;;
    
    files)
        echo -e "${YELLOW}📁 Output files:${NC}"
        run_remote "ls -la /mnt/user/appdata/civiphrases/ 2>/dev/null || echo 'Output directory not found'"
        echo ""
        echo -e "${YELLOW}📄 Wildcard files:${NC}"
        run_remote "ls -la /mnt/user/appdata/civiphrases/wildcards/ 2>/dev/null || echo 'Wildcards directory not found'"
        ;;
    
    cleanup)
        echo -e "${YELLOW}🧹 Cleaning up old containers and images...${NC}"
        run_remote "docker container prune -f"
        run_remote "docker image prune -f"
        echo -e "${GREEN}✅ Cleanup completed${NC}"
        ;;
    
    health)
        echo -e "${YELLOW}🏥 Checking application health...${NC}"
        if run_remote "curl -f http://localhost:5000/health"; then
            echo -e "${GREEN}✅ Application is healthy${NC}"
        else
            echo -e "${RED}❌ Application health check failed${NC}"
        fi
        ;;
    
    *)
        show_usage
        ;;
esac
