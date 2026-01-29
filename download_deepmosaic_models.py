# download_deepmosaic_models.py
import os
import requests
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import re
import subprocess
import rarfile
import shutil

# Model URLs with their original filenames and target subdirectories
MODEL_URLS = [
    # MOSAIC models (go to mosaic/ subdirectory)
    ("mosaic/add_face.pth", "https://files.catbox.moe/6zj9ly.pth"),
    ("mosaic/add_youknow.pth", "https://files.catbox.moe/1xawn9.pth"),
    ("mosaic/clean_youknow_resnet_9blocks.pth", "https://files.catbox.moe/lvyj6g.pth"),
    ("mosaic/mosaic_position.pth", "https://files.catbox.moe/z40yji.pth"),
    ("mosaic/clean_youknow_video.pth", "https://files.catbox.moe/b4ntro.pth"),
    ("mosaic/edges2cat.pth", "https://files.catbox.moe/7z0q3m.pth"),
    
    # STYLE models (go to style/ subdirectory)
    ("style/style_apple2orange.pth", "https://files.catbox.moe/6ppy8s.pth"),
    ("style/style_cezanne.pth", "https://files.catbox.moe/pftq0p.pth"),
    ("style/style_monet.pth", "https://files.catbox.moe/3rszwv.pth"),
    ("style/style_orange2apple.pth", "https://files.catbox.moe/4uu8vh.pth"),
    ("style/style_summer2winter.pth", "https://files.catbox.moe/f7baan.pth"),
    ("style/style_ukiyoe.pth", "https://files.catbox.moe/qhgfs5.pth"),
    ("style/style_vangogh.pth", "https://files.catbox.moe/pohxvj.pth"),
    ("style/style_winter2summer.pth", "https://files.catbox.moe/irs3o8.pth"),
    
    # RAR file for mosaic models (will be extracted to mosaic/)
    ("clean_face_HD.pth.part1.rar", "https://files.catbox.moe/w5w75v.rar"),
    ("clean_face_HD.pth.part2.rar", "https://files.catbox.moe/yfl9h3.rar"),
    ("clean_face_HD.pth.part3.rar", "https://files.catbox.moe/cipo3s.rar"),
    ("clean_face_HD.pth.part4.rar", "https://files.catbox.moe/79aqe4.rar"),
]

# Target directory paths
SCRIPT_DIR = Path(__file__).parent.absolute()
DEEP_MOSAICS_DIR = SCRIPT_DIR / "DeepMosaics"
TARGET_BASE_DIR = DEEP_MOSAICS_DIR / "pretrained_models"
MOSAIC_DIR = TARGET_BASE_DIR / "mosaic"
STYLE_DIR = TARGET_BASE_DIR / "style"

def check_deepmosaics_exists():
    """Check if DeepMosaics directory exists."""
    print(f"Checking for DeepMosaics directory...")
    print(f"Script directory: {SCRIPT_DIR}")
    print(f"Expected DeepMosaics: {DEEP_MOSAICS_DIR.absolute()}")
    
    if not DEEP_MOSAICS_DIR.exists():
        print(f"\n❌ ERROR: DeepMosaics directory not found!")
        print(f"Expected location: {DEEP_MOSAICS_DIR.absolute()}")
        print(f"\nPlease ensure:")
        print(f"1. You're running this script from the same directory as DeepMosaics")
        print(f"2. The directory structure is: ./DeepMosaics/pretrained_models/")
        
        # Offer to create the directory
        response = input(f"\nCreate the directory structure? (y/n): ")
        if response.lower() == 'y':
            try:
                DEEP_MOSAICS_DIR.mkdir(parents=True, exist_ok=True)
                print(f"✅ Created directory: {DEEP_MOSAICS_DIR.absolute()}")
                return True
            except Exception as e:
                print(f"❌ Failed to create directory: {e}")
                return False
        else:
            return False
    
    print(f"✅ Found DeepMosaics directory: {DEEP_MOSAICS_DIR.absolute()}")
    return True

def setup_directories():
    """Create all necessary directories."""
    directories = [TARGET_BASE_DIR, MOSAIC_DIR, STYLE_DIR]
    
    for directory in directories:
        if not directory.exists():
            print(f"Creating directory: {directory.absolute()}")
            directory.mkdir(parents=True, exist_ok=True)
    
    print(f"\nDirectory structure:")
    print(f"  Base: {TARGET_BASE_DIR.absolute()}")
    print(f"  Mosaic models: {MOSAIC_DIR.absolute()}")
    print(f"  Style models: {STYLE_DIR.absolute()}")
    
    return TARGET_BASE_DIR, MOSAIC_DIR, STYLE_DIR

def check_existing_files_and_skip():
    """Check for existing files and skip downloading if they already exist."""
    print(f"\n📋 Checking for existing files...")
    
    files_to_download = []
    existing_files_count = 0
    
    for rel_path, url in MODEL_URLS:
        file_path = TARGET_BASE_DIR / rel_path
        
        # Check if file already exists
        if file_path.exists():
            file_size = file_path.stat().st_size
            if file_size > 1024:  # File exists and has reasonable size
                existing_files_count += 1
                size_mb = file_size / (1024*1024)
                print(f"  ✅ Already exists: {rel_path} ({size_mb:.1f} MB)")
                continue
        
        # File doesn't exist or is too small, add to download list
        files_to_download.append((rel_path, url))
    
    print(f"\n📊 Summary: {existing_files_count} files already exist, {len(files_to_download)} files to download")
    
    # Also check for extracted files
    extracted_pth_files = []
    for dir_path in [MOSAIC_DIR, STYLE_DIR]:
        if dir_path.exists():
            for pth_file in dir_path.glob("*.pth"):
                if pth_file.stat().st_size > 1024:
                    extracted_pth_files.append(pth_file)
    
    if extracted_pth_files:
        print(f"\n📁 Found {len(extracted_pth_files)} extracted .pth files in subdirectories:")
        for pth_file in extracted_pth_files[:10]:
            size_mb = pth_file.stat().st_size / (1024*1024)
            rel_path = pth_file.relative_to(TARGET_BASE_DIR)
            print(f"  ✅ {rel_path} ({size_mb:.1f} MB)")
        
        if len(extracted_pth_files) > 10:
            print(f"  ... and {len(extracted_pth_files) - 10} more")
    
    # Check if clean_face_HD.pth is already in mosaic directory
    clean_face_hd_path = MOSAIC_DIR / "clean_face_HD.pth"
    if clean_face_hd_path.exists() and clean_face_hd_path.stat().st_size > 1024:
        print(f"\n⚠  Note: clean_face_HD.pth already exists in mosaic directory")
        size_mb = clean_face_hd_path.stat().st_size / (1024*1024)
        print(f"    {clean_face_hd_path} ({size_mb:.1f} MB)")
        print("    RAR files may not need to be downloaded/extracted")
    
    return files_to_download

def download_file_thread(filename, url, dest_path, progress_dict):
    """Download a file in a thread with progress tracking."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    progress_dict[filename] = {'status': 'downloading', 'progress': 0, 'size': 0}
    
    try:
        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        progress_dict[filename] = {
                            'status': 'downloading', 
                            'progress': progress, 
                            'size': total_size,
                            'downloaded': downloaded
                        }
        
        progress_dict[filename] = {'status': 'completed', 'progress': 100, 'size': total_size}
        return True, filename, None
        
    except Exception as e:
        progress_dict[filename] = {'status': 'failed', 'error': str(e)}
        return False, filename, str(e)

def display_progress(progress_dict, total_files):
    """Display download progress for all files."""
    completed = sum(1 for p in progress_dict.values() if p.get('status') == 'completed')
    downloading = sum(1 for p in progress_dict.values() if p.get('status') == 'downloading')
    failed = sum(1 for p in progress_dict.values() if p.get('status') == 'failed')
    
    print(f"\n📊 Progress: {completed}/{total_files} completed | {downloading} downloading | {failed} failed")
    print("-" * 60)
    
    for filename, progress in progress_dict.items():
        status = progress.get('status', 'pending')
        if status == 'downloading':
            pct = progress.get('progress', 0)
            downloaded = progress.get('downloaded', 0)
            size = progress.get('size', 0)
            size_mb = size / (1024*1024) if size > 0 else 0
            downloaded_mb = downloaded / (1024*1024) if downloaded > 0 else 0
            bar_length = 30
            filled = int(bar_length * pct / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            # Extract just the filename for display
            display_name = Path(filename).name
            print(f"  {display_name[:30]:30} [{bar}] {pct:5.1f}% ({downloaded_mb:.1f}/{size_mb:.1f} MB)")
        elif status == 'completed':
            size_mb = progress.get('size', 0) / (1024*1024)
            display_name = Path(filename).name
            print(f"  {display_name[:30]:30} ✅ COMPLETED ({size_mb:.1f} MB)")
        elif status == 'failed':
            error = progress.get('error', 'Unknown error')
            display_name = Path(filename).name
            print(f"  {display_name[:30]:30} ❌ FAILED: {error[:40]}")
        else:
            display_name = Path(filename).name
            print(f"  {display_name[:30]:30} ⏳ PENDING")
    
    return completed

def download_all_files_concurrent(files_to_download, base_dir, max_workers=3):
    """Download all files concurrently with progress display."""
    if not files_to_download:
        print("No files to download - all files already exist.")
        return 0, []
    
    print(f"Starting concurrent download of {len(files_to_download)} files...")
    print(f"Files will be organized into mosaic/ and style/ subdirectories")
    
    progress_dict = {}
    futures = []
    
    # Start downloads in threads
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for rel_path, url in files_to_download:
            dest_path = base_dir / rel_path
            future = executor.submit(download_file_thread, rel_path, url, dest_path, progress_dict)
            futures.append(future)
        
        # Monitor progress while downloads are running
        while any(not f.done() for f in futures):
            completed = display_progress(progress_dict, len(files_to_download))
            if completed == len(files_to_download):
                break
            time.sleep(1)
        
        # Get results
        results = []
        for future in as_completed(futures):
            success, filename, error = future.result()
            results.append((success, filename, error))
    
    # Final progress display
    display_progress(progress_dict, len(files_to_download))
    
    # Count results
    successful = sum(1 for r in results if r[0])
    failed = sum(1 for r in results if not r[0])
    
    print(f"\n📋 Download Summary: {successful} successful, {failed} failed")
    
    # List failed downloads
    failed_files = []
    for success, filename, error in results:
        if not success:
            failed_files.append((filename, error))
    
    if failed_files:
        print("\n❌ Failed downloads:")
        for filename, error in failed_files:
            print(f"  - {filename}: {error}")
    
    return successful, failed_files

def verify_downloads(model_urls):
    """Verify all downloads are complete and not corrupted."""
    print("\n🔍 Verifying downloads...")
    
    all_valid = True
    invalid_files = []
    
    for rel_path, url in model_urls:
        file_path = TARGET_BASE_DIR / rel_path
        
        if not file_path.exists():
            print(f"  ❌ {rel_path}: File not found")
            all_valid = False
            invalid_files.append((rel_path, url))
        else:
            file_size = file_path.stat().st_size
            if file_size == 0:
                print(f"  ❌ {rel_path}: File is empty (0 bytes)")
                all_valid = False
                invalid_files.append((rel_path, url))
            elif file_size < 1024:  # Less than 1KB is suspicious
                print(f"  ⚠  {rel_path}: File is very small ({file_size} bytes) - might be incomplete")
            else:
                size_mb = file_size / (1024*1024)
                print(f"  ✅ {rel_path}: OK ({size_mb:.1f} MB)")
    
    return all_valid, invalid_files

def install_rarfile():
    """Install rarfile module if needed."""
    try:
        import rarfile
        print("✅ rarfile module already installed")
        return True
    except ImportError:
        print("Installing rarfile module...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "rarfile"])
            print("✅ rarfile module installed")
            return True
        except Exception as e:
            print(f"❌ Failed to install rarfile: {e}")
            return False

def extract_rar_files():
    """Extract all .rar files to their respective directories."""
    print("\n" + "=" * 70)
    print("EXTRACTING RAR FILES")
    print("=" * 70)
    
    # Find all .rar files
    rar_files = list(TARGET_BASE_DIR.glob("*.rar"))
    
    if not rar_files:
        print("No .rar files found to extract")
        return True, []
    
    print(f"Found {len(rar_files)} .rar file(s)")
    
    # Install rarfile if needed
    if not install_rarfile():
        print("⚠ Could not install rarfile. Trying alternative extraction methods...")
    
    extracted_files = []
    failed_extractions = []
    skipped_extractions = []
    
    # Check if clean_face_HD.pth already exists in mosaic directory
    clean_face_hd_path = MOSAIC_DIR / "clean_face_HD.pth"
    clean_face_hd_exists = clean_face_hd_path.exists() and clean_face_hd_path.stat().st_size > 1024 * 1024  # > 1MB
    
    if clean_face_hd_exists:
        size_mb = clean_face_hd_path.stat().st_size / (1024*1024)
        print(f"✓ clean_face_HD.pth already exists in mosaic directory ({size_mb:.1f} MB)")
        print("Skipping extraction of RAR files...")
        
        # Ask user if they want to extract anyway
        response = input("Extract RAR files anyway? (y/n): ").lower()
        if response != 'y':
            print("Skipping all RAR file extraction.")
            # Record that all RAR files were skipped
            skipped_extractions = [str(rar_file.name) for rar_file in rar_files]
            return True, []
    
    # Sort RAR files by name to ensure correct order
    rar_files_sorted = sorted(rar_files, key=lambda x: x.name)
    
    # Process each rar file
    for rar_file in rar_files_sorted:
        print(f"\n📦 Processing: {rar_file.name}")
        
        # Skip extraction if the target file already exists
        target_pth_files = []
        try:
            # Try to list contents without extracting
            import rarfile
            rf = rarfile.RarFile(rar_file)
            target_pth_files = [f for f in rf.namelist() if f.endswith('.pth')]
            rf.close()
        except:
            # If we can't list contents, assume we need to extract
            pass
        
        # Check if any target .pth files already exist
        skip_extraction = False
        for pth_filename in target_pth_files:
            pth_path = TARGET_BASE_DIR / pth_filename
            if pth_path.exists() and pth_path.stat().st_size > 1024 * 1024:  # > 1MB
                size_mb = pth_path.stat().st_size / (1024*1024)
                print(f"  ✓ Target file already exists: {pth_filename} ({size_mb:.1f} MB)")
                skip_extraction = True
        
        if skip_extraction and target_pth_files:
            print(f"  Skipping extraction of {rar_file.name}")
            skipped_extractions.append(rar_file.name)
            continue
        
        print(f"  Extracting...")
        
        try:
            # Method 1: Try using rarfile module
            import rarfile
            rf = rarfile.RarFile(rar_file)
            
            # Get list of files in archive
            file_list = rf.namelist()
            print(f"  Files in archive: {len(file_list)}")
            
            # Check if any files already exist
            existing_files = []
            for file_in_rar in file_list:
                extracted_path = TARGET_BASE_DIR / file_in_rar
                if extracted_path.exists():
                    size = extracted_path.stat().st_size
                    if size > 1024:  # More than 1KB
                        existing_files.append(file_in_rar)
            
            if existing_files:
                print(f"  {len(existing_files)} file(s) already exist in target directory")
                response = input(f"  Overwrite existing files? (y/n): ").lower()
                if response != 'y':
                    print(f"  Skipping extraction of {rar_file.name}")
                    skipped_extractions.append(rar_file.name)
                    rf.close()
                    continue
            
            # Extract to the same directory as the rar file
            extract_dir = TARGET_BASE_DIR
            print(f"  Extracting to: {extract_dir.relative_to(TARGET_BASE_DIR.parent.parent)}/")
            
            print("  Extracting...")
            rf.extractall(extract_dir)
            rf.close()
            
            # Record extracted files with their full paths
            for file_in_rar in file_list:
                extracted_path = extract_dir / file_in_rar
                if extracted_path.exists():
                    extracted_files.append(str(extracted_path.relative_to(TARGET_BASE_DIR)))
            
            print(f"  ✅ Successfully extracted {len(file_list)} files")
            
        except Exception as e:
            print(f"  ❌ Failed to extract with rarfile: {e}")
            
            # Method 2: Try command line tools
            print("  Trying command line extraction...")
            success = extract_with_commandline(rar_file, TARGET_BASE_DIR)
            
            if success:
                print(f"  ✅ Successfully extracted with command line")
                # Try to list extracted files
                try:
                    # Look for extracted .pth files
                    extracted_pth_files = list(TARGET_BASE_DIR.glob("*.pth"))
                    for pth_file in extracted_pth_files:
                        if pth_file not in rar_files:  # Don't count RAR files
                            extracted_files.append(str(pth_file.relative_to(TARGET_BASE_DIR)))
                    print(f"  Found {len(extracted_pth_files)} extracted .pth files")
                except:
                    pass
            else:
                print(f"  ❌ Failed to extract")
                failed_extractions.append(str(rar_file.relative_to(TARGET_BASE_DIR)))
    
    # Move clean_face_HD.pth to mosaic directory if extracted
    move_extracted_files_to_mosaic(extracted_files)
    
    # Print summary
    if skipped_extractions:
        print(f"\n📊 Skipped {len(skipped_extractions)} RAR file(s):")
        for rar_name in skipped_extractions:
            print(f"  - {rar_name}")
    
    return len(failed_extractions) == 0, extracted_files

def move_extracted_files_to_mosaic(extracted_files):
    """Move extracted files to their correct directories."""
    print("\n📂 Organizing extracted files...")
    
    moved_count = 0
    skipped_count = 0
    
    # Look for clean_face_HD.pth in the base directory
    base_dir = TARGET_BASE_DIR
    clean_face_hd_path = base_dir / "clean_face_HD.pth"
    mosaic_dir = MOSAIC_DIR
    
    if clean_face_hd_path.exists() and clean_face_hd_path.stat().st_size > 1024:
        print(f"  Found: {clean_face_hd_path.name}")
        
        # Check if already in mosaic directory
        mosaic_version = mosaic_dir / "clean_face_HD.pth"
        if mosaic_version.exists() and mosaic_version.stat().st_size > 1024:
            print(f"  ✓ clean_face_HD.pth already exists in mosaic directory")
            skipped_count += 1
            # Clean up the extracted file in base directory
            try:
                clean_face_hd_path.unlink()
                print(f"  Cleaned up duplicate in base directory")
            except:
                pass
        else:
            # Move to mosaic directory
            try:
                # Ensure mosaic directory exists
                mosaic_dir.mkdir(parents=True, exist_ok=True)
                
                # Move the file
                shutil.move(str(clean_face_hd_path), str(mosaic_dir))
                print(f"  ✅ Moved clean_face_HD.pth to mosaic directory")
                moved_count += 1
                
                # Update extracted_files list
                if "clean_face_HD.pth" in extracted_files:
                    extracted_files.remove("clean_face_HD.pth")
                extracted_files.append(f"mosaic/clean_face_HD.pth")
                
            except Exception as e:
                print(f"  ❌ Failed to move clean_face_HD.pth: {e}")
                # Try copying instead
                try:
                    shutil.copy2(str(clean_face_hd_path), str(mosaic_dir))
                    print(f"  ✅ Copied clean_face_HD.pth to mosaic directory")
                    moved_count += 1
                except Exception as e2:
                    print(f"  ❌ Also failed to copy: {e2}")
    
    # Also check for any other .pth files that should be in mosaic
    for pth_file in base_dir.glob("*.pth"):
        if pth_file.name not in ["clean_face_HD.pth"]:  # Exclude already processed files
            # Check if this looks like a mosaic model
            mosaic_keywords = ['mosaic', 'clean', 'add_face', 'edges2cat']
            if any(keyword in pth_file.name.lower() for keyword in mosaic_keywords):
                mosaic_target = mosaic_dir / pth_file.name
                if mosaic_target.exists() and mosaic_target.stat().st_size > 1024:
                    print(f"  ✓ {pth_file.name} already exists in mosaic directory")
                    skipped_count += 1
                    try:
                        pth_file.unlink()  # Remove duplicate
                        print(f"  Cleaned up duplicate in base directory")
                    except:
                        pass
                else:
                    try:
                        mosaic_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(pth_file), str(mosaic_dir))
                        print(f"  ✅ Moved {pth_file.name} to mosaic directory")
                        moved_count += 1
                        if pth_file.name in extracted_files:
                            extracted_files.remove(pth_file.name)
                        extracted_files.append(f"mosaic/{pth_file.name}")
                    except Exception as e:
                        print(f"  ❌ Failed to move {pth_file.name}: {e}")
    
    print(f"  Summary: Moved {moved_count} files, skipped {skipped_count} duplicates")

def extract_with_commandline(rar_file, target_dir):
    """Extract RAR file using command line tools."""
    try:
        if sys.platform == "win32":
            # Try 7-Zip on Windows
            cmd = ["7z", "x", str(rar_file), f"-o{str(target_dir)}", "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return True
        else:
            # Try unrar on Linux/Mac
            cmd = ["unrar", "x", str(rar_file), str(target_dir), "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return True
            
            # Try 7z as fallback
            cmd = ["7z", "x", str(rar_file), f"-o{str(target_dir)}", "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return True
    except Exception as e:
        print(f"    Command line extraction error: {e}")
    
    return False

def analyze_file_types(model_urls):
    """Analyze and display file types."""
    print("\n📁 File type analysis:")
    
    mosaic_files = [f for f, _ in model_urls if f.startswith('mosaic/')]
    style_files = [f for f, _ in model_urls if f.startswith('style/')]
    rar_files = [f for f, _ in model_urls if f.endswith('.rar')]
    
    mosaic_pth = [f for f in mosaic_files if f.endswith('.pth')]
    style_pth = [f for f in style_files if f.endswith('.pth')]
    
    print(f"  Mosaic directory ({len(mosaic_pth)} .pth files):")
    for i, file in enumerate(sorted(mosaic_pth)[:10], 1):
        print(f"    {i:2d}. {Path(file).name}")
    
    print(f"  Style directory ({len(style_pth)} .pth files):")
    for i, file in enumerate(sorted(style_pth)[:10], 1):
        print(f"    {i:2d}. {Path(file).name}")
    
    if rar_files:
        print(f"  RAR archives ({len(rar_files)} files):")
        print(f"    Will extract clean_face_HD.pth to mosaic directory")

def main():
    print("=" * 70)
    print("DEEPMOSAICS MODEL DOWNLOADER & EXTRACTOR")
    print("=" * 70)
    print("This script will:")
    print("1. Check if DeepMosaics directory exists")
    print("2. Download only missing model files (.pth and .rar)")
    print("3. Keep already downloaded files in mosaic/ and style/ subdirectories")
    print("4. Extract .rar files and move clean_face_HD.pth to mosaic directory")
    print("=" * 70)
    
    # First check if DeepMosaics exists
    if not check_deepmosaics_exists():
        print("\n❌ Cannot continue without DeepMosaics directory.")
        print("Please ensure the directory structure is correct and try again.")
        return
    
    # Setup directories
    print("\n📁 Setting up directory structure...")
    base_dir, mosaic_dir, style_dir = setup_directories()
    
    # Analyze file types
    analyze_file_types(MODEL_URLS)
    
    # Check for existing files and skip downloading them
    files_to_download = check_existing_files_and_skip()
    
    if not files_to_download:
        print(f"\n✅ All files already exist. Skipping download phase.")
        # Still run verification
        all_valid, _ = verify_downloads(MODEL_URLS)
        if all_valid:
            print("\n✅ All files verified successfully.")
        # Proceed to extraction phase if needed
    else:
        # Show download summary
        print(f"\n📥 Download Summary:")
        print(f"  Files to download: {len(files_to_download)}")
        print(f"  Base directory: {base_dir.absolute()}")
        print(f"  Mosaic models: {mosaic_dir.absolute()}")
        print(f"  Style models: {style_dir.absolute()}")
        
        # Show file list
        print("\n📋 Files to download:")
        for i, (rel_path, url) in enumerate(files_to_download, 1):
            filename = Path(rel_path).name
            print(f"    {i:2d}. {filename}")
            if filename.endswith('.rar'):
                print(f"         (Will extract clean_face_HD.pth to mosaic/)")
        
        response = input("\nDo you want to continue? (y/n): ")
        if response.lower() != 'y':
            print("Exiting...")
            return
        
        # PHASE 1: DOWNLOAD MISSING FILES
        print("\n" + "=" * 70)
        print("PHASE 1: DOWNLOADING MISSING FILES")
        print("=" * 70)
        print("⚠  DO NOT INTERRUPT THE DOWNLOAD PROCESS!")
        
        successful, failed_files = download_all_files_concurrent(files_to_download, base_dir, max_workers=3)
        
        if successful < len(files_to_download):
            print(f"\n⚠  Only {successful}/{len(files_to_download)} files downloaded successfully")
            if failed_files:
                response = input("Try to re-download failed files? (y/n): ")
                if response.lower() == 'y':
                    # Re-download failed files
                    for rel_path, error in failed_files:
                        # Find the URL for this filename
                        for model_rel_path, url in MODEL_URLS:
                            if model_rel_path == rel_path:
                                filename = Path(rel_path).name
                                print(f"\nRe-downloading {filename}...")
                                dest_path = base_dir / rel_path
                                # Remove corrupted file
                                if dest_path.exists():
                                    dest_path.unlink()
                                # Re-download
                                progress_dict = {}
                                success, _, new_error = download_file_thread(rel_path, url, dest_path, progress_dict)
                                if success:
                                    print(f"  ✅ Successfully re-downloaded: {filename}")
                                else:
                                    print(f"  ❌ Failed again: {new_error}")
                                break
        
        # Verify downloads (all files, not just downloaded ones)
        print("\n" + "=" * 70)
        print("VERIFYING ALL FILES")
        print("=" * 70)
        
        all_valid, invalid_files = verify_downloads(MODEL_URLS)
        
        if not all_valid:
            print(f"\n⚠  Some files failed verification.")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("Exiting...")
                return
    
    # PHASE 2: EXTRACT RAR FILES (if any exist)
    # Check if clean_face_HD.pth already exists in mosaic
    clean_face_hd_mosaic = mosaic_dir / "clean_face_HD.pth"
    if clean_face_hd_mosaic.exists() and clean_face_hd_mosaic.stat().st_size > 1024:
        print(f"\n⚠  clean_face_HD.pth already exists in mosaic directory")
        size_mb = clean_face_hd_mosaic.stat().st_size / (1024*1024)
        print(f"  {clean_face_hd_mosaic.name} ({size_mb:.1f} MB)")
        
        # Check if RAR files exist
        rar_files = list(base_dir.glob("*.rar"))
        if rar_files:
            response = input(f"\nFound {len(rar_files)} .rar files. Extract them anyway? (y/n): ")
            if response.lower() != 'y':
                print("Skipping RAR extraction.")
                extraction_success = True
                extracted_files = []
            else:
                extraction_success, extracted_files = extract_rar_files()
        else:
            print("No .rar files found to extract.")
            extraction_success = True
            extracted_files = []
    else:
        # Extract RAR files
        extraction_success, extracted_files = extract_rar_files()
    
    # Show final summary
    print("\n" + "=" * 70)
    print("PROCESS COMPLETE!")
    print("=" * 70)
    
    # List all files by directory
    print(f"\n📁 Directory structure:")
    print(f"  Base: {base_dir.absolute()}")
    
    # Mosaic directory contents
    if mosaic_dir.exists():
        mosaic_contents = list(mosaic_dir.iterdir())
        mosaic_contents = [f for f in mosaic_contents if f.is_file() and f.suffix == '.pth']
        if mosaic_contents:
            print(f"\n  Mosaic models ({len(mosaic_contents)} .pth files):")
            for i, item in enumerate(sorted(mosaic_contents)[:20], 1):
                size_mb = item.stat().st_size / (1024*1024)
                print(f"    {i:2d}. {item.name} ({size_mb:.1f} MB)")
            
            if len(mosaic_contents) > 20:
                print(f"    ... and {len(mosaic_contents) - 20} more")
    
    # Style directory contents
    if style_dir.exists():
        style_contents = list(style_dir.iterdir())
        style_contents = [f for f in style_contents if f.is_file() and f.suffix == '.pth']
        if style_contents:
            print(f"\n  Style models ({len(style_contents)} .pth files):")
            for i, item in enumerate(sorted(style_contents)[:20], 1):
                size_mb = item.stat().st_size / (1024*1024)
                print(f"    {i:2d}. {item.name} ({size_mb:.1f} MB)")
            
            if len(style_contents) > 20:
                print(f"    ... and {len(style_contents) - 20} more")
    
    # Find and list .rar files (if any remain)
    rar_files = list(base_dir.glob("*.rar"))
    if rar_files:
        print(f"\n🗜️  Archive files ({len(rar_files)} files - can be deleted):")
        for i, rar_file in enumerate(rar_files[:10], 1):
            size_mb = rar_file.stat().st_size / (1024*1024)
            print(f"  {i:2d}. {rar_file.name} ({size_mb:.1f} MB)")
        
        if len(rar_files) > 10:
            print(f"  ... and {len(rar_files) - 10} more .rar files")
        
        response = input("\nDelete downloaded .rar files to save space? (y/n): ")
        if response.lower() == 'y':
            deleted_count = 0
            for rar_file in rar_files:
                try:
                    rar_file.unlink()
                    deleted_count += 1
                except:
                    pass
            print(f"✅ Deleted {deleted_count} .rar files")
    
    print("\n" + "=" * 70)
    if extraction_success:
        print("✅ SUCCESS: All files downloaded and organized!")
        print(f"\nModels are organized in:")
        print(f"  Mosaic: {mosaic_dir.absolute()}")
        print(f"  Style: {style_dir.absolute()}")
        
        # Check if clean_face_HD.pth is in mosaic
        if (mosaic_dir / "clean_face_HD.pth").exists():
            size_mb = (mosaic_dir / "clean_face_HD.pth").stat().st_size / (1024*1024)
            print(f"  clean_face_HD.pth is in mosaic directory ({size_mb:.1f} MB)")
    else:
        print("⚠  WARNING: Some .rar files failed to extract")
        print("   You may need to extract them manually")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠  Process interrupted by user!")
        print("If downloads were interrupted, you may need to:")
        print(f"1. Check the '{TARGET_BASE_DIR}' folder for partial files")
        print("2. Delete any incomplete files")
        print("3. Run the script again")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("\nPlease check your network connection and try again.")