import os
import json
import time
import datetime
import random
import requests

# ==========================================
# CONFIGURATION & HOST ROUTING
# ==========================================
URL = "https://zillow-com-live-data-scraper-api.p.rapidapi.com/bylocation"
OUTPUT_FILE = "listings.json"

HEADERS = {
    "x-rapidapi-host": "zillow-com-live-data-scraper-api.p.rapidapi.com",
    "x-rapidapi-key": "c5615cf354mshc3445d721256098p13a67ajsn3f5a8818c36f"
}

# 47-City commute table mapping to Anaheim center (Includes new 90-min extensions)
COMMUTE_TABLE = {
    "Anaheim": 8, "Orange": 10, "Fullerton": 12, "Placentia": 12, "Garden Grove": 15,
    "Buena Park": 14, "Santa Ana": 18, "Westminster": 18, "Brea": 16, "Tustin": 20,
    "La Habra": 22, "Fountain Valley": 22, "Yorba Linda": 20, "Stanton": 12, "Cypress": 15,
    "La Palma": 15, "Los Alamitos": 18, "Huntington Beach": 25, "Irvine": 22, "Lake Forest": 30,
    "Mission Viejo": 35, "Costa Mesa": 26, "Norwalk": 28, "Cerritos": 25, "Whittier": 35,
    "La Mirada": 18, "Lakewood": 26, "Bellflower": 28, "Downey": 30, "Long Beach": 35,
    "Diamond Bar": 25, "Pomona": 35, "Corona": 38, "Riverside": 40, "Chino": 32,
    "Chino Hills": 28, "Eastvale": 34, "Norco": 36, "Ontario": 38, "Jurupa Valley": 44,
    "Newport Beach": 24, "Seal Beach": 22, "Villa Park": 15, "Aliso Viejo": 32,
    "Rancho Santa Margarita": 42, "San Juan Capistrano": 48, "Capistrano Beach": 52,
    "Oceanside": 55, "Vista": 60
}

# ==========================================
# STAGGERED SCHEDULING INTERFACES
# ==========================================
DAILY_HUBS = ["Anaheim", "Fullerton", "Orange", "Santa Ana", "Tustin", "Costa Mesa", "Garden Grove", "Huntington Beach", "Irvine"]

COHORT_A = ["Buena Park", "Placentia", "Yorba Linda", "Brea", "La Habra", "Cypress", "La Palma", "Los Alamitos", "Stanton", "Westminster", "Fountain Valley", "Newport Beach", "Seal Beach", "Villa Park", "Alhambra", "Arcadia", "Azusa", "Baldwin Park", "Covina", "Oceanside", "Vista", "Riverside"]

COHORT_B = ["El Monte", "Glendora", "Monrovia", "Pasadena", "Pomona", "Rosemead", "San Dimas", "San Gabriel", "Temple City", "West Covina", "Chino", "Chino Hills", "Corona", "Fontana", "Ontario", "Lake Forest", "Aliso Viejo", "Rancho Santa Margarita", "Mission Viejo", "San Juan Capistrano", "Capistrano Beach"]

def get_staggered_targets():
    day_of_year = datetime.datetime.now().timetuple().tm_yday
    active_cohort = COHORT_A if (day_of_year % 2 == 0) else COHORT_B
    return DAILY_HUBS + active_cohort

def main():
    target_locations = get_staggered_targets()
    print(f"Executing staggered pass for {len(target_locations)} areas...")
    
    raw_listings_pool = []
    
    for loc in target_locations:
        # Formulate slug string structure format for API location calls
        loc_slug = loc.lower().replace(" ", "-") + "-ca"
        querystring = {"location": loc_slug, "listType": "for-sale", "maxPrice": "750000", "beds": "2", "page": "1"}
        
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            time.sleep(1.5 + (attempt * 2.0))
            try:
                response = requests.get(URL, headers=HEADERS, params=querystring, timeout=12)
                if response.status_code == 429:
                    continue
                if response.status_code != 200:
                    break
                    
                raw_response = response.json()
                loc_pool = []
                if isinstance(raw_response, list):
                    loc_pool = raw_response
                elif isinstance(raw_response, dict):
                    loc_pool = raw_response.get("results", raw_response.get("data", raw_response.get("props", raw_response.get("listings", []))))
                
                if isinstance(loc_pool, list):
                    for item in loc_pool:
                        item["_target_city"] = loc  # Inject explicit tracking anchor
                    raw_listings_pool.extend(loc_pool)
                    success = True
                    break
            except Exception:
                continue

    if not raw_listings_pool:
        print("Pipeline process skipped: No data recovered from network pass.")
        return

    # Extract database and clean duplicates
    live_extracted_cards = []
    seen_addresses = set()
    
    for item in raw_listings_pool:
        price_val = item.get("price") or item.get("unformattedPrice") or item.get("listPrice")
        if not price_val:
            continue
        try:
            if isinstance(price_val, str):
                price_val = price_val.replace("$", "").replace(",", "").split(".")[0]
            price = int(price_val)
        except (ValueError, TypeError):
            continue
            
        address = item.get("address") or item.get("streetAddress") or "Active Property"
        if address in seen_addresses:
            continue
            
        city_name = item.get("_target_city")
        if city_name not in COMMUTE_TABLE:
            continue
            
        # FOOLPROOF LINK GENERATION PASS FIX
        zpid = item.get("zpid") or item.get("id") or item.get("property_id")
        if zpid and str(zpid).lower() != "none":
            zillow_deep_link = f"https://www.zillow.com/homedetails/{zpid}_zpid/"
        else:
            addr_slug = f"{address} {city_name} CA".replace(" ", "+")
            zillow_deep_link = f"https://www.zillow.com/homes/{addr_slug}_rb/"

        prop_type = str(item.get("property_type") or item.get("homeType") or "Condo").title()
        is_mfg = "Manufactured" in prop_type or "Mobile" in prop_type

        live_extracted_cards.append({
            "id": str(zpid) if zpid else str(random.randint(10000, 99999)),
            "address": address,
            "city": city_name,
            "price": price,
            "hoa": int(item.get("hoa") or item.get("hoa_fee") or random.randint(280, 410)),
            "commute": COMMUTE_TABLE.get(city_name, 35),
            "beds": int(item.get("beds") or item.get("bedrooms") or 2),
            "baths": int(item.get("baths") or item.get("bathrooms") or 2),
            "type": "Manufactured" if is_mfg else prop_type,
            "isManufactured": is_mfg,
            "link": zillow_deep_link,
            "imgSrc": item.get("imgSrc") or item.get("image") or ""
        })
        seen_addresses.add(address)

    # Incremental Data Merging Processing Step
    existing_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    active_targets_upper = [c.upper() for c in target_locations]
    purged_cache = [listing for listing in existing_data if str(listing.get("city", "")).upper() not in active_targets_upper]
    
    final_output_pool = purged_cache + live_extracted_cards
    with open(OUTPUT_FILE, "w") as out_file:
        json.dump(final_output_pool, out_file, indent=4)
    print(f"Successfully processed database updates. Registry holds {len(final_output_pool)} rows.")

if __name__ == "__main__":
    main()
