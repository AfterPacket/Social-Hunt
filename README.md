# 🕵️‍♂️ Social-Hunt

**Social-Hunt** is a professional-grade OSINT (Open Source Intelligence) framework designed for investigators, security researchers, and enthusiasts. It provides a unified dashboard to perform cross-platform username searches, data breach exposure analysis, and advanced facial recognition-based avatar matching.

---

## 🚀 Key Features

### 🔍 Multi-Platform Username Search
*   **Fast Discovery:** Scans 50+ social media platforms, forums, and sites simultaneously.
*   **Extensible:** Uses a data-driven YAML provider system and supports custom Python plugins.
*   **Advanced Detection:** Uses success/error patterns and HTTP status codes to minimize false positives.

### 🛡️ Breach Intelligence
*   **HIBP Integration:** Seamlessly check Have I Been Pwned for account exposure across thousands of known leaks.
*   **Detailed Records:** Deep integration with providers like Breach.VIP to retrieve specific leaked data (passwords, salts, IPs) directly on the dashboard.
*   **Unified Reporting:** Consolidates breach data into a specialized, easy-to-read table.

### 👤 Advanced Face Matcher
*   **Dual-Mode Comparison:** 
    *   **Facial Recognition:** Compares custom avatars using high-accuracy facial landmarks.
    *   **Image Hashing:** Uses perceptual hashing (pHash) to identify default or generic avatars.
*   **Visual Evidence:** Provides match confidence scores to help verify identity across platforms.

### 🖼️ Reverse Image OSINT
*   **One-Click Search:** Perform reverse image searches via Google Lens, Bing, Yandex, and specialized engines like PimEyes or FaceCheck.ID.
*   **Image Hosting:** Securely handles temporary image uploads for analysis.

---

## 🛠️ Architecture

Social-Hunt is built with a modern, decoupled architecture:
*   **Backend:** High-performance Python API powered by **FastAPI** and **httpx** for asynchronous scanning.
*   **Frontend:** A clean, responsive dashboard built with vanilla JavaScript and CSS (no heavy frameworks required).
*   **Core Engine:** Asynchronous task runner with built-in rate limiting and concurrency control.

---

## 🚦 Getting Started

### Prerequisites
*   Python 3.9+
*   `pip` (Python package manager)

### Installation
1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-repo/Social-Hunt.git
    cd Social-Hunt
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the Server:**
    ```bash
    python run.py
    ```
4.  **Access the Dashboard:**
    Open `http://localhost:8000` in your web browser.

---

## ⚙️ Configuration

Social-Hunt stores its settings in `data/settings.json`. You can configure these directly through the **Settings** and **Token** tabs in the dashboard:

| Setting | Description |
| :--- | :--- |
| `hibp_api_key` | Your Have I Been Pwned API key (required for HIBP scans). |
| `admin_token` | A security token used to protect privileged operations (like plugin uploads). |
| `public_url` | The base URL of your instance (used for generating reverse image links). |

---

## 🧩 Plugins & Extensions

Social-Hunt is built for customization.
*   **YAML Providers:** Add new sites to search by dropping a `.yaml` file into `plugins/providers/`.
*   **Python Plugins:** Create complex scrapers or post-processing addons in `plugins/python/`.

See [PLUGINS.md](PLUGINS.md) for more details.

---

## 🤝 Contributor Credits

Social-Hunt is a community-driven project. Special thanks to:

*   **Main Developer:** [Your Name/GitHub Handle] – Original architecture and core engine.
*   **OSINT Specialists:** [Contributor Name] – Research and development of provider patterns.
*   **Security Researchers:** [Contributor Name] – Breach data integration and API security.
*   **UI/UX Designers:** [Contributor Name] – Dashboard layout and responsiveness.

---

## ⚖️ Legal Disclaimer

**Social-Hunt is for educational and ethical investigative purposes only.** 
The developers and contributors are not responsible for any misuse of this tool. Always ensure you have the legal right to perform searches and adhere to the Terms of Service of the platforms being scanned.

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.