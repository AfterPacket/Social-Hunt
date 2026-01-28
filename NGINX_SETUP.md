# Nginx reverse proxy setup

This guide shows how to run Social-Hunt behind Nginx and (optionally) expose
IOPaint at `/iopaint` on the same domain.

## 1) Install Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

## 2) Example server block (HTTPS + /iopaint)

Use this when Social-Hunt is on `127.0.0.1:8000` and IOPaint is on
`127.0.0.1:8080`. Social-Hunt’s API is served under `/sh-api`.

```nginx
server {
    listen 80;
    server_name osint.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name osint.example.com;

    ssl_certificate     /etc/ssl/your_cert/fullchain.pem;
    ssl_certificate_key /etc/ssl/your_cert/privkey.pem;

    # Allow large uploads (IOPaint)
    client_max_body_size 0;

    # IOPaint UI + assets + API + socket.io
    location /iopaint/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /assets/ {
        proxy_pass http://127.0.0.1:8080/assets/;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io/ {
        proxy_pass http://127.0.0.1:8080/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Social-Hunt API (moved to /sh-api)
    location /sh-api/ {
        proxy_pass http://127.0.0.1:8000/sh-api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Websocket endpoint
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Social-Hunt app
    location / {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 3) Enable site and reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Notes

- If you see 413 errors, increase `client_max_body_size`.
- If IOPaint returns 403, your WAF may be blocking `/api` POSTs.
- For the subdomain approach, point `iopaint.example.com` at 127.0.0.1:8080 and
  keep Social-Hunt on `osint.example.com`.
