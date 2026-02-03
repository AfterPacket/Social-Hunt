# Social-Hunt Docker Setup

This directory contains all the necessary Docker configuration files to run the Social-Hunt application in containerized environments.

## Overview

Social-Hunt is a sophisticated social media monitoring and analysis platform that enables users to track, analyze, and manage social media activities across various platforms. This Docker setup provides an easy and consistent way to deploy Social-Hunt regardless of the underlying operating system.

## Features

- **Containerized Deployment**: Run Social-Hunt in isolated containers for better security and resource management
- **Multi-Service Architecture**: Includes the main application, optional reverse proxies (Nginx/Apache), and supporting services
- **Persistent Data Storage**: Configuration, job results, and plugins are stored in Docker volumes for data persistence
- **SSL Support**: Built-in support for HTTPS with Let's Encrypt or custom certificates
- **Plugin Architecture**: Extend functionality through custom plugins that can be managed via the web interface
- **Reverse Proxy Options**: Choose between Nginx or Apache as your reverse proxy

## Quick Start

1. Ensure Docker and Docker Compose are installed
2. Navigate to this directory (`cd docker` from the project root)
3. Run `docker compose up -d` to start the basic Social-Hunt service
4. Access the application at http://localhost:8000

## Services Included

- **social-hunt**: The main Social-Hunt application service
- **nginx-proxy**: Optional Nginx reverse proxy (use with `--profile nginx`)
- **apache-proxy**: Optional Apache reverse proxy (use with `--profile apache`)
- **nginx-ssl**: Nginx with SSL support (use with `--profile ssl`)
- **certbot**: Let's Encrypt certificate helper (use with `--profile certbot`)
- **iopaint**: Optional AI inpainting service (use with `--profile iopaint`)

## Deployment Options

### Basic Deployment
```bash
docker compose up -d
```

### With Nginx Reverse Proxy
```bash
docker compose --profile proxy --profile nginx up -d
```

### With Apache Reverse Proxy
```bash
docker compose --profile proxy --profile apache up -d
```

### With SSL (Nginx + Let's Encrypt)
```bash
python setup_ssl.py
docker compose --profile certbot run --rm --service-ports certbot
docker compose --profile ssl up -d
```


## Environment Variables



The following environment variables can be configured in docker-compose.yml:



- `admin_token`: Security token for dashboard access (preferred method)

- `SOCIAL_HUNT_PLUGIN_TOKEN`: Security token for dashboard access (alternative method)
- `SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD`: Enable/disable plugin uploads via UI (1 or 0)

- `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP`: Allow setting token via UI if not configured (1 or 0)

### Setting the Admin Token

There are two ways to set the admin token:

1. **Environment Variable (Recommended)**: Set the `admin_token` environment variable in docker-compose.yml:
   ```yaml
   environment:
     - admin_token=YourSecureTokenHere
   ```

2. **Settings File**: Update the `data/settings.json` file with your token:
   ```json
   {
     "admin_token": "YourSecureTokenHere"
   }
   ```

The environment variable takes precedence over the settings file.


## Volume Mounts

Data persistence is achieved through Docker volume mounts:

- `../data:/app/data`: Stores settings, job results, and search history
- `../plugins:/app/plugins`: Custom YAML and Python plugins
- `../web/temp_uploads:/app/web/temp_uploads`: Temporary uploads for reverse image search

## Building Your Own Image

To build the Social-Hunt Docker image locally:

```bash
docker build -t social-hunt:latest -f Dockerfile ..
```

## Using Pre-built Images

The docker-compose.yml file can be configured to use pre-built images from Docker Hub instead of building locally:

```yaml
social-hunt:
  image: afterpacket/social-hunt:latest
  # build:
  #   context: ..
  #   dockerfile: docker/Dockerfile
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: If port 8000 is already in use, modify the port mapping in docker-compose.yml
2. **Permission errors**: Ensure Docker has access to the project directory
3. **Build failures**: Make sure all dependencies are properly installed

### Checking Logs

To view application logs:
```bash
docker compose logs social-hunt
```

### Updating the Application

To update to the latest version:
```bash
docker compose down
docker pull afterpacket/social-hunt:latest
docker compose up -d
```

## Docker Hub Repository

The official Social-Hunt Docker image is available on Docker Hub:
https://hub.docker.com/r/afterpacket/social-hunt

Pull the image directly:
```bash
docker pull afterpacket/social-hunt:latest
```
