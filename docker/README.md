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
├── START_HERE.md               # ← Quick start guide
│
├── docker-compose.yml          # Docker services configuration
├── Dockerfile                  # Docker image build instructions
├── nginx.conf                  # Nginx reverse proxy config
├── setup_ssl.py                # SSL certificate setup script
│
├── docs/                       # 📚 All documentation
│   ├── DEV_UPDATE.md          # Development team update
│   ├── DOCKER_DESKTOP_GUIDE.md # GUI usage guide
│   ├── IOPAINT_GUIDE.md       # IOPaint setup guide
│   ├── OVERVIEW.md            # Project overview
│   ├── README_DOCKER.md       # Detailed Docker docs
│   └── STARTUP_SCRIPTS.md     # Auto-startup configuration
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
- **Quick Start**: Read `START_HERE.md` (in this folder)
- **Docker Desktop GUI**: See `docs/DOCKER_DESKTOP_GUIDE.md`
- **Detailed Setup**: See `docs/README_DOCKER.md`

### Special Features
- **IOPaint (AI Image Editing)**: See `docs/IOPAINT_GUIDE.md`
- **Automatic Startup**: See `docs/STARTUP_SCRIPTS.md`
- **Project Overview**: See `docs/OVERVIEW.md`

### For Developers
- **Development Update**: See `docs/DEV_UPDATE.md`
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

### Start with IOPaint (AI Image Editor)
```bash
docker compose --profile iopaint up -d
```

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
- **IOPaint**: http://localhost:8080 (when enabled)

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
- Check `START_HERE.md` for quick troubleshooting
- See `docs/DOCKER_DESKTOP_GUIDE.md` for GUI help
- Review logs: `docker compose logs`

---

## 🌟 Features

- **One-Command Start**: Just run a script or double-click!
- **Cross-Platform**: Works on Windows, Linux, and macOS
- **Auto-Restart**: Containers restart automatically if they crash
- **Data Persistence**: Settings and results are saved between restarts
- **SSL Support**: Built-in HTTPS configuration available
- **Reverse Proxy**: Optional Nginx/Apache integration
- **IOPaint Integration**: Optional AI-powered image editing

---

## 📦 Docker Hub

Pre-built image available:
- **Repository**: https://hub.docker.com/r/afterpacket/social-hunt
- **Pull Command**: `docker pull afterpacket/social-hunt:latest`

The `docker-compose.yml` already uses this image, so you don't need to build anything!

---

## 🆘 Need Help?

1. **Read the Quick Start**: `START_HERE.md`
2. **Check Documentation**: Browse the `docs/` folder
3. **View Logs**: `docker compose logs`
4. **GitHub Issues**: https://github.com/AfterPacket/Social-Hunt/issues

---

## ✨ What's New?

- ✅ Universal startup scripts for all platforms
- ✅ Organized folder structure (docs/, scripts/)
- ✅ Comprehensive documentation
- ✅ Docker Hub integration
- ✅ IOPaint support for AI image editing
- ✅ Easy one-click/one-command startup

---

**Happy Hunting! 🎯**

For detailed information, explore the `docs/` folder or run the startup scripts to get started immediately.