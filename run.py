import os
import sys

import uvicorn


def main():
    """
    Entry point for starting the Social-Hunt server.
    Configurable via environment variables:
    - SOCIAL_HUNT_HOST: Bind address (default: 0.0.0.0)
    - SOCIAL_HUNT_PORT: Port to listen on (default: 8000)
    - SOCIAL_HUNT_RELOAD: Enable auto-reload for development (default: 0)
    """
    host = os.getenv("SOCIAL_HUNT_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("SOCIAL_HUNT_PORT", "8000"))
    except ValueError:
        port = 8000

    reload = os.getenv("SOCIAL_HUNT_RELOAD", "0") == "1"

    print("=" * 50)
    try:
        print("      🕵️‍♂️ Social-Hunt OSINT Framework")
    except UnicodeEncodeError:
        # Console may use cp1252 or another non-UTF-8 code page on Windows.
        print("      Social-Hunt OSINT Framework")
    print("=" * 50)
    print(f"[*] Starting server on {host}:{port}")
    print(f"[*] Dashboard: http://{'localhost' if host == '0.0.0.0' else host}:{port}")
    print("[*] Press Ctrl+C to stop.")
    print("-" * 50)

    try:
        uvicorn.run(
            "api.main:app", host=host, port=port, reload=reload, log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")
    except Exception as e:
        print(f"[!] Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
