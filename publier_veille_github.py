#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GitHub Actions - Veille pharmaceutique automatique avec Claude AI
Officia - Pharmacies de La Reunion

Modifications 29/09/2026 :
- Verification que Supabase repond AVANT de generer la veille (economie de credits API)
- Alerte email via Brevo si la publication echoue
- Exit code 1 en cas d'echec (GitHub Actions detecte l'erreur)

Modifications 06/10/2026 :
- Nettoyage du HTML genere : suppression de la phrase d'introduction et des balises ```html

Modifications 06/10/2026 (2) :
- La veille du lundi couvre la semaine ecoulee (titre, recherche et bandeau "semaine precedente")

Modifications 16/11/2026 (proposition) :
- Prompt : uniquement les informations datees de la semaine ecoulee, date + source obligatoires
- Plus de paragraphe "Reunion" sans source officielle ; plans nationaux (ex. plan hivernal) signales "France hexagonale"
- Pas de consigne inventee ; tous les lots cites ; ajout des textes du Journal officiel
"""

import os
import re
import sys
import requests
from datetime import datetime, timedelta

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dkvumdemuueoqlolohhw.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
ALERT_EMAIL = "contact@officia.re"


def check_supabase_health():
    """Verifie que Supabase repond avant de generer la veille."""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    url = f"{SUPABASE_URL}/rest/v1/Veilles?select=Titre&limit=1"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print("Supabase OK - base de donnees accessible")
            return True
        else:
            print(f"Supabase ERREUR ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Supabase INJOIGNABLE: {e}")
        return False


def send_alert_email(subject, body):
    """Envoie une alerte par email via Brevo (ex-Sendinblue)."""
    if not BREVO_API_KEY:
        print("Pas de BREVO_API_KEY configuree - alerte email impossible")
        print(f"ALERTE: {subject}")
        return False
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "sender": {"name": "Officia Veille", "email": ALERT_EMAIL},
        "to": [{"email": ALERT_EMAIL}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p><p><small>Message automatique - GitHub Actions</small></p>"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"Alerte email envoyee a {ALERT_EMAIL}")
            return True
        else:
            print(f"Erreur envoi email ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False


def get_week_dates():
    # La veille part le lundi : elle couvre la SEMAINE ECOULEE
    # (lundi precedent -> dimanche precedent), pas la semaine qui commence.
    today = datetime.now()
    monday = today - timedelta(days=today.weekday() + 7)
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
    elif monday.year != sunday.year:
        date_semaine = (f"{jour_debut} {mois_debut} {annee} au "
                        f"{jour_fin} {mois_fin} {sunday.strftime('%Y')}")
    else:
        date_semaine = f"{jour_debut} {mois_debut} au {jour_fin} {mois_fin} {annee}"
    titre = f"Veille Pharmaceutique - Semaine du {date_semaine}"
    return titre, date_semaine, monday


def nettoyer_html(texte):
    """Retire les phrases d'introduction et les balises ```html que l'IA ajoute parfois."""
    m = re.search(r"```(?:html)?\s*(.*?)```", texte, re.DOTALL | re.IGNORECASE)
    if m:
        texte = m.group(1)
    else:
        texte = re.sub(r"```(?:html)?", "", texte, flags=re.IGNORECASE)
    debut = texte.find("<")
    if debut > 0:
        texte = texte[debut:]
    return texte.strip()


def generate_veille_with_claude():
    import anthropic
    titre, date_semaine, monday = get_week_dates()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Tu es un assistant specialise en pharmacie officine en France, avec attention aux specificites de La Reunion.

Recherche et synthetise l actualite pharmaceutique PUBLIEE OFFICIELLEMENT pendant la semaine ecoulee, du {date_semaine} (du lundi au dimanche inclus).

Effectue des recherches sur :
1. Retraits de lots et alertes de securite ANSM
2. Arretes, decrets et textes parus au Journal officiel concernant les pharmacies, les medicaments ou leur remboursement
3. Nouveaux medicaments generiques et nouvelles molecules avec AMM en France
4. Changements de prix et de remboursement Securite Sociale
5. Actualites pharmacie officine

REGLES DE FIABILITE (prioritaires sur tout le reste) :
- PERIODE : ne retiens QUE les informations dont la date de publication officielle est comprise dans la semaine du {date_semaine}. Une information publiee avant cette semaine (meme importante) est ECARTEE, sauf si un fait nouveau est survenu pendant la semaine ; dans ce cas, ne decris que le fait nouveau.
- DATE ET SOURCE : chaque element doit indiquer sa date de publication et sa source (ANSM, Journal officiel, VIDAL, ARS La Reunion...). Si tu ne trouves pas la date ou la source, n ecris pas l element.
- NE RIEN INVENTER : ne mentionne aucune consigne (cesser la delivrance, contacter les patients, rappeler tous les lots...) qui ne figure pas explicitement dans la source. Cite tous les lots concernes (pas seulement un), avec leur numero.
- LA REUNION : n ecris AUCUN paragraphe "Reunion", "DROM" ou "outre-mer" sauf si une source officielle (ANSM, ARS La Reunion, ministere) le mentionne explicitement pour La Reunion ou les DROM ; dans ce cas, cite-la. Ne fais aucune supposition locale (stocks, commandes, rétrocession...).
- PLANS ET CAMPAGNES NATIONAUX (ex : plan hivernal, campagnes de vaccination) : ils visent en general la France hexagonale. Ne les mentionne que s ils sont nouveaux cette semaine ET precise "France hexagonale" sauf si la source indique que La Reunion est concernee. La Reunion est dans l hemisphere sud : en novembre c est le printemps (l hiver austral va de juin a aout). Ne presente JAMAIS un plan hivernal, une epidemie hivernale (grippe, bronchiolite, VRS) ou un conseil de stock lie a l hiver comme concernant La Reunion, sauf source officielle precisant le contraire.
- VOCABULAIRE : DCI uniquement (pas de noms de marque, sauf dans une alerte de lot ou le nom commercial est necessaire pour identifier le produit), vocabulaire en appui du pharmacien, jamais de formulation qui engage a decider a sa place.
- Si une rubrique n a aucune information verifiee cette semaine, ecris : "Aucune actualite verifiee cette semaine."

Genere un contenu HTML structure avec :
- Alertes securite et retraits de lots
- Textes officiels et changements remboursement / prix
- Nouveaux generiques et molecules
- Actualites officine

FORMAT : HTML propre h2/h3 ul/li.
FORMAT DE SORTIE : reponds UNIQUEMENT avec le code HTML, sans phrase d introduction, sans conclusion et sans balises de code (pas de ```)."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
        messages=[{"role": "user", "content": prompt}]
    )
    contenu_html = ""
    for block in response.content:
        if hasattr(block, 'text'):
            contenu_html += block.text
    contenu_html = nettoyer_html(contenu_html)
    if not contenu_html.strip():
        contenu_html = "<p>Veille en cours de generation.</p>"
    bandeau = (f"<p><em>Actualité de la semaine précédente : du {date_semaine}. "
               "Informations issues de recherches web, à vérifier auprès des sources officielles "
               "(ANSM, VIDAL).</em></p>\n")
    contenu_html = bandeau + contenu_html
    post_facebook = f"Veille pharmaceutique - {titre}\n\nVotre veille est disponible sur le site Officia.\n\n#PharmacieReunion #Officia"
    return {"Titre": titre, "date_semaine": date_semaine, "contenu_html": contenu_html, "post_facebook": post_facebook}


def publish_to_supabase(data):
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    url = f"{SUPABASE_URL}/rest/v1/Veilles"
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            print("Veille publiee avec succes !")
            return True
        else:
            print(f"Erreur publication ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Erreur reseau : {e}")
        return False


def main():
    print("=" * 60)
    print("Veille Pharmaceutique Automatique - Officia")
    print(f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    # Verification des cles
    if not ANTHROPIC_API_KEY:
        print("ERREUR: ANTHROPIC_API_KEY manquante dans les secrets GitHub !")
        sys.exit(1)

    if not SUPABASE_KEY:
        print("ERREUR: SUPABASE_KEY manquante dans les secrets GitHub !")
        sys.exit(1)

    # Etape 1 : Verifier que Supabase repond
    print("\n[1/3] Verification Supabase...")
    if not check_supabase_health():
        msg = ("La veille n'a PAS ete publiee : Supabase ne repond pas. "
               "Le projet est peut-etre en pause (plan gratuit). "
               "Va sur https://supabase.com/dashboard pour le reactiver.")
        print(f"ECHEC: {msg}")
        send_alert_email(
            "ALERTE Officia - Veille non publiee (Supabase en panne)",
            msg
        )
        sys.exit(1)

    # Etape 2 : Generer la veille avec Claude
    print("\n[2/3] Generation du contenu avec Claude...")
    data = generate_veille_with_claude()
    print(f"Contenu genere : {data['Titre']}")

    # Etape 3 : Publier dans Supabase
    print("\n[3/3] Publication dans Supabase...")
    success = publish_to_supabase(data)

    if success:
        print("\n" + "=" * 60)
        print("SUCCES - Veille publiee sur le site !")
        print("=" * 60)
    else:
        msg = ("La veille a ete generee mais la publication dans Supabase a echoue. "
               "Verifier les logs GitHub Actions pour plus de details.")
        print(f"\nECHEC: {msg}")
        send_alert_email(
            "ALERTE Officia - Veille generee mais non publiee",
            msg
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
