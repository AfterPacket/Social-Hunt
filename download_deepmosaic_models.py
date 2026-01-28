# download_deepmosaic_models.py
import requests
import os
from pathlib import Path

def download_file(url, destination):
    """Download a file from URL to destination"""
    print(f"Downloading {url} to {destination}")
    
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    with open(destination, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    print(f"Downloaded {destination}")

def main():
    # Create directories
    base_dir = Path("DeepMosaics/pretrained_models")
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "mosaic").mkdir(exist_ok=True)
    (base_dir / "style").mkdir(exist_ok=True)
    
    for model_path, url in models.items():
        dest = base_dir / model_path
        if not dest.exists():
            try:
                download_file(url, dest)
            except Exception as e:
                print(f"Failed to download {model_path}: {e}")
                print(f"Please manually download from: {url}")
        else:
            print(f"Model already exists: {dest}")

if __name__ == "__main__":
    main()