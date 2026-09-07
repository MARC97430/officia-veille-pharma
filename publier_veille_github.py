#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GitHub Actions pour publier la veille pharmaceutique
"""

import requests
import os
import json
from datetime import datetime

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xrmavatowkkpzggrlghr.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_E7Td7w0mhAquUmnEoKUpiA_zHhcasKz")

def generate_veille():
    """Génère la veille de cette semaine"""
    from datetime import datetime, timedelta
    
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    
    jour_debut = monday.strftime("%d")
    jour_fin = sunday.strftime("%d")
    mois = monday.strftime("%b").lower()
    annee = monday.strftime("%Y")
    
    titre = f"Veille Pharmaceutique — Semaine du {jour_debut} {mois} au {jour_fin} {mois} {annee}"
    date_semaine = f"{jour_debut} {mois} au {jour_fin} {mois} {annee}"
    
    contenu_html = """
    <div class="doc-title">Veille Pharmaceutique Hebdomadaire</div>
    <div class="doc-subtitle">Intelligence Artificielle pour Pharmacies d'Officine</div>
    <p><strong>Veille générée automatiquement par OFFICIA.IA</strong></p>
    <p>Consultez la version complète sur votre site pour les détails.</p>
    """
    
    post_facebook = f"""📰 Veille pharmaceutique — {titre}

Votre veille de la semaine est maintenant disponible.
Consultez-la sur notre site pour les actualités en détail.

#PharmacieReunion #OFFICIAIA #VeillePharmacie"""
    
    return {
        "titre": titre,
        "date_semaine": date_semaine,
        "contenu_html": contenu_html,
        "post_facebook": post_facebook
    }

def publish_to_supabase(data):
    """Envoie les données à Supabase"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    url = f"{SUPABASE_URL}/rest/v1/veilles"
    
    try:
        print("⏳ Envoi à Supabase...")
        response = requests.post(url, json=data, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            print("✅ Veille publiée avec succès!")
            return True
        else:
            print(f"❌ Erreur ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return False

def main():
    print("=" * 60)
    print("📋 Publication Automatique - GitHub Actions")
    print("=" * 60)
    
    # Générer la veille
    data = generate_veille()
    print(f"✅ Veille générée: {data['titre']}")
    
    # Publier
    success = publish_to_supabase(data)
    
    print("=" * 60)
    if success:
        print("✅ Succès!")
    else:
        print("❌ Échec - Vérifiez les logs")
    print("=" * 60)

if __name__ == "__main__":
    main()
