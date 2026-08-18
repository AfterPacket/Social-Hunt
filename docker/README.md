# 🐳 Social-Hunt Docker Setup

Welcome! This folder contains everything you need to run Social-Hunt in Docker.

---

## ⚡ Quick Start (3 Steps)

### 1. Make Sure Docker is Running
- Open Docker Desktop (Windows/macOS)
- Or start Docker service (Linux): `sudo systemctl start docker`

### 2. Start Social-Hunt
**Windows**: Double-click `start.bat`  
**Linux/macOS**: Double-click `start.sh` or run `./start.sh`  
**Any OS**: Run `python start.py`

### 3. Access the Application
Open your browser: **http://localhost:8000**

That's it! 🎉

---

## 📁 Folder Structure

```
docker/
├── start.bat                   # ← Windows launcher (just double-click!)
├── start.sh                    # ← Linux/macOS launcher
├── start.py                    # ← Universal Python script (works on all OS)
│
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                  # Docker image build instructions
├── nginx.conf                  # Nginx reverse proxy config (optional, for the `nginx`/`ssl` profiles)
├── setup_ssl.py                # SSL certificate setup script
│
├── docs/                       # 📚 All documentation
│   ├── IOPAINT_GUIDE.md       # AI workers (IOPaint + DeepMosaic) setup guide
│   ├── DOCKER_DESKTOP_GUIDE.md # Docker Desktop GUI usage guide
│   ├── README_DOCKER.md       # Detailed Docker docs (env vars, volumes, troubleshooting)
│   └── STARTUP_SCRIPTS.md     # Auto-startup configuration (systemd/cron/task scheduler)
│
├── scripts/                    # 🔧 Advanced/alternative scripts
│   ├── start-social-hunt.bat  # Windows-specific script
│   └── start-social-hunt.sh   # Linux-specific script
│
├── apache/                     # Apache reverse proxy configs
└── ssl/                        # SSL certificates and configs
```

---

## 🎯 What Do I Use?

### For Most Users (Easiest):
- **Windows**: `start.bat` (just double-click)
- **Linux/macOS**: `start.sh` (just double-click or `./start.sh`)
- **Any OS with Python**: `python start.py`

### For Advanced Users:
- **Manual Control**: `docker compose up -d`
- **OS-Specific Scripts**: See `scripts/` folder
- **Custom Configurations**: Edit `docker-compose.yml`

---

## 📚 Documentation

### Getting Started
- **Quick Start**: Read on below (the "Quick Start (3 Steps)" section)
- **Docker Desktop GUI**: See `docs/DOCKER_DESKTOP_GUIDE.md`
- **Detailed Setup**: See `docs/README_DOCKER.md`

### Special Features
- **AI Workers (IOPaint + DeepMosaic)**: See `docs/IOPAINT_GUIDE.md`
- **Automatic Startup**: See `docs/STARTUP_SCRIPTS.md`

### For Developers
- **All Documentation**: Browse the `docs/` folder

---

## 🚀 Common Tasks

### Start Social-Hunt
```bash
# Easy way (all OS)
python start.py

# Or direct docker compose
docker compose up -d
```

### Start with AI workers (IOPaint + DeepMosaic)
```bash
docker compose --profile ai up -d --build
```

This enables both IOPaint (port 8080) and DeepMosaic (port 8081). The main
Social-Hunt container stays on secure Pillow 12 (no torch) and reaches the
workers over the internal docker network. See `docs/IOPAINT_GUIDE.md`.

### Stop Everything
```bash
docker compose down
```

### View Logs
```bash
docker compose logs -f social-hunt
```

### Check Status
```bash
docker compose ps
```

### Update to Latest Version
```bash
docker compose pull
docker compose up -d
```

---

## 🔑 Configuration

### Admin Token
The admin token can be set in two places:

1. **docker-compose.yml** (environment variable):
   ```yaml
   - admin_token=your_secure_token_here
   ```

2. **data/settings.json** (fallback):
   ```json
   {
     "admin_token": "ChangeME"
   }
   ```

⚠️ **IMPORTANT**: Change the default token before production use!

### Ports
- **Social-Hunt**: http://localhost:8000
- **IOPaint**: http://localhost:8080 (when `--profile ai` is enabled)
- **DeepMosaic**: http://localhost:8081/status (when `--profile ai` is enabled)

To change ports, edit `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"  # Change first number only
```

---

## 🐛 Troubleshooting

### Can't Access http://localhost:8000?
- ❌ Don't use: `http://0.0.0.0:8000`
- ✅ Use: `http://localhost:8000` or `http://127.0.0.1:8000`

### Container Won't Start?
```bash
# Check logs for errors
docker compose logs

# Restart Docker Desktop (Windows/macOS)
# Or: sudo systemctl restart docker (Linux)
```

### Port Already in Use?
Edit `docker-compose.yml` and change the port mapping:
```yaml
ports:
  - "8080:8000"  # Use 8080 instead of 8000
```

### Need More Help?
- See `docs/DOCKER_DESKTOP_GUIDE.md` for GUI help
- See `docs/README_DOCKER.md` for detailed setup
- Review logs: `docker compose logs`

---

## 🌟 Features

- **One-Command Start**: Just run a script or double-click!
- **Cross-Platform**: Works on Windows, Linux, and macOS
- **Auto-Restart**: Containers restart automatically if they crash
- **Data Persistence**: Settings and results are saved between restarts
- **SSL Support**: Built-in HTTPS configuration available
- **Reverse Proxy**: Optional Nginx/Apache integration
- **AI Workers**: Optional IOPaint (interactive inpainting) and DeepMosaic (automated mosaic removal) via `--profile ai`

---

## 📦 Docker Hub

Pre-built image available:
- **Repository**: https://hub.docker.com/r/afterpacket/social-hunt
- **Pull Command**: `docker pull afterpacket/social-hunt:latest`

The `docker-compose.yml` already uses this image, so you don't need to build anything!

---

## 🆘 Need Help?

1. **Read the Quick Start**: the "Quick Start (3 Steps)" section above
2. **Check Documentation**: Browse the `docs/` folder
3. **View Logs**: `docker compose logs`
4. **GitHub Issues**: https://github.com/AfterPacket/Social-Hunt/issues

---

## ✨ What's New?

- ✅ Universal startup scripts for all platforms
- ✅ Organized folder structure (docs/, scripts/)
- ✅ Comprehensive documentation
- ✅ Docker Hub integration
- ✅ IOPaint + DeepMosaic AI workers (isolated via `--profile ai`)
- ✅ Easy one-click/one-command startup

---

**Happy Hunting! 🎯**

For detailed information, explore the `docs/` folder or run the startup scripts to get started immediately.