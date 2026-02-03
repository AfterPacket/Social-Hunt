# 🎨 IOPaint Setup Guide for Social-Hunt

IOPaint is an AI-powered image inpainting tool that can be used alongside Social-Hunt for advanced image editing and restoration.

---

## 📋 What is IOPaint?

IOPaint is a free and open-source image inpainting tool powered by state-of-the-art AI models. It allows you to:
- Remove unwanted objects from images
- Restore damaged or masked areas
- Edit and enhance photos
- Perform AI-powered image manipulation

---

## 🚀 Starting IOPaint

### Method 1: Start with Social-Hunt (Recommended)

Start both Social-Hunt and IOPaint together:

```bash
cd C:\Git\Social-Hunt\docker
docker compose --profile iopaint up -d
```

### Method 2: Start IOPaint Separately

If Social-Hunt is already running:

```bash
cd C:\Git\Social-Hunt\docker
docker compose --profile iopaint up -d
```

### Method 3: Using PowerShell/Terminal

```powershell
cd C:\Git\Social-Hunt\docker
docker compose --profile iopaint up -d
```

---

## ⏱️ First-Time Setup (Important!)

**The first time you start IOPaint, it will take 5-15 minutes to set up.**

### What's Happening During First Start:

1. **Downloading Dependencies** (2-3 minutes)
   - PyTorch (~2GB)
   - Transformers
   - Diffusers
   - Other AI libraries

2. **Installing Packages** (3-5 minutes)
   - Compiling native extensions
   - Setting up CUDA support (if available)
   - Configuring models

3. **Starting the Server** (1 minute)
   - Loading IOPaint application
   - Initializing web server
   - Ready to use!

### How to Check Progress:

```bash
docker compose logs -f iopaint
```

Look for this message when ready:
```
INFO:     Uvicorn running on http://0.0.0.0:8080
```

---

## 🌐 Accessing IOPaint

Once installation is complete:

### Direct Access:
- **URL**: http://localhost:8080
- **Browser**: Open any modern web browser

### From Social-Hunt Dashboard:
1. Open Social-Hunt: http://localhost:8000
2. Navigate to: **Demasking** → **IOPaint Inpainting**
3. The dashboard may provide controls to:
   - Start/stop IOPaint server
   - Open IOPaint interface
   - Check server status

---

## 🔍 Checking IOPaint Status

### Using Docker Desktop GUI:
1. Open Docker Desktop
2. Click **"Containers"** in the left sidebar
3. Look for: `docker-iopaint-1`
4. Status should show: ✅ Running (green dot)

### Using Command Line:

```bash
# Check if IOPaint is running
docker compose ps

# You should see:
# NAME               STATUS       PORTS
# docker-iopaint-1   Up X minutes 0.0.0.0:8080->8080/tcp
```

### View Real-Time Logs:

```bash
# Watch logs as they appear
docker compose logs -f iopaint

# View last 50 lines
docker compose logs --tail 50 iopaint
```

---

## 🛠️ Managing IOPaint

### Stop IOPaint:

```bash
docker compose stop iopaint
```

Or in Docker Desktop:
- Containers → docker-iopaint-1 → Stop button

### Restart IOPaint:

```bash
docker compose restart iopaint
```

Or in Docker Desktop:
- Containers → docker-iopaint-1 → Restart button

### Stop Everything (Social-Hunt + IOPaint):

```bash
docker compose --profile iopaint down
```

---

## 🎯 Usage Tips

### First-Time Users:

1. **Be Patient**: First startup takes 5-15 minutes
2. **Watch the Logs**: Use `docker compose logs -f iopaint` to see progress
3. **Check Container Status**: Make sure it shows "Up" in Docker Desktop
4. **Wait for Ready Message**: Look for "Uvicorn running on http://0.0.0.0:8080"

### Regular Use:

After the first setup, IOPaint starts much faster:
- Subsequent starts: 30-60 seconds
- Dependencies already installed
- Models already downloaded

### Performance Notes:

- **CPU Only**: This Docker setup uses CPU processing (no GPU)
- **Slower Processing**: AI operations will be slower than GPU versions
- **Memory Usage**: IOPaint can use 2-4GB of RAM
- **For Better Performance**: Consider using a GPU-enabled version on compatible hardware

---

## 🐛 Troubleshooting

### Issue: "Can't reach this page" at http://localhost:8080

**Solution:**
1. Check if IOPaint is still installing:
   ```bash
   docker compose logs iopaint
   ```
2. Wait for the "Uvicorn running" message
3. Refresh your browser after it's ready

### Issue: Container Keeps Restarting

**Solution:**
1. Check the logs for errors:
   ```bash
   docker compose logs iopaint
   ```
2. Common causes:
   - Insufficient memory (need at least 4GB available)
   - Port 8080 already in use
   - Dependency installation failed

### Issue: Port 8080 Already in Use

**Solution:**
Edit `docker-compose.yml` and change the port:

```yaml
iopaint:
  ports:
    - "8081:8080"  # Change to 8081 or any free port
```

Then access at: http://localhost:8081

### Issue: Installation Takes Too Long

**This is Normal!** First-time setup can take:
- Fast connection: 5-10 minutes
- Slow connection: 10-20 minutes
- Downloads ~2-3GB of packages

**To verify it's working:**
```bash
docker compose logs -f iopaint
```

You should see:
- "Downloading..." messages
- "Installing..." messages
- Progress bars and package names

### Issue: Container Shows "Exited"

**Solution:**
1. Check what went wrong:
   ```bash
   docker compose logs iopaint
   ```
2. Try restarting:
   ```bash
   docker compose restart iopaint
   ```
3. If it fails again, remove and recreate:
   ```bash
   docker compose down
   docker compose --profile iopaint up -d
   ```

---

## 📊 Port Configuration

### Default Configuration:

- **Social-Hunt**: http://localhost:8000
- **IOPaint**: http://localhost:8080

### If You Need Different Ports:

Edit `docker-compose.yml`:

```yaml
services:
  social-hunt:
    ports:
      - "8000:8000"  # Keep as is or change first number
  
  iopaint:
    ports:
      - "8080:8080"  # Keep as is or change first number
```

Remember: Change only the **first** number (host port), not the second (container port).

---

## 🔄 Automatic Startup

### To Start IOPaint Automatically with Social-Hunt:

The `restart: unless-stopped` policy in docker-compose.yml means:
- ✅ Restarts if it crashes
- ✅ Starts when Docker Desktop starts (if it was running before)
- ❌ Won't start on first boot

### For Automatic Startup on System Boot:

1. **Enable Docker Desktop Auto-Start**:
   - Docker Desktop → Settings → General
   - ✅ Check "Start Docker Desktop when you log in"

2. **Start IOPaint Once**:
   ```bash
   docker compose --profile iopaint up -d
   ```

3. **Leave It Running**:
   - Don't manually stop it
   - It will auto-start with Docker Desktop on reboot

---

## 💡 Integration with Social-Hunt

### Using IOPaint from Social-Hunt Dashboard:

1. **Navigate to**: Social-Hunt → Demasking → IOPaint Inpainting
2. **Features Available**:
   - Start/stop IOPaint server
   - Open IOPaint interface in new tab
   - Check server status
   - View logs

### Direct Access:

You can also use IOPaint directly at http://localhost:8080 without going through Social-Hunt.

---

## 📚 Additional Resources

### IOPaint Documentation:
- Official Site: https://www.iopaint.com/
- GitHub: https://github.com/Sanster/IOPaint

### Social-Hunt Documentation:
- Main README: `../README.md`
- Docker Guide: `README_DOCKER.md`
- Startup Scripts: `STARTUP_SCRIPTS.md`

---

## ⚡ Quick Reference

### Start IOPaint:
```bash
docker compose --profile iopaint up -d
```

### Stop IOPaint:
```bash
docker compose stop iopaint
```

### View Logs:
```bash
docker compose logs -f iopaint
```

### Check Status:
```bash
docker compose ps
```

### Access IOPaint:
- **URL**: http://localhost:8080

### First Setup Time:
- **5-15 minutes** (normal)
- Watch logs to track progress

---

## ❓ FAQ

**Q: How long does first-time setup take?**  
A: 5-15 minutes, depending on your internet speed and computer performance.

**Q: Why is it so slow?**  
A: This Docker setup uses CPU only (no GPU acceleration). For faster performance, use GPU-enabled versions.

**Q: Can I use it without Social-Hunt?**  
A: Yes! Access it directly at http://localhost:8080

**Q: Does it work offline after first setup?**  
A: Yes, once dependencies are installed, IOPaint can work offline.

**Q: Is it safe to stop it?**  
A: Yes, you can stop and start IOPaint anytime without losing data.

**Q: Will it slow down Social-Hunt?**  
A: Minimal impact when idle. Processing images will use CPU/memory resources.

---

## 🆘 Still Having Issues?

1. **Check the logs**: `docker compose logs iopaint`
2. **Restart Docker Desktop**: Sometimes helps with stuck installations
3. **Remove and recreate**: 
   ```bash
   docker compose down
   docker compose --profile iopaint up -d
   ```
4. **Check system resources**: Ensure you have at least 4GB RAM available
5. **Review other docs**: Check `DOCKER_DESKTOP_GUIDE.md` for general Docker help

---

**Remember: First-time setup takes time, but subsequent starts are fast! Be patient during the initial installation. 🚀**