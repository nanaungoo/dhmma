import re
import requests
import os
import json
import time
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ---------------- CONFIG ----------------
base_url = "https://www.dhammadownload.com/"
main_page = "https://www.dhammadownload.com/AudioInMyanmar.htm"
max_threads = 3
max_retries = 3
retry_delay = 5
failed_log = "failed_downloads.txt"
cache_file = "file_list_cache.json"
# ----------------------------------------

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} TB"

def choose_destination():
    print("\n" + "="*60)
    print("📁 CHOOSE DOWNLOAD DESTINATION")
    print("="*60)
    print("\n1. Current folder (~/dhamma_download)")
    print("2. External drive (custom path)")
    print("3. Home directory (~/)")
    print("4. Custom path")

    while True:
        choice = input("\nEnter choice (1-4): ").strip()
        if choice == '1':
            dest = os.path.expanduser("~/dhamma_download")
            break
        elif choice == '2':
            dest = os.path.expanduser(input("Enter external drive path: ").strip())
            break
        elif choice == '3':
            dest = os.path.expanduser("~/")
            break
        elif choice == '4':
            dest = os.path.expanduser(input("Enter custom path: ").strip())
            break
        else:
            print("❌ Invalid choice. Try again.")
    
    os.makedirs(dest, exist_ok=True)
    print(f"\n✅ Destination set to: {dest}")
    return dest

# ---------- LOAD CACHE ----------
def load_cache():
    if os.path.exists(cache_file):
        use_cache = input("\n💾 Load cached file list? (y/n): ").strip().lower()
        if use_cache in ['y', 'yes']:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    return []

# ---------- SAVE CACHE ----------
def save_cache(file_list):
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(file_list, f, ensure_ascii=False, indent=2)

# ---------- FETCH SAYADAW AUDIO ----------
def fetch_audio_list():
    print("\n🔍 Scanning for Sayadaw categories and audio files...\n")
    try:
        response = requests.get(main_page, timeout=10)
        html_content = response.text
        sayadaw_pattern = r'href="([^"]*[Ss]ayadaw[^"]*\.htm)"'
        sayadaw_links = sorted(set(re.findall(sayadaw_pattern, html_content)))
        print(f"Found {len(sayadaw_links)} Sayadaw categories\n")

        file_list = []
        for sayadaw_href in sayadaw_links:
            category_url = urljoin(base_url, sayadaw_href)
            category_name = sayadaw_href.replace('.htm', '').replace('/', '_')
            print(f"📁 {category_name}")
            try:
                cat_response = requests.get(category_url, timeout=10)
                cat_html = cat_response.text
                audio_pattern = r'href="([^"]*\.(mp3|m4a|wav|ogg))"'
                audio_urls = list(set(link[0] for link in re.findall(audio_pattern, cat_html, re.IGNORECASE)))

                for audio_href in audio_urls:
                    audio_url = urljoin(base_url, audio_href)
                    filename = audio_href.split('/')[-1]
                    file_list.append({
                        'category': category_name,
                        'filename': filename,
                        'url': audio_url
                    })
            except Exception as e:
                print(f"  ✗ Error accessing category: {e}")

        save_cache(file_list)
        return file_list

    except Exception as e:
        print(f"Error: {e}")
        return []

# ---------- RETRY DECORATOR ----------
def retry_request(func):
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise e
    return wrapper

@retry_request
def download_with_retry(url, headers, mode, filepath, progress_bar):
    with requests.get(url, headers=headers, stream=True, timeout=30) as r:
        total = int(r.headers.get('content-length', 0))
        with open(filepath, mode) as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    progress_bar.update(len(chunk))

# ---------- DOWNLOAD FUNCTION ----------
def download_file(item, idx, total, skip_head, download_dest):
    category_path = os.path.join(download_dest, item['category'])
    os.makedirs(category_path, exist_ok=True)
    filepath = os.path.join(category_path, item['filename'])

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        return None  # skip existing

    existing_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    total_file_size = 0

    if not skip_head:
        try:
            head = requests.head(item['url'], timeout=10, allow_redirects=True)
            total_file_size = int(head.headers.get('content-length', 0))
        except:
            total_file_size = 0

    if total_file_size and existing_size >= total_file_size:
        return None

    headers = {'Range': f'bytes={existing_size}-'} if existing_size > 0 else {}
    mode_write = 'ab' if existing_size > 0 else 'wb'
    start_text = "↻ Resuming" if existing_size > 0 else "⬇ Downloading"

    try:
        with tqdm(
            total=total_file_size if total_file_size else None,
            initial=existing_size,
            unit='B',
            unit_scale=True,
            desc=f"[{idx}/{total}] {item['filename'][:40]}",
            leave=False,
        ) as progress_bar:
            download_with_retry(item['url'], headers, mode_write, filepath, progress_bar)
        return f"[{idx}/{total}] {start_text} {item['category']}/{item['filename']} ✓"
    except Exception as e:
        with open(failed_log, 'a', encoding='utf-8') as log:
            log.write(f"{item['url']}\n")
        return f"[{idx}/{total}] {start_text} {item['category']}/{item['filename']} ✗ ({e})"

# ---------- MAIN EXECUTION ----------
def main():
    download_dest = choose_destination()
    file_list = load_cache()
    if not file_list:
        file_list = fetch_audio_list()

    print("\n" + "="*60)
    print(f"📊 Total files: {len(file_list)}")
    print(f"📂 Download to: {download_dest}")
    print("="*60)

    print("\n1. Check total file sizes first")
    print("2. Skip and download now (fast mode)")
    mode = input("\nEnter choice (1 or 2): ").strip()
    skip_head = (mode == '2')

    if mode == '1':
        total_size = 0
        print("\n📏 Checking file sizes...\n")
        for item in file_list:
            try:
                head = requests.head(item['url'], timeout=10, allow_redirects=True)
                size = int(head.headers.get('content-length', 0))
                item['size'] = size
                total_size += size
                print(f"  ✓ {item['filename']} ({format_size(size)})")
            except Exception as e:
                print(f"  ✗ {item['filename']} - Error: {e}")
        print(f"\n📦 Total size: {format_size(total_size)}")
        confirm = input("\nDownload now? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Cancelled.")
            exit()

    print("\n⬇️  Starting parallel downloads (retry + resume supported)...\n")

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = []
        for idx, item in enumerate(file_list, 1):
            futures.append(executor.submit(download_file, item, idx, len(file_list), skip_head, download_dest))
        for future in as_completed(futures):
            result = future.result()
            if result:
                print(result)

    print("\n✓ All downloads complete.")
    print(f"❗ Failed URLs (if any) are saved in: {failed_log}")

if __name__ == "__main__":
    main()

