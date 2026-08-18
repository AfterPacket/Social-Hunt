# Apache deployment (reverse proxy) + systemd

These steps assume Ubuntu/Debian, Apache2, and that you want:
- Apache on :80/:443
- Social-Hunt app on localhost:8000
- Apache reverse-proxies to the app

## 1) Install system packages

```bash
sudo apt update
sudo apt -y install python3 python3-venv python3-pip apache2
```

## 2) Put the app somewhere stable

Example:

```bash
sudo mkdir -p /opt/social-hunt
sudo chown -R $USER:$USER /opt/social-hunt
cd /opt/social-hunt
# copy the project here (or git clone)
```

Create venv + install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) Create a systemd service

Create `/etc/systemd/system/social-hunt.service`:

```ini
[Unit]
Description=Social-Hunt (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/social-hunt
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/social-hunt/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

# Hardening (optional but recommended)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/social-hunt

[Install]
WantedBy=multi-user.target
```

Enable + start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now social-hunt
sudo systemctl status social-hunt --no-pager
```

## 4) Enable Apache proxy modules

```bash
sudo a2enmod proxy proxy_http headers rewrite
sudo systemctl reload apache2
```

## 5) Create an Apache site (reverse proxy)

Create `/etc/apache2/sites-available/social-hunt.conf`:

```apache
<VirtualHost *:80>
  ServerName osint.example.com

  # Basic security headers
  Header always set X-Content-Type-Options "nosniff"
  Header always set X-Frame-Options "DENY"
  Header always set Referrer-Policy "no-referrer"

  # Reverse proxy to the app
  ProxyPreserveHost On
  ProxyPass / http://127.0.0.1:8000/
  ProxyPassReverse / http://127.0.0.1:8000/

  # (Optional) access log
  ErrorLog ${APACHE_LOG_DIR}/social-hunt_error.log
  CustomLog ${APACHE_LOG_DIR}/social-hunt_access.log combined
</VirtualHost>
```

Enable the site:

```bash
sudo a2ensite social-hunt
sudo a2dissite 000-default
sudo systemctl reload apache2
```

## 6) Add TLS (recommended)

If you have a domain pointed at the VPS:

```bash
sudo apt -y install certbot python3-certbot-apache
sudo certbot --apache -d osint.example.com
```

## 6b) Exposing the AI workers (IOPaint, DeepMosaic)

The AI workers run in isolated environments (their own venvs or containers) and
the Social-Hunt app reaches them over loopback (`IOPAINT_URL`,
`DEEPMOSAIC_URL`). They do **not** need to be proxied through Apache for the app
to use them — the dashboard's "Open IOPaint WebUI" button opens IOPaint directly
on port `8080`.

> **Do not proxy IOPaint under `/iopaint/`.** IOPaint is a single-page app that
> assumes it is served at site root. Its internal `/assets/` and `/api/` calls
> are absolute, so a subpath proxy breaks them. Use a separate subdomain (or the
> raw port `8080`) instead. See `FIXES.md` for the full reasoning.

If you want IOPaint's web UI on the same TLS domain without a port number, use a
separate subdomain VirtualHost:

```apache
<VirtualHost *:443>
  ServerName iopaint.example.com

  SSLEngine on
  SSLCertificateFile /etc/ssl/your_cert/ssl.combined
  SSLCertificateKeyFile /etc/ssl/your_cert/ssl.key

  SSLProtocol -all +TLSv1.2 +TLSv1.3
  SSLCipherSuite HIGH:!aNULL:!MD5:!3DES
  SSLHonorCipherOrder On

  ProxyPreserveHost On
  RequestHeader set X-Forwarded-Proto "https"

  LimitRequestBody 0

  ProxyPass        / http://127.0.0.1:8080/
  ProxyPassReverse / http://127.0.0.1:8080/
</VirtualHost>
```

DeepMosaic has no web UI — leave it on `127.0.0.1:8081` and set
`DEEPMOSAIC_URL=http://127.0.0.1:8081` on the Social-Hunt process. It does not
need an Apache vhost.

On the main Social-Hunt vhost, do **not** add a global `/api/` proxy rule — it
collides with IOPaint's internal `/api/` namespace. Social-Hunt uses `/sh-api/`
exclusively.

## 7) (Recommended) Put auth in front of it (so it can't be abused)

### Option A: Basic Auth in Apache (fast)

Enable auth module:

```bash
sudo a2enmod auth_basic
sudo systemctl reload apache2
```

Create a password file:

```bash
sudo apt -y install apache2-utils
sudo htpasswd -c /etc/apache2/.socialhunt.htpasswd youruser
```

Then add inside your `<VirtualHost>`:

```apache
  <Location />
    AuthType Basic
    AuthName "Social-Hunt"
    AuthUserFile /etc/apache2/.socialhunt.htpasswd
    Require valid-user
  </Location>
```

Reload:

```bash
sudo systemctl reload apache2
```

### Option B: Restrict by IP

```apache
  <Location />
    Require ip 1.2.3.4 5.6.7.8
  </Location>
```

## 8) Optional: Apache-side request limits

These don't replace app-side limits, but they help keep the proxy stable:

```apache
# Timeouts for slow clients
RequestReadTimeout header=20-40,MinRate=500 body=20,MinRate=500

# Limit request body size
LimitRequestBody 1048576
```

Enable module:

```bash
sudo a2enmod reqtimeout
sudo systemctl reload apache2
```

---

### Notes
- Some platforms will return bot-walls; the app reports `blocked` or `unknown` rather than guessing.
- If you want persistence across restarts and multiple workers, swap the in-memory job store for Redis.
