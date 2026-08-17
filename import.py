import json
import requests

# Tes identifiants Supabase
SUPABASE_URL = "https://jzurawtfxwyinwzowpkx.supabase.co"
SUPABASE_KEY = "sb_publishable_OXqEOCgFVL4qbZUHK7DaKg_o6BzN8rK"

# Liste complète de tes articles prête à être injectée
articles = [
    {
        "item_id": "1",
        "name": "Pantalon Nike Trail",
        "taille": "S",
        "etat": "8/10 (petite égratignure sur le genou)",
        "prix": 60.0,
        "poids": 350,
    },
    {
        "item_id": "2",
        "name": "Pantalon Nike Aeroswift",
        "taille": "M",
        "etat": "Excellent état",
        "prix": 75.0,
        "poids": 300,
    },
    {
        "item_id": "3",
        "name": "Pantalon Nike Phenom Elite",
        "taille": "L",
        "etat": "Excellent état",
        "prix": 90.0,
        "poids": 350,
    },
    {
        "item_id": "4",
        "name": "Sweat Nike Tech Aviateur v1",
        "taille": "M",
        "etat": "Excellent état",
        "prix": 60.0,
        "poids": 400,
    },
    {
        "item_id": "5",
        "name": "Pantalon Nike Phenom Elite (Gris)",
        "taille": "L",
        "etat": "Excellent état",
        "prix": 90.0,
        "poids": 350,
    },
    {
        "item_id": "6",
        "name": "Tee-Shirt Nike Trail",
        "taille": "S",
        "etat": "Excellent état",
        "prix": 40.0,
        "poids": 150,
    },
    {
        "item_id": "7",
        "name": "Tee-Shirt Nike Running Division",
        "taille": "M",
        "etat": "Excellent état",
        "prix": 35.0,
        "poids": 150,
    },
    {
        "item_id": "8",
        "name": "Tee-Shirt Nike Dri-Fit (Rouge)",
        "taille": "S",
        "etat": "Excellent état",
        "prix": 30.0,
        "poids": 150,
    },
    {
        "item_id": "9",
        "name": "Sweat Nike Tech Fleece (Noir)",
        "taille": "S",
        "etat": "Excellent état",
        "prix": 70.0,
        "poids": 900,
    },
    {
        "item_id": "10",
        "name": "Pantalon Nike Phenom Elite Poche Noir",
        "taille": "S",
        "etat": "8/10",
        "prix": 80.0,
        "poids": 250,
    },
]

url = f"{SUPABASE_URL}/rest/v1/catalog"
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

response = requests.post(url, headers=headers, data=json.dumps(articles))

if response.status_code in [200, 201]:
    print("Succès ! Tous tes articles sont maintenant dans Supabase.")
else:
    print("Erreur :", response.text)
