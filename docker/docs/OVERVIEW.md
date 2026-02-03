# Social-Hunt Overview

Social-Hunt is an advanced OSINT (Open Source Intelligence) framework designed for comprehensive social media investigation and analysis. It provides powerful tools for username discovery, breach exposure lookups, and avatar-based face matching across multiple platforms.

## Key Features

### Multi-Platform Username Discovery
- Scan for username presence across 500+ platforms using YAML-based provider configurations
- Real-time status indicators for each platform during scans
- Concurrent processing for fast results

### Breach Intelligence
- Integration with Have I Been Pwned (HIBP) for data breach lookups
- BreachVIP integration for comprehensive breach exposure analysis

### Advanced Face Matching
- Profile avatar face matching using state-of-the-art face recognition algorithms
- Image hashing for similarity comparisons
- Optional AI-powered face restoration/demasking capabilities

### Reverse Image OSINT
- Multiple search engine integration (Google Lens, Bing, Yandex, etc.)
- Public URL generation for sharing reverse image search results

### Tor/Onion Site Support
- SOCKS proxy support for dark web investigations
- Split-tunneling ensures regular sites use direct connections while .onion sites route through Tor

### Plugin System
- Extensible architecture with YAML provider packs
- Optional Python plugins for custom functionality
- Hot-reload capability for development
- Web-based plugin uploader for easy management

## Architecture

Social-Hunt follows a modern, efficient architecture:

- **Backend**: FastAPI with asynchronous httpx scanning engine for high performance
- **Frontend**: Lightweight static HTML/CSS/JS dashboard (no heavy frameworks)
- **Core Engine**: Asynchronous concurrency with per-provider rules and status heuristics
- **Data Storage**: JSON-based settings and job storage for simplicity and portability

## Deployment Options

### Docker (Recommended)
Pre-built Docker images and comprehensive docker-compose configuration make deployment straightforward:

```bash
cd Social-Hunt/docker
docker-compose up -d
```

### Manual Installation
Direct installation on host systems with Python virtual environments for development or specialized deployments.

## Security & Privacy

- Admin token authentication for dashboard access
- Encrypted secure notes with AES-256-GCM encryption
- Demo mode for safe demonstrations that censors sensitive data
- Responsible disclosure practices with canary warrant templates

## AI-Powered Capabilities

### Face Restoration/Demasking
Multiple options for AI-powered image enhancement:
- Replicate API integration for managed SaaS solution
- IOPaint WebUI for interactive inpainting
- DeepMosaic for automated mosaic removal
- Custom/self-hosted solutions via configurable endpoints

## Configuration Flexibility

Extensive environment variable support allows fine-tuning of all aspects:
- Port binding and host configuration
- Custom paths for data, plugins, and settings
- Proxy configuration for Tor support
- Plugin security controls and web upload permissions

## Reverse Proxy Support

Built-in support for both Nginx and Apache reverse proxies with detailed setup guides for production deployments with SSL termination.

## Legal Compliance

Social-Hunt emphasizes responsible use:
- Designed for lawful, authorized investigations only
- Users are responsible for complying with platform terms and local laws
- Ethical OSINT practices encouraged

This overview provides a comprehensive introduction to Social-Hunt's capabilities. For detailed usage instructions, please refer to the full documentation in README.md and the various setup guides.