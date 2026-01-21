# 🕵️‍♂️ Social-Hunt 
### **Advanced Web + CLI OSINT Username Discovery**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-05998b)

**Social-Hunt** is a lightweight, high-performance OSINT engine designed to find usernames across hundreds of platforms. Unlike basic scrapers, it prioritizes **metadata depth** (followers, avatars, bios) and **transparency** clearly distinguishing between a missing profile and a bot-wall.

---

## 🚀 Key Features

* **Dual Interface:** Seamlessly switch between a modern **FastAPI Web UI** and a powerful **CLI**.
* **Rich Metadata:** Extracts more than just "Exists"—gets `display_name`, `avatar_url`, `bio`, and `follower_counts`.
* **Smart Statuses:** No more false negatives. Results are categorized as:
    * `FOUND` | `NOT_FOUND` | `UNKNOWN` | `BLOCKED` (Anti-bot detected) | `ERROR`
* **Hybrid Provider System:**
    * **YAML:** Quick-add sites via regex patterns.
    * **Python Plugins:** Custom logic for complex APIs (GitHub, Reddit) to bypass simple limitations.
* **Rate-Limit Aware:** Integrated per-host pacing and concurrency management.
* **Advanced Addons:**
    * **Face Matcher:** Dual-mode avatar comparison using:
        * Facial recognition for custom avatars with faces
        * Perceptual image hashing for default/generic avatars
    * **HIBP Integration:** Check breach exposure via Have I Been Pwned API
    * **Network Safety:** URL validation and content-type checking

---

## 📂 Project Structure

```txt
.
├── social_hunt/            # Core Engine
│   ├── providers/          # Python Plugins (High-fidelity data)
│   ├── addons/             # Extensible addon modules
│   ├── engine.py           # Async scanning logic
│   ├── registry.py         # Plugin & YAML loader
│   └── rate_limit.py       # Pacing & Concurrency control
├── api/                    # FastAPI Server logic
├── web/                    # Frontend (HTML/JS/CSS)
├── providers.yaml          # Simple pattern-based definitions
├── addons.yaml             # Addon configurations
└── requirements.txt        # Dependencies
