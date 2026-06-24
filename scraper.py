import os
import json
import time
import datetime
import requests

# ==========================================
# CONFIGURATION & API SETTINGS
# ==========================================
API_URL = "https://zillow-com-real-estate-api.p.rapidapi.com/search"  # Update to match your provider endpoint
API_KEY = "YOUR_REAL_ESTATE_API_KEY_HERE"
API_HOST = "zillow-com-real-estate-api.p.rapidapi.com"
OUTPUT_FILE = "listings.json"

PRICE_MAX = 750000

# ==========================================
# GEOGRAPHIC COHORTS (STRATIFIED BY VELOCITY)
# ==========================================

# Core high-turnover hubs monitored 100% daily
DAILY_HUBS = [
    "Anaheim", "Fullerton", "Orange", "Santa Ana", "Tustin", 
    "Costa Mesa", "Garden Grove", "Huntington Beach", "Irvine"
]

# Cohort A (Scraped on EVEN days of the year)
COHORT_A = [
    "Buena Park", "Placentia", "Yorba Linda", "Brea", "La Habra", 
    "Cypress", "La Palma", "Los Alamitos", "Stanton", "Westminster", 
    "Fountain Valley", "Newport Beach", "Seal Beach", "Villa Park",
    "Alhambra", "Arcadia", "Azusa", "Baldwin Park", "Covina",
    "Oceanside", "Vista", "Riverside"
]

# Cohort B (Scraped on ODD days of the year)
COHORT_B = [
    "El Monte", "Glendora", "Monrovia", "Pasadena", "Pomona", 
    "Rosemead", "San Dimas", "San Gabriel", "Temple City", "West Covina",
    "Chino", "Chino Hills", "Corona", "Fontana", "Ontario",
    "Lake Forest", "Aliso Viejo", "Rancho Santa Margarita", "Mission Viejo",
    "San Juan Capistrano", "Capistrano Beach"
]

def get_active_targets():
    """Determines today's precise tracking grid based on day-of-year modulo."""
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    is_even = (day_of_year % 2 == 0)
    
    active_cohort = COHORT_A if is_even else COHORT_B
    cohort_label = "Cohort A (Even Day)" if is_even else "Cohort B (Odd Day)"
    
    print(f"--- Initialization: Day of Year {day_of_year} ({cohort_label}) ---")
    return DAILY_HUBS + active_cohort

def fetch_city_listings(city, max_retries=4):
    """Fetches real estate listings for a targeted city with exponential backoff handling."""
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    params = {
        "location": f"{city}, CA",
        "status": "forSale",
        "maxPrice": str(PRICE_MAX)
    }
    
    delay = 2
    for attempt in range(max_retries):
        try:
            print(f"   Querying dynamic payload for {city}...")
            response = requests.get(API_URL, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("listings", []) or data.get("results", []) or data.get("props", [])
                return results
            elif response.status_code == 429:
                print(f"   [429 Rate Limit hit] Backing off. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"   [Error] Received status code {response.status_code} for {city}")
                return []
        except Exception as e:
            print(f"   [Exception] Connection failed on attempt {attempt + 1}: {e}")
            time.sleep(delay)
            delay *= 2
            
    print(f" ❌ Skipping {city} after failing all retry configurations.")
    return []

def process_and_normalize(raw_data, city_name):
    """Normalizes vendor-specific variants into consistent frontend data properties."""
    normalized = []
    for item in raw_data:
        prop_type = str(item.get("propertyType", "") or item.get("homeType", "")).lower()
        
        # Flag manufactured homes instead of skipping them
        is_manufactured = "manufactured" in prop_type or "mobile" in prop_type
            
        price = item.get("price", 0)
        if not price or price > PRICE_MAX:
            continue

        normalized.append({
            "zpid": str(item.get("zpid") or item.get("id")),
            "price": price,
            "beds": item.get("bedrooms") or item.get("beds") or 0,
            "baths": item.get("bathrooms") or item.get("baths") or 0,
            "address": item.get("address", "Address Not Disclosed"),
            "city": city_name,
            "imgSrc": item.get("imgSrc") or item.get("image") or "",
            "propertyType": "Manufactured" if is_manufactured else prop_type.replace("_", " ").title(),
            "isManufactured": is_manufactured,
            "url": item.get("detailUrl") or f"https://www.zillow.com/homedetails/{item.get('zpid')}_zpid/"
        })
    return normalized

def merge_and_save_data(new_listings, active_cities):
    """Ensures staggered architecture persists old data while cleanly merging fresh scans."""
    existing_data = []
    
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                existing_data = json.load(f)
            print(f" Successfully mapped {len(existing_data)} cached records from disk.")
        except Exception as e:
            print(f" Could not read existing {OUTPUT_FILE} safely ({e}). Initializing clean baseline.")
            existing_data = []

    active_cities_upper = [c.upper() for c in active_cities]
    purged_dataset = [
        listing for listing in existing_data 
        if str(listing.get("city", "")).upper() not in active_cities_upper
    ]
    
    final_dataset = purged_dataset + new_listings
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(final_dataset, f, indent=4)
        
    print(f"\n Pipeline Complete: Wrote {len(new_listings)} new/updated rows.")
    print(f" Database updated smoothly. Total visible inventory count: {len(final_dataset)}")

def main():
    active_cities = get_active_targets()
    print(f"Running pipeline across {len(active_cities)} total target hubs today.\n")
    
    all_fresh_listings = []
    
    for idx, city in enumerate(active_cities, 1):
        print(f"[{idx}/{len(active_cities)}] Processing target: {city}")
        raw_results = fetch_city_listings(city)
        
        if raw_results:
            normalized_results = process_and_normalize(raw_results, city)
            all_fresh_listings.extend(normalized_results)
            print(f"   Found {len(normalized_results)} valid listings matching baseline scope.")
        
        time.sleep(1.2)
        
    merge_and_save_data(all_fresh_listings, active_cities)

if __name__ == "__main__":
    main()
