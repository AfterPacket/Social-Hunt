# BreachVIP Proxy Configuration

This document explains how to configure proxy settings for BreachVIP searches to bypass Cloudflare blocks and other network restrictions.

## Overview

BreachVIP (breach.vip) sometimes blocks requests from certain IP addresses, particularly those from data centers or VPS providers. The proxy configuration feature allows you to:

- Route BreachVIP requests through proxy servers
- Use different connection strategies (regular first, proxy first, or proxy only)
- Configure authentication for proxy servers
- Enable residential IP routing when available

## Configuration Methods

### Method 1: Web UI Configuration (Recommended)

1. Navigate to the **Settings** page in the Social-Hunt dashboard
2. Scroll to the **BreachVIP Proxy Configuration** section
3. Configure your proxy settings:

#### Basic Settings

- **Enable Proxy for BreachVIP**: Toggle to enable/disable proxy usage
- **Proxy URL**: Enter your proxy server URL (e.g., `http://proxy-server:8080`, `socks5://127.0.0.1:1080`)
- **Auth (optional)**: Enter proxy authentication in format `username:password`

#### Advanced Settings

- **Strategy**: Choose your connection strategy:
  - **Try Regular First, Proxy as Failover**: Attempts direct connection first, falls back to proxy if blocked
  - **Try Proxy First, Regular as Failover**: Attempts proxy connection first, falls back to direct if proxy fails
  - **Use Proxy Only**: Only uses proxy connection, never attempts direct connection

- **Use Residential IP**: Enable if your proxy provider supports residential IP routing

4. Click **Save Proxy Settings** to apply changes
5. Use **Test Connection** to verify proxy functionality

### Method 2: Environment Variables

Set these environment variables before starting Social-Hunt:

```bash
# Basic proxy configuration
export BREACHVIP_PROXY_ENABLED="true"
export BREACHVIP_PROXY_URL="http://proxy-server:8080"
export BREACHVIP_PROXY_AUTH="username:password"
export BREACHVIP_PROXY_STRATEGY="regular_first"  # or "proxy_first", "proxy_only"
export BREACHVIP_USE_RESIDENTIAL_IP="true"
```

> **Note**: UI settings override environment variables when both are configured.

## Proxy Types and Examples

### HTTP Proxy
```
Proxy URL: http://proxy.example.com:8080
Auth: myuser:mypass
```

### HTTPS Proxy
```
Proxy URL: https://secure-proxy.example.com:8080
Auth: myuser:mypass
```

### SOCKS5 Proxy
```
Proxy URL: socks5://127.0.0.1:1080
Auth: (leave blank for most SOCKS5 proxies)
```

### SOCKS5 with Authentication
```
Proxy URL: socks5://proxy.example.com:1080
Auth: username:password
```

## Connection Strategies

### Regular First (Default)
- **Best for**: General use when blocks are occasional
- **Behavior**: Tries direct connection first, uses proxy only if blocked (HTTP 403/Cloudflare block)
- **Advantages**: Faster when not blocked, conserves proxy bandwidth

### Proxy First
- **Best for**: Regions with frequent blocking
- **Behavior**: Always tries proxy first, falls back to direct if proxy fails
- **Advantages**: More reliable in restricted environments

### Proxy Only
- **Best for**: Maximum privacy or when direct connections never work
- **Behavior**: Only uses proxy, never attempts direct connection
- **Advantages**: Consistent routing, maximum anonymity

## Common Proxy Providers

### Residential Proxies
- **Bright Data** (formerly Luminati)
- **Smartproxy**
- **Proxy-Seller**

### Datacenter Proxies
- **ProxyMesh**
- **Storm Proxies**
- **MyPrivateProxy**

### Self-Hosted
- **Squid Proxy** on VPS
- **Tor** (SOCKS5 via `127.0.0.1:9050`)
- **SSH Tunnels**

## Troubleshooting

### Common Issues

#### 1. Proxy Authentication Failed
**Error**: Connection failed with 407 Proxy Authentication Required
**Solution**: 
- Verify username/password in the Auth field
- Format should be `username:password`
- Check with proxy provider for correct credentials

#### 2. Proxy Connection Timeout
**Error**: Connection timeout or refused
**Solution**:
- Verify proxy URL format and port
- Check if proxy server is online
- Test with different proxy endpoints

#### 3. Still Getting Cloudflare Blocks
**Error**: HTTP 403 or Cloudflare challenge page
**Solution**:
- Switch to "Proxy Only" strategy
- Try different proxy endpoints
- Use residential proxies instead of datacenter proxies
- Enable "Use Residential IP" if supported

#### 4. Proxy Working But Slow
**Issue**: Searches taking too long
**Solution**:
- Use "Regular First" strategy for better performance
- Choose proxy servers geographically closer
- Upgrade to faster proxy service

### Debug Information

Social-Hunt logs proxy activity in the console. Look for these messages:

```
[DEBUG] BreachVIP proxy config: enabled=true, strategy=regular_first, url=true
[DEBUG] BreachVIP attempt 1: using regular
[DEBUG] BreachVIP attempt 1: using proxy via http://proxy:8080
[SUCCESS] BreachVIP proxy succeeded
```

### Testing Configuration

1. Save proxy settings in the UI
2. Click "Test Connection" - this will attempt to connect through your proxy
3. Check server logs for connection details
4. Perform a test BreachVIP search to verify functionality

## Security Considerations

### Proxy Authentication
- Proxy credentials are stored securely server-side
- They are never displayed in the UI after saving
- Use strong, unique passwords for proxy authentication

### Traffic Routing
- All BreachVIP traffic will route through configured proxies
- Consider the jurisdiction and logging policies of your proxy provider
- Residential proxies generally provide better anonymity

### Network Security
- Ensure proxy connections use HTTPS when possible
- Verify proxy provider's security practices
- Consider using VPN + proxy for additional security layers

## Performance Optimization

### Strategy Selection
- **High-speed networks**: Use "Regular First"
- **Blocked regions**: Use "Proxy First" or "Proxy Only"
- **Privacy-focused**: Use "Proxy Only"

### Proxy Selection
- Choose proxies geographically close to breach.vip servers
- Residential proxies are slower but less likely to be blocked
- Datacenter proxies are faster but more likely to be blocked

### Connection Pooling
- Social-Hunt reuses connections when possible
- Proxy connections are established per search session
- Failed connections trigger automatic retry with different strategies

## Configuration Examples

### Basic Residential Proxy
```json
{
  "breachvip": {
    "proxy_enabled": true,
    "proxy_url": "http://residential-proxy.example.com:8080",
    "proxy_auth": "user123:pass456",
    "proxy_strategy": "proxy_first",
    "use_residential_ip": true
  }
}
```

### Tor SOCKS5 Proxy
```json
{
  "breachvip": {
    "proxy_enabled": true,
    "proxy_url": "socks5://127.0.0.1:9050",
    "proxy_auth": "",
    "proxy_strategy": "proxy_only",
    "use_residential_ip": false
  }
}
```

### Failover Configuration
```json
{
  "breachvip": {
    "proxy_enabled": true,
    "proxy_url": "http://backup-proxy.example.com:3128",
    "proxy_auth": "backup_user:backup_pass",
    "proxy_strategy": "regular_first",
    "use_residential_ip": false
  }
}
```

## API Integration

The proxy settings are part of the general settings API:

### Get Current Settings
```bash
curl -H "X-Plugin-Token: YOUR_TOKEN" \
  http://localhost:8000/sh-api/settings
```

### Update Proxy Settings
```bash
curl -X PUT -H "X-Plugin-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": {
      "breachvip.proxy_enabled": true,
      "breachvip.proxy_url": "http://proxy:8080",
      "breachvip.proxy_strategy": "regular_first"
    }
  }' \
  http://localhost:8000/sh-api/settings
```

## Support

If you encounter issues with proxy configuration:

1. Check the server logs for detailed error messages
2. Verify proxy credentials and endpoints with your provider
3. Test with different proxy strategies
4. Consider switching proxy providers if blocks persist

For additional support, refer to the main Social-Hunt documentation or open an issue on the project repository.