from fastapi import FastAPI, HTTPException, status, Path, Header
import requests
from dotenv import load_dotenv
import os
import random
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv()

last_fm_key = os.getenv("LASTFM_API_KEY")
ticketmasters_key = os.getenv("TICKETMASTER_API_KEY")
api_passwd = os.getenv("API_PASSWD")

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"], allow_credentials=True, allow_methods=["GET"], allow_headers=["passwd", "Content-Type", "Authorization"])

@app.get("/new-artist/{name}/{limit}")
def get_similar(
        name: str = Path(..., min_length=1, description="Trzeba podać nazwę artysty"), 
        limit: int = Path(..., ge=1, le=3, description="Limit musi być liczbą z przedziału 1 do 3"),
        passwd: str = Header(None)):
    if passwd != api_passwd:
        raise HTTPException(status_code=401, detail="Brak autoryzacji")

    url = f"http://ws.audioscrobbler.com/2.0/?method=artist.getsimilar&artist={name}&api_key={last_fm_key}&format=json&limit=50"
    res_json = requests.get(url).json()

    if "error" in res_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artysta nie został znaleziony"
        )

    res = res_json["similarartists"]["artist"]

    if not res:
        return []

    l = min(len(res), limit)

    ans = random.sample(res, l)
    return [a["name"] for a in ans]

@app.get("/albums/{name}")
def get_artist_album(name: str= Path(..., min_length=1, description="Trzeba podać nazwę artysty"), passwd: str = Header(None)):
    if passwd != api_passwd:
        raise HTTPException(status_code=401, detail="Brak autoryzacji")

    url = f"http://ws.audioscrobbler.com/2.0/?method=artist.gettopalbums&artist={name}&api_key={last_fm_key}&format=json&limit=10"
    res_json = requests.get(url).json()

    if "error" in res_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artysta nie został znaleziony"
        )
    
    res_albums = res_json["topalbums"]["album"]
    res = []

    for a in res_albums:
        images = a.get("image", [])
        img_url = ""
        if images:
            ind = min(2, len(images)-1)
            img_url = images[ind].get("#text", "")
        res.append((a.get("name", "Brak nazwy"), img_url, int(a.get("playcount", 0))))

    if (len(res) == 0): return {"avg": 0, "min": 0, "max": 0,"albums": []}

    avg = 0
    mini = float("inf")
    maxi = -float("inf")
    for element in res:
        avg += element[-1]

        if (mini > element[-1]):
            mini = element[-1]
        if (maxi < element[-1]):
            maxi = element[-1]

    avg = avg/len(res)
    return {"avg": avg, "min": mini, "max": maxi,"albums": res[:min(3, len(res))]}

@app.get("/tags/{name}")
def get_tags(name: str = Path(..., min_length=1, description="Trzeba podać nazwę artysty"), passwd: str = Header(None)):
    if passwd != api_passwd:
        raise HTTPException(status_code=401, detail="Brak autoryzacji")

    url = f"http://ws.audioscrobbler.com/2.0/?method=artist.gettoptags&artist={name}&api_key={last_fm_key}&format=json"
    res_json = requests.get(url).json()

    if "error" in res_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artysta nie został znaleziony"
        )
    
    tags_list = res_json.get("toptags", {}).get("tag", [])
    if not isinstance(tags_list, list):
        tags_list = [tags_list]
    
    return [a.get("name", "Brak tagów") for a in tags_list][:5]

@app.get("/country/{name}")
def get_artists_by_country(name: str = Path(..., min_length=1, description="Trzeba podać nazwę kraju"), passwd: str = Header(None)):
    if passwd != api_passwd:
        raise HTTPException(status_code=401, detail="Brak autoryzacji")

    url = f"http://ws.audioscrobbler.com/2.0/?method=geo.gettopartists&country={name}&api_key={last_fm_key}&format=json&limit=20"
    res_json = requests.get(url).json()

    if "error" in res_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nie znaleziono kraju"
        )
    
    res = res_json["topartists"]["artist"]
    mini = min(res, key=lambda element: int(element.get("listeners", 0)))
    maxi = max(res, key=lambda element: int(element.get("listeners", 0)))
    
    return {"arr": [a["name"] for a in res], "min": mini, "max": maxi}

def get_stats(arr):
    min_price_sum = 0
    min_counter = 0
    max_price_sum = 0
    max_counter = 0

    for concert in arr:
        if concert["price_min"] != "Brak danych":
            min_price_sum += float(concert["price_min"])
            min_counter += 1
        if concert["price_max"] != "Brak danych":
            max_price_sum += float(concert["price_max"])
            max_counter += 1

    min_avg = min_price_sum/min_counter if min_counter != 0 else 0
    max_avg = max_price_sum/max_counter if max_counter != 0 else 0
    
    # (min,max)
    return (min_avg, max_avg)
    


@app.get("/events/{name}")
def get_events(name: str = Path(..., min_length=1, description="Trzeba podać nazwę artysty"), passwd: str = Header(None)):
    if passwd != api_passwd:
        raise HTTPException(status_code=401, detail="Brak autoryzacji")

    url = f"https://app.ticketmaster.com/discovery/v2/events?apikey={ticketmasters_key}&keyword={name}"
    res_json = requests.get(url).json()

    if "fault" in res_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nie znaleziono eventów"
        )
    
    if "_embedded" not in res_json:
        return {"arr": [], "min_avg": 0, "max_avg": 0}
        
    res = res_json["_embedded"]["events"]
    res_to_return = []

    for concert in res:
        price = concert.get("priceRanges", [])
        venues = concert.get("_embedded", {}).get("venues", [])

        if price:
            price_min = price[0].get("min", "Brak danych")
            price_max = price[0].get("max", "Brak danych")
            currency = price[0].get("currency", "Brak danych")
        else:
            price_min = "Brak danych"
            price_max = "Brak danych"
            currency = "Brak danych"

        
        city = venues[0].get("city", {}).get("name", "Brak danych") if venues else "Brak danych"
        c_name = concert.get("name")
        d = concert.get("dates", {}).get("start",{}).get("localDate", "Brak danych")
    
        res_to_return.append({
            "name": c_name,
            "date": d,
            "city": city,
            "price_min": price_min,
            "price_max": price_max,
            "currency": currency
        })

    min_avg, max_avg = get_stats(res_to_return)
    res_to_return = random.sample(res_to_return, min(3, len(res_to_return)))
    return {"arr": res_to_return, "min_avg": min_avg, "max_avg": max_avg}

@app.get("/")
async def serve_index():
    return FileResponse("index.html")