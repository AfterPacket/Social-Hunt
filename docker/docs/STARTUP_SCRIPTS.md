# Social-Hunt Startup Scripts

This directory contains startup scripts to automatically launch Social-Hunt Docker containers on different operating systems.

## Available Scripts

### Universal Scripts (Recommended)

- **`start.py`** - Universal Python script that auto-detects OS and starts Docker
- **`start.bat`** - Windows wrapper for start.py (just double-click)
- **`start.sh`** - Linux/macOS wrapper for start.py

### OS-Specific Scripts

- **`start-social-hunt.bat`** - Windows-only startup script
- **`start-social-hunt.sh`** - Linux/macOS-only startup script

## Prerequisites

1. Docker Desktop (Windows/macOS) or Docker Engine (Linux) must be installed
2. Python 3.6+ (for universal scripts) - optional, falls back to direct docker compose
3. The `docker-compose.yml` file must be in the same directory as the scripts

**Note**: The universal scripts can automatically detect your OS and even attempt to start Docker if it's not running!

## Quick Start

### Universal Method (Recommended - Works on All OS)

#### Option 1: Using Python Script Directly
```bash
python3 start.py
# or
python start.py
```

#### Option 2: Using OS Wrappers (Just Double-Click!)

**Windows**: Double-click `start.bat`

**Linux/macOS**: Double-click `start.sh` or run in terminal:
```bash
./start.sh
```

**Features of Universal Scripts:**
- ✅ Auto-detects your operating system
- ✅ Checks if Docker is running
- ✅ Can attempt to start Docker automatically if not running
- ✅ Waits for Docker to be ready
- ✅ Provides clear status messages and helpful commands

### OS-Specific Method (Alternative)

#### Windows

1. Double-click `start-social-hunt.bat`
2. Or run from Command Prompt/PowerShell:
   ```cmd
   cd C:\Git\Social-Hunt\docker
   start-social-hunt.bat
   ```

#### Linux/macOS

1. Open Terminal and navigate to the docker directory:
   ```bash
   cd /path/to/Social-Hunt/docker
   ./start-social-hunt.sh
   ```

2. Or make it executable and run:
   ```bash
   chmod +x start-social-hunt.sh
   ./start-social-hunt.sh
   ```

## Automatic Startup on System Boot

### Windows

#### Method 1: Startup Folder (Recommended)

1. Press `Win + R` to open the Run dialog
2. Type `shell:startup` and press Enter
3. Create a shortcut to `start-social-hunt.bat` in this folder
4. Right-click the shortcut → Properties
5. Set "Start in" to: `C:\Git\Social-Hunt\docker`

**Note**: Ensure Docker Desktop is set to start automatically:
- Open Docker Desktop Settings
- Check "Start Docker Desktop when you log in"

#### Method 2: Task Scheduler (Advanced)

1. Open Task Scheduler (`taskschd.msc`)
2. Click "Create Basic Task"
3. Name: "Social-Hunt Startup"
4. Trigger: "When I log on"
5. Action: "Start a program"
6. Program: `C:\Git\Social-Hunt\docker\start-social-hunt.bat`
7. Start in: `C:\Git\Social-Hunt\docker`
8. Check "Run with highest privileges" (if needed)

### Linux

#### Method 1: systemd Service (Recommended)

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/social-hunt.service
   ```

2. Add the following content (adjust paths as needed):
   ```ini
   [Unit]
   Description=Social-Hunt Docker Container
   Requires=docker.service
   After=docker.service

   [Service]
   Type=oneshot
   RemainAfterExit=yes
   WorkingDirectory=/path/to/Social-Hunt/docker
   ExecStart=/usr/bin/docker compose up -d
   ExecStop=/usr/bin/docker compose down
   User=your-username

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable social-hunt.service
   sudo systemctl start social-hunt.service
   ```

4. Check status:
   ```bash
   sudo systemctl status social-hunt.service
   ```

#### Method 2: Cron Job

1. Edit your crontab:
   ```bash
   crontab -e
   ```

2. Add this line:
   ```bash
   @reboot sleep 30 && /path/to/Social-Hunt/docker/start-social-hunt.sh
   ```

#### Method 3: rc.local (Older Systems)

1. Edit `/etc/rc.local`:
   ```bash
   sudo nano /etc/rc.local
   ```

2. Add before `exit 0`:
   ```bash
   /path/to/Social-Hunt/docker/start-social-hunt.sh &
   ```

3. Make it executable:
   ```bash
   sudo chmod +x /etc/rc.local
   ```

### macOS

#### Method 1: Launch Agent (Recommended)

1. Create a launch agent plist file:
   ```bash
   nano ~/Library/LaunchAgents/com.socialhunt.startup.plist
   ```

2. Add the following content (adjust paths):
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.socialhunt.startup</string>
       <key>ProgramArguments</key>
       <array>
           <string>/path/to/Social-Hunt/docker/start-social-hunt.sh</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>WorkingDirectory</key>
       <string>/path/to/Social-Hunt/docker</string>
       <key>StandardOutPath</key>
       <string>/tmp/social-hunt.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/social-hunt.err</string>
   </dict>
   </plist>
   ```

3. Load the launch agent:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.socialhunt.startup.plist
   ```

4. To unload:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.socialhunt.startup.plist
   ```

**Note**: Ensure Docker Desktop is set to start automatically:
- Open Docker Desktop Preferences
- Check "Start Docker Desktop when you log in"

#### Method 2: Login Items

1. Open System Preferences → Users & Groups
2. Click your username
3. Go to "Login Items" tab
4. Click the "+" button
5. Navigate to and select `start-social-hunt.sh`

## Troubleshooting

### Docker Not Running

If you get "Docker is not running" error:

**Windows/macOS:**
- Open Docker Desktop manually
- Ensure "Start Docker Desktop when you log in" is enabled in settings

**Linux:**
```bash
sudo systemctl start docker
sudo systemctl enable docker  # Enable on boot
```

### Permission Denied (Linux/macOS)

Make the script executable:
```bash
chmod +x start-social-hunt.sh
```

### Port Already in Use

If port 8000 is already in use:
1. Stop the conflicting service
2. Or change the port in `docker-compose.yml`:
   ```yaml
   ports:
     - "8080:8000"  # Use 8080 instead
   ```

### Container Doesn't Start Automatically

Check the restart policy in `docker-compose.yml`:
```yaml
restart: unless-stopped
```

View container status:
```bash
docker compose ps
```

View logs:
```bash
docker compose logs social-hunt
```

## Manual Commands

### Start Social-Hunt
```bash
docker compose up -d
```

### Stop Social-Hunt
```bash
docker compose down
```

### View Logs
```bash
docker compose logs -f social-hunt
```

### Restart Social-Hunt
```bash
docker compose restart
```

### Check Status
```bash
docker compose ps
```

### Update to Latest Image
```bash
docker compose pull
docker compose up -d
```

## Accessing Social-Hunt

Once started, access the application at:
- **http://localhost:8000**
- **http://127.0.0.1:8000**

Default admin token location:
- Environment variable: `admin_token` in `docker-compose.yml`
- Settings file: `data/settings.json`

## Uninstalling Automatic Startup

### Windows (Startup Folder)
1. Press `Win + R`, type `shell:startup`
2. Delete the `start-social-hunt.bat` shortcut

### Windows (Task Scheduler)
1. Open Task Scheduler
2. Find "Social-Hunt Startup" task
3. Right-click → Delete

### Linux (systemd)
```bash
sudo systemctl stop social-hunt.service
sudo systemctl disable social-hunt.service
sudo rm /etc/systemd/system/social-hunt.service
sudo systemctl daemon-reload
```

### Linux (cron)
```bash
crontab -e
# Remove the @reboot line
```

### macOS (Launch Agent)
```bash
launchctl unload ~/Library/LaunchAgents/com.socialhunt.startup.plist
rm ~/Library/LaunchAgents/com.socialhunt.startup.plist
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Social-Hunt GitHub](https://github.com/AfterPacket/Social-Hunt)
- [Docker Hub Image](https://hub.docker.com/r/afterpacket/social-hunt)

## Support

For issues or questions:
- Check the main README.md
- Review Docker logs: `docker compose logs`
- Open an issue on GitHub

---

**Note**: These scripts require Docker to be installed and running. Make sure Docker Desktop (Windows/macOS) or Docker Engine (Linux) is properly configured before using these startup scripts.