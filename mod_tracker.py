import time
import json
import os
import re
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
BASE_URL = "https://www.curseforge.com"
SEARCH_URL = f"{BASE_URL}/hytale/search?page=1&pageSize=20&sortBy=total+downloads&class=mods"
DATA_FILE = "mod_data.json"
UPDATE_INTERVAL_SECONDS = 3600  # Do not lower this. Deep scraping requires strict rate limits.

def get_mod_data():
    """Crawls the search page, then deep-dives into individual mod pages for richer data."""
    scraper = cloudscraper.create_scraper() 
    print("Fetching main leaderboard...")
    response = scraper.get(SEARCH_URL)
    
    if response.status_code != 200:
        print(f"Failed to fetch main page. Status: {response.status_code}")
        return {}

    soup = BeautifulSoup(response.text, 'html.parser')
    cards = soup.select(".project-card")
    
    top_mods = {}
    
    for rank, card in enumerate(cards[:10], start=1):
        try:
            # 1. Surface Level Data
            name_elem = card.select_one(".name")
            name = name_elem.get_text(strip=True) if name_elem else "Unknown"
            
            dl_elem = card.select_one(".detail-downloads")
            downloads = parse_downloads(dl_elem.get_text(strip=True)) if dl_elem else 0
            
            author_elem = card.select_one(".author")
            author = author_elem.get_text(strip=True) if author_elem else "Unknown"
            
            date_elem = card.select_one(".date-updated") or card.select_one("abbr")
            updated_date = date_elem.get_text(strip=True) if date_elem else "Unknown"

            # 2. Extract Mod URL for Deep Scraping
            link_elem = card.select_one("a.overlay-link") or card.select_one("a")
            mod_url = BASE_URL + link_elem['href'] if link_elem else ""

            dependents_count = 0
            
            # 3. Deep Crawl: Modpack Relations
            if mod_url:
                # Target the specific page where other modpacks link to this mod
                dependents_url = f"{mod_url}/relations/dependents?filter-related-dependents=6"
                
                # CRITICAL: Pause to mimic human browsing and bypass Cloudflare
                time.sleep(3) 
                
                dep_response = scraper.get(dependents_url)
                if dep_response.status_code == 200:
                    dep_soup = BeautifulSoup(dep_response.text, 'html.parser')
                    
                    # Look for text like "Viewing 1 - 20 of 1,245"
                    pagination = dep_soup.select_one(".pagination-text, .pagination-top")
                    if pagination:
                        match = re.search(r'of\s+([0-9,]+)', pagination.text)
                        if match:
                            dependents_count = int(match.group(1).replace(',', ''))
                    else:
                        # Fallback: manually count visible cards if there is only one page
                        dependents_count = len(dep_soup.select(".project-card"))

            # Build the rich data payload
            top_mods[name] = {
                "rank": rank,
                "downloads": downloads,
                "author": author,
                "last_updated": updated_date,
                "modpacks_included": dependents_count
            }
            
            print(f"[{rank}/10] Parsed '{name}' | Modpacks tracking this: {dependents_count}")
            
        except Exception as e:
            print(f"Skipping rank {rank} due to parse error: {e}")
            continue
            
    return top_mods

def parse_downloads(dl_str):
    """Converts metric strings to integers."""
    dl_str = dl_str.upper().replace(',', '')
    try:
        if 'K' in dl_str: return int(float(dl_str.replace('K', '')) * 1000)
        elif 'M' in dl_str: return int(float(dl_str.replace('M', '')) * 1000000)
        elif 'B' in dl_str: return int(float(dl_str.replace('B', '')) * 1000000000)
        return int(float(dl_str))
    except ValueError:
        return 0

def update_data(new_data):
    """Appends the deep metrics into the JSON database."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            history = json.load(f)
    else:
        history = {}

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for mod, data in new_data.items():
        if mod not in history:
            history[mod] = {
                "author": data["author"],
                "history": {
                    "timestamps": [],
                    "downloads": [],
                    "ranks": [],
                    "last_updated": [],
                    "modpacks_included": []
                }
            }
        
        history[mod]["history"]["timestamps"].append(current_time)
        history[mod]["history"]["downloads"].append(data["downloads"])
        history[mod]["history"]["ranks"].append(data["rank"])
        history[mod]["history"]["last_updated"].append(data["last_updated"])
        history[mod]["history"]["modpacks_included"].append(data["modpacks_included"])

    with open(DATA_FILE, "w") as f:
        json.dump(history, f, indent=4)

def main():
    print("Starting Deep Analytics Scraper...")
    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Initiating crawl sequence...")
            new_data = get_mod_data()
            
            if new_data:
                update_data(new_data)
                print("JSON database updated successfully.")
            else:
                print("Crawl blocked or failed.")
                
        except Exception as e:
            print(f"Fatal error during cycle: {e}")
        
        print(f"Sleeping for {UPDATE_INTERVAL_SECONDS} seconds to clear rate limits...")
        time.sleep(UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()