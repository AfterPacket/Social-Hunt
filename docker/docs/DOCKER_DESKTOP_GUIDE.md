# 🐳 Docker Desktop GUI Guide for Social-Hunt

This guide shows you how to run Social-Hunt using Docker Desktop's graphical interface.

---

## ⚡ Quickest Method: Use Our Startup Scripts!

**You don't need to use the command line at all!**

### Windows Users:
1. Open File Explorer
2. Navigate to: `C:\path\to\Social-Hunt\docker`
3. **Double-click `start.bat`**
4. A window will open and start everything automatically
5. Access at: http://localhost:8000

### That's it! 🎉

The script does everything for you:
- ✅ Checks if Docker is running
- ✅ Starts all containers
- ✅ Shows you the access URL
- ✅ Provides helpful commands

---

## 🖥️ Using Docker Desktop GUI

Docker Desktop's GUI doesn't have a direct "Compose Up" button, but here are your options:

### Method 1: Using Docker Desktop's Built-in Terminal

1. **Open Docker Desktop**
   - Look for the Docker whale icon in your system tray (bottom-right corner)
   - Click it and select "Dashboard"

2. **Open the Terminal in Docker Desktop**
   - Look at the top menu bar
   - Some versions have a terminal icon (🔲 or ⌨️)
   - Or click the three dots (⋮) menu
   - Select "Terminal" or "CLI"

3. **Run the commands**:
   ```bash
   cd /c/path/to/Social-Hunt/docker
   docker compose up -d
   ```

### Method 2: Using Windows PowerShell/Terminal from Docker Desktop

1. **Open Docker Desktop Dashboard**
   
2. **Click on "Images" in the left sidebar**
   - You should see `afterpacket/social-hunt` listed
   - This confirms your image is available

3. **Open Windows PowerShell**:
   - Press `Win + X`
   - Select "Windows PowerShell" or "Terminal"
   
4. **Navigate and start**:
   ```powershell
   cd C:\path\to\Social-Hunt\docker
   docker compose up -d
   ```

### Method 3: Right-Click in File Explorer (Easiest!)

1. **Open File Explorer**
   - Navigate to: `C:\path\to\Social-Hunt\docker`

2. **Open PowerShell Here**:
   - Hold `Shift` key
   - Right-click in the folder (on empty space)
   - Select "Open PowerShell window here" or "Open in Terminal"

3. **Start Social-Hunt**:
   ```powershell
   docker compose up -d
   ```

4. **Access the application**:
   - Open browser: http://localhost:8000

---

## 📊 Monitoring Containers in Docker Desktop GUI

Once your containers are running, you can manage them through Docker Desktop:

### Viewing Running Containers

1. **Open Docker Desktop Dashboard**

2. **Click "Containers" in the left sidebar**
   - You'll see: `social-hunt` (running)
   - Status should show: ▶️ Running

3. **Container Actions Available**:
   - **▶️ Start** - Start the container
   - **⏸️ Stop** - Stop the container
   - **🔄 Restart** - Restart the container
   - **🗑️ Delete** - Remove the container
   - **📋 Logs** - View container logs
   - **⚙️ Inspect** - View container details

### Viewing Logs

1. In Docker Desktop, click on the **`social-hunt`** container

2. You'll see:
   - **Logs tab**: Real-time container output
   - **Inspect tab**: Container configuration
   - **Stats tab**: CPU, memory usage
   - **Files tab**: Container filesystem

3. **Check if it's working**:
   - Look for: `INFO: Uvicorn running on http://0.0.0.0:8000`
   - This means it's ready!

### Managing the Application

#### To Stop Social-Hunt:
1. Find `social-hunt` container in the list
2. Click the **⏸️ Stop** button
3. Or hover over it and click the three dots (⋮) → Stop

#### To Restart Social-Hunt:
1. Find `social-hunt` container
2. Click the **🔄 Restart** button

#### To View Real-Time Logs:
1. Click on the `social-hunt` container name
2. The Logs tab will show live output
3. Look for any errors or status messages

---

## 🎯 Docker Desktop Shortcuts

### Opening Specific Container Logs:
1. Docker Desktop Dashboard
2. Click "Containers" (left sidebar)
3. Click on the **`social-hunt`** container name
4. Logs appear automatically

### Quick Actions Menu:
- Hover over any container in the list
- Click the three dots (⋮) on the right
- Available actions:
  - Open in Browser (if configured)
  - Stop
  - Restart
  - Remove
  - View Logs
  - Open in Terminal

### Opening Container Terminal:
1. Find your container in the "Containers" list
2. Click the three dots (⋮)
3. Select "Open in Terminal" or "CLI"
4. You get a shell inside the container!

---

## 🔍 Checking if Social-Hunt is Running

### Visual Indicators in Docker Desktop:

1. **Container Status**:
   - ✅ Green dot = Running
   - ⭕ Gray dot = Stopped
   - 🔄 Blue spinning = Starting

2. **Port Information**:
   - Under the container name, you'll see: `8000:8000`
   - This means: Host port 8000 → Container port 8000

3. **Click the Port Number**:
   - Some versions of Docker Desktop let you click the port
   - It opens http://localhost:8000 in your browser automatically!

---

## 🚀 Starting Fresh

### If You Need to Rebuild Everything:

#### Using PowerShell:
```powershell
cd C:\path\to\Social-Hunt\docker
docker compose down
docker compose pull
docker compose up -d
```

#### Using Docker Desktop GUI:
1. **Stop and Remove Containers**:
   - Containers → Find `social-hunt`
   - Click three dots (⋮) → Remove
   - Check "Remove associated volumes" if starting fresh

2. **Pull Latest Image**:
   - Images → Find `afterpacket/social-hunt`
   - Click three dots (⋮) → Pull
   - Wait for download to complete

3. **Start Again**:
   - Use `start.bat` or PowerShell commands above

---

## 🛠️ Troubleshooting

### Container Won't Start

1. **Check Docker Desktop Status**:
   - Look at system tray icon
   - Should show "Docker Desktop is running"
   - If not, click and select "Start Docker Desktop"

2. **Check Error Messages**:
   - Containers → Click `social-hunt`
   - Read the logs for error messages
   - Common issues:
     - Port 8000 already in use
     - Missing volumes
     - Configuration errors

3. **Port Conflict**:
   - If port 8000 is busy:
   - Edit `docker-compose.yml`
   - Change `8000:8000` to `8080:8000`
   - Access at http://localhost:8080 instead

### Can't Access http://localhost:8000

1. **Check Container Status**:
   - Is it showing green/running in Docker Desktop?

2. **Check Port Binding**:
   - Click on container
   - Look for "8000:8000" in the details

3. **Try Alternative URLs**:
   - ❌ NOT: http://0.0.0.0:8000
   - ✅ TRY: http://localhost:8000
   - ✅ TRY: http://127.0.0.1:8000

4. **Check Logs for Errors**:
   - Container → Logs tab
   - Look for: `INFO: Uvicorn running on http://0.0.0.0:8000`

### Docker Desktop Not Responding

1. **Restart Docker Desktop**:
   - System tray → Right-click Docker icon
   - Select "Quit Docker Desktop"
   - Wait 10 seconds
   - Start Docker Desktop again

2. **Check Resources**:
   - Docker Desktop → Settings → Resources
   - Ensure enough CPU/Memory allocated
   - Recommended: 4GB RAM minimum

---

## 📖 Quick Reference Card

### Start Social-Hunt:
**Easiest**: Double-click `start.bat`  
**GUI**: Containers → social-hunt → Start  
**CLI**: `docker compose up -d`

### Stop Social-Hunt:
**GUI**: Containers → social-hunt → Stop  
**CLI**: `docker compose down`

### View Logs:
**GUI**: Containers → Click `social-hunt` → Logs  
**CLI**: `docker compose logs -f social-hunt`

### Restart Social-Hunt:
**GUI**: Containers → social-hunt → Restart  
**CLI**: `docker compose restart`

### Access Application:
**URL**: http://localhost:8000

### Admin Token Location:
**File 1**: `docker-compose.yml` (environment variable)  
**File 2**: `data/settings.json` (fallback)  
**Default**: `your_secure_token_here` or `ChangeME`

---

## 💡 Pro Tips

### Tip 1: Pin Docker Desktop for Easy Access
- Right-click Docker Desktop in taskbar
- Select "Pin to taskbar"
- Quick access anytime!

### Tip 2: Enable Auto-Start
- Docker Desktop → Settings → General
- ✅ Check "Start Docker Desktop when you log in"
- Containers with `restart: unless-stopped` will auto-start

### Tip 3: Bookmark the Application
- Once running, bookmark http://localhost:8000
- Easy access without Docker Desktop

### Tip 4: Use the Startup Script
- Create a desktop shortcut to `start.bat`
- Double-click anytime to start Social-Hunt
- No need to remember commands!

---

## 🎓 Understanding Docker Desktop Interface

### Left Sidebar Icons:

- 🏠 **Dashboard**: Overview of everything
- 📦 **Containers**: Running/stopped containers
- 🖼️ **Images**: Downloaded Docker images
- 📚 **Volumes**: Persistent data storage
- 🌐 **Dev Environments**: Development setups (newer feature)
- ⚙️ **Settings**: Docker configuration

### Top Bar:

- 🔍 **Search**: Find containers/images quickly
- 🔔 **Notifications**: Updates and alerts
- ⚙️ **Settings Gear**: Configuration menu
- 👤 **Account**: Docker Hub login

---

## ❓ FAQ

**Q: Do I need to use the command line?**  
A: No! Just double-click `start.bat` in the docker folder.

**Q: How do I know if it's running?**  
A: Open Docker Desktop → Containers → Look for `social-hunt` with a green dot.

**Q: Can I use Docker Desktop instead of commands?**  
A: Yes for monitoring, but starting requires either the startup script or a terminal command.

**Q: Where's the "compose up" button in Docker Desktop?**  
A: Docker Desktop doesn't have a direct compose button. Use the startup scripts or terminal.

**Q: It says "Can't reach this page"?**  
A: Don't use `http://0.0.0.0:8000` - use `http://localhost:8000` instead.

---

## 🆘 Still Need Help?

1. **Check the Logs**:
   - Docker Desktop → Containers → social-hunt → Logs
   - Look for error messages

2. **Try the Universal Startup Script**:
   - Just double-click `start.bat`
   - It handles everything automatically

3. **Review Other Documentation**:
   - `README_DOCKER.md` - Docker details and configuration
   - `STARTUP_SCRIPTS.md` - All startup methods and auto-start
   - `IOPAINT_GUIDE.md` - AI workers (IOPaint + DeepMosaic)
   - `../README.md` - Main project README

4. **Check GitHub Issues**:
   - https://github.com/AfterPacket/Social-Hunt/issues

---

**Remember: The easiest way is to just double-click `start.bat` in the docker folder! 🚀**