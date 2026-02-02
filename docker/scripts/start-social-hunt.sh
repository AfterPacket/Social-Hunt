#!/bin/bash
# Social-Hunt Linux/macOS Startup Script
# This script starts the Social-Hunt Docker containers automatically

set -e

echo "Starting Social-Hunt..."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running!"
    echo "Please start Docker and try again."
    echo ""
    echo "On Linux: sudo systemctl start docker"
    echo "On macOS: Open Docker Desktop"
    exit 1
fi

echo "Docker is running. Starting Social-Hunt containers..."
echo ""

# Start the containers
if docker compose up -d; then
    echo ""
    echo "========================================"
    echo "Social-Hunt started successfully!"
    echo "Access the application at:"
    echo "  http://localhost:8000"
    echo "========================================"
    echo ""
    echo "To view logs: docker compose logs -f social-hunt"
    echo "To stop: docker compose down"
    echo ""
    exit 0
else
    echo ""
    echo "ERROR: Failed to start Social-Hunt containers."
    echo "Please check the error messages above."
    echo ""
    exit 1
fi
