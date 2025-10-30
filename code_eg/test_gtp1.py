import re
import requests
import os
import time
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- CONFIG ----------
base_url = "https://www.dhammadownload.com/"
main_page = "https://www.dhammadownload.com/AudioInMyanmar.htm"
max_threads = 5  # Adjust for faster/slower multi-threading
# ----------------------------

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

print("🔍 Scanning for Sayadaw categories and audio files...\n")
download_dest = choose_destination()
file_list = []
category_count = 0
total_size = 0

# ---------- FETCH MAIN PAGE ----------
try:
    print("\nFetching main page...")
    response = requests.get(main_page, timeout=10)
    html_content = response.text
    sayadaw_pattern = r'href="([^"]*[Ss]ayadaw[^"]*\.htm)"'
    sayadaw_links = sorted(set(re.findall(sayadaw_pattern, html_content)))
    print(f"Found {len(sayadaw_links)} Sayadaw categories\n")

    for sayadaw_href in sayadaw_links:
        category_url = urljoin(base_url, sayadaw_href)
        category_name = sayadaw_href.replace('.htm', '').replace('/', '_')
        print(f"📁 {category_name}")
        category_count += 1

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
                print(f"  ✓ {filename}")
        except Exception as e:
            print(f"  ✗ Error accessing category: {e}")

except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*60)
print(f"📊 Total categories: {category_count}")
print(f"📊 Total files: {len(file_list)}")
print(f"📂 Download to: {download_dest}")
print("="*60)

# ---------- USER CHOICE ----------
print("\n1. Check total file sizes first")
print("2. Skip and download now")
mode = input("\nEnter choice (1 or 2): ").strip()

if mode == '1':
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

# ---------- DOWNLOAD FUNCTION ----------
def download_file(item, idx, total, skip_head):
    category_path = os.path.join(download_dest, item['category'])
    os.makedirs(category_path, exist_ok=True)
    filepath = os.path.join(category_path, item['filename'])
    existing_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0

    total_file_size = 0
    if not skip_head:
        try:
            head = requests.head(item['url'], timeout=10, allow_redirects=True)
            total_file_size = int(head.headers.get('content-length', 0))
        except:
            total_file_size = 0

    if total_file_size and existing_size >= total_file_size:
        return f"[{idx}/{total}] ✅ {item['category']}/{item['filename']} (already complete)"

    headers = {'Range': f'bytes={existing_size}-'} if existing_size > 0 else {}
    mode_write = 'ab' if existing_size > 0 else 'wb'
    start_text = "↻ Resuming" if existing_size > 0 else "⬇ Downloading"

    try:
        with requests.get(item['url'], headers=headers, stream=True, timeout=30) as r:
            with open(filepath, mode_write) as f:
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
        return f"[{idx}/{total}] {start_text} {item['category']}/{item['filename']} ✓"
    except Exception as e:
        return f"[{idx}/{total}] {start_text} {item['category']}/{item['filename']} ✗ ({e})"

# ---------- MULTI-THREAD DOWNLOAD ----------
print("\n⬇️  Starting parallel downloads (resume supported)...\n")
skip_head = (mode == '2')

with ThreadPoolExecutor(max_workers=max_threads) as executor:
    futures = []
    for idx, item in enumerate(file_list, 1):
        futures.append(executor.submit(download_file, item, idx, len(file_list), skip_head))
    for future in as_completed(futures):
        print(future.result())

print("\n✓ All downloads complete with resume support.")

