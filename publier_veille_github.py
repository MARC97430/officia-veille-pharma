#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GitHub Actions - Veille pharmaceutique automatique avec Claude AI
Officia - Pharmacies de La Reunion
"""

import os
import requests
from datetime import datetime, timedelta

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xrmavatowkkpzggrlghr.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_E7Td7w0mhAquUmnEoKUpiA_zHhcasKz")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


def get_week_dates():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    MOIS_FR = {1:"janvier",2:"fevrier",3:"mars",4:"avril",5:"mai",6:"juin",
               7:"juillet",8:"aout",9:"septembre",10:"octobre",11:"novembre",12:"decembre"}
    jour_debut = monday.strftime("%d")
    jour_fin = sunday.strftime("%d")
    mois_debut = MOIS_FR[monday.month]
    mois_fin = MOIS_FR[sunday.month]
    annee = monday.strftime("%Y")
    if monday.month == sunday.month:
        date_semaine = f"{jour_debut} au {jour_fin} {mois_debut} {annee}"
    else:
        date_semaine = f"{jour_debut} {mois_debut} au {jour_fin} {mois_fin} {annee}"
    titre = f"Veille Pharmaceutique - Semaine du {date_semaine}"
    return titre, date_semaine, monday


def generate_veille_with_claude():
    import anthropic
    titre, date_semaine, monday = get_week_dates()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Tu es un assistant specialise en pharmacie officine en France, avec attention aux specificites de La Reunion.

Recherche et synthetise l actualite pharmaceutique de la semaine du {date_semaine}.

Effectue des recherches sur :
1. Nouveaux medicaments generiques commercialises en France
2. Retraits de lots et alertes de securite ANSM
3. Changements de prix et remboursement Securite Sociale
4. Nouvelles molecules avec AMM en France
5. Actualites pharmacie officine

Genere un contenu HTML structure avec :
- Alertes securite et retraits de lots
- Nouveaux generiques et molecules
- Changements remboursement / prix
- Actualites officine

REGLES : DCI uniquement (pas de noms de marque), ne rien inventer, vocabulaire en appui du pharmacien, HTML propre h2/h3 ul/li, citer les sources ANSM VIDAL."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
        messages=[{"role": "user", "content": prompt}]
    )
    contenu_html = ""
    for block in response.content:
        if hasattr(block, 'text'):
            contenu_html += block.text
    if not contenu_html.strip():
        contenu_html = "<p>Veille en cours de generation.</p>"
    post_facebook = f"Veille pharmaceutique - {titre}\n\nVotre veille est disponible sur le site Officia.\n\n#PharmacieReunion #Officia"
    return {"titre": titre, "date_semaine": date_semaine, "contenu_html": contenu_html, "post_facebook": post_facebook}


def publish_to_supabase(data):
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json", "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/veilles"
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            print("Veille publiee avec succes !")
            return True
        else:
            print(f"Erreur ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Erreur reseau : {e}")
        return False


def main():
    print("=" * 60)
    print("Veille Pharmaceutique Automatique - Officia")
    print("=" * 60)
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY manquante dans les secrets GitHub !")
        return
    data = generate_veille_with_claude()
    print(f"Contenu genere : {data['titre']}")
    success = publish_to_supabase(data)
    print("Succes !" if success else "Echec - verifier les logs")
    print("=" * 60)

if __name__ == "__main__":
    main()
