# Nginx reverse proxy setup

This guide shows how to run Social-Hunt behind Nginx and (optionally) expose the
AI workers (IOPaint, DeepMosaic) on the same host.

> **Do not proxy IOPaint under `/iopaint/`.** IOPaint is a single-page app that
> assumes it is served at site root. Its internal `/assets/` and `/api/` calls
> are absolute, so a subpath proxy breaks them. Expose IOPaint on its own port
> (`8080`) or a separate subdomain instead. See `FIXES.md` for the full reasoning.

## 1) Install Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

## 2) Example server block (HTTPS)

Use this when Social-Hunt is on `127.0.0.1:8000`. Social-Hunt's API is served
under `/sh-api`. The AI workers (IOPaint on `127.0.0.1:8080`, DeepMosaic on
`127.0.0.1:8081`) are reached by the app over loopback and do **not** need to be
proxied here — the dashboard opens IOPaint's web UI directly on port `8080`.

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

    # Allow large uploads (demasking, reverse image search)
    client_max_body_size 0;

    # Social-Hunt API (served under /sh-api). MUST come before the catch-all.
    location /sh-api/ {
        proxy_pass http://127.0.0.1:8000/sh-api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
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

    # Social-Hunt app + static assets
    location / {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 3) (Optional) Expose IOPaint on a separate subdomain

If you want IOPaint's web UI on the same domain (TLS) without a port number, use
a subdomain — **not** a subpath. Add a second server block:

```nginx
server {
    listen 443 ssl http2;
    server_name iopaint.example.com;

    ssl_certificate     /etc/ssl/your_cert/fullchain.pem;
    ssl_certificate_key /etc/ssl/your_cert/privkey.pem;

    client_max_body_size 0;

    location / {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # IOPaint uses websockets for live updates
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Then point the dashboard at it by setting `IOPAINT_URL=http://127.0.0.1:8080`
on the Social-Hunt process (loopback, not the public subdomain — the app talks
to the worker directly, the subdomain is only for the browser).

DeepMosaic has no web UI — leave it on `127.0.0.1:8081` and set
`DEEPMOSAIC_URL=http://127.0.0.1:8081`.

## 4) Enable site and reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Notes

- If you see 413 errors, increase `client_max_body_size`.
- If IOPaint returns 403, your WAF may be blocking `/api` POSTs.
- Do **not** add a global `/api/` proxy rule on the Social-Hunt vhost — it
  collides with IOPaint's internal `/api/` namespace. Social-Hunt uses `/sh-api/`.
- The `docker/nginx.conf` in this repo follows the same direct-port approach and
  documents the (not-recommended) `/iopaint/` subpath as a commented-out block.