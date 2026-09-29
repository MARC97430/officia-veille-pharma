#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GitHub Actions - Veille hebdomadaire Kinesitherapie
Officia - La Reunion

Genere une veille professionnelle pour masseurs-kinesitherapeutes
et l'envoie par email via Brevo.
"""

import os
import sys
import requests
from datetime import datetime, timedelta


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = "contact@officia.re"
SENDER_NAME = "Officia Veille Kine"

# Liste des destinataires (adresses email)
DESTINATAIRES = os.getenv("KINE_EMAILS", "").split(",")


def get_week_dates():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    MOIS_FR = {
        1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "aout",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre"
    }
    jour_debut = monday.strftime("%d")
    jour_fin = sunday.strftime("%d")
    mois_debut = MOIS_FR[monday.month]
    mois_fin = MOIS_FR[sunday.month]
    annee = monday.strftime("%Y")
    if monday.month == sunday.month:
        date_semaine = f"{jour_debut} au {jour_fin} {mois_debut} {annee}"
    else:
        date_semaine = f"{jour_debut} {mois_debut} au {jour_fin} {mois_fin} {annee}"
    titre = f"Veille Kinesitherapie - Semaine du {date_semaine}"
    return titre, date_semaine


def generate_veille_with_claude(titre, date_semaine):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Tu es un assistant specialise en kinesitherapie et reeducation en France,
avec une attention particuliere aux specificites de La Reunion.

Recherche et synthetise l actualite professionnelle des masseurs-kinesitherapeutes
pour la semaine du {date_semaine}.

Effectue des recherches sur :
1. Actualites de l Ordre des masseurs-kinesitherapeutes (CNOMK)
2. Nouvelles recommandations HAS concernant la kinesitherapie et la reeducation
3. Evolutions de la NGAP (nomenclature des actes) et tarifs conventionnels MK
4. Nouveaux dispositifs medicaux et techniques de reeducation
5. Actualites formation continue / DPC pour les kinesitherapeutes
6. Specificites La Reunion : ARS Ocean Indien, pathologies tropicales, sport en milieu tropical

Genere un contenu HTML structure et professionnel avec :
- Un en-tete avec le titre de la veille
- Section Reglementation et convention (NGAP, tarifs, textes officiels)
- Section Recommandations cliniques (HAS, bonnes pratiques)
- Section Techniques et innovations (nouveaux dispositifs, nouvelles approches)
- Section Formation et DPC (opportunites, obligations)
- Section Actualites profession (Ordre, syndicats, vie professionnelle)

REGLES IMPORTANTES :
- Ne rien inventer : ne rapporter que des informations verifiees
- Citer les sources (HAS, CNOMK, Journal Officiel, ARS)
- Vocabulaire professionnel adapte aux MK
- HTML propre avec h2/h3, ul/li, paragraphes
- Si peu d actualites sur un theme, le mentionner brievement plutot que d inventer
- Ajouter une note en bas : Cette veille est generee automatiquement par Officia
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": prompt}]
    )
    contenu_html = ""
    for block in response.content:
        if hasattr(block, 'text'):
            contenu_html += block.text
    if not contenu_html.strip():
        contenu_html = "<p>La veille est en cours de generation.</p>"
    return contenu_html


def send_email(titre, contenu_html, destinataires):
    if not BREVO_API_KEY:
        print("ERREUR: BREVO_API_KEY manquante !")
        return False
    emails_valides = [e.strip() for e in destinataires if e.strip()]
    if not emails_valides:
        print("ERREUR: Aucun destinataire configure (KINE_EMAILS vide) !")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}

    email_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 20px; color: #333;">
    <div style="background: #2563eb; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center;">
        <h1 style="margin: 0; font-size: 22px;">{titre}</h1>
        <p style="margin: 5px 0 0; opacity: 0.9;">Officia - Votre veille professionnelle</p>
    </div>
    <div style="border: 1px solid #e5e7eb; border-top: none; padding: 20px; border-radius: 0 0 8px 8px;">
        {contenu_html}
    </div>
    <div style="text-align: center; padding: 15px; color: #9ca3af; font-size: 12px;">
        <p>Officia - Services IA pour les professionnels de sante</p>
        <p>La Reunion | contact@officia.re</p>
    </div>
</body>
</html>"""

    to_list = [{"email": email} for email in emails_valides]
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": to_list,
        "subject": titre,
        "htmlContent": email_html
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code in [200, 201]:
            print(f"Email envoye a {len(emails_valides)} destinataire(s)")
            for email in emails_valides:
                print(f"  -> {email}")
            return True
        else:
            print(f"Erreur envoi email ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"Erreur reseau envoi email: {e}")
        return False


def send_alert_email(subject, body):
    if not BREVO_API_KEY:
        print(f"ALERTE (pas d email): {subject} - {body}")
        return
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"api-key": BREVO_API_KEY, "Content-Type": "application/json"}
    payload = {
        "sender": {"name": "Officia Veille Kine", "email": SENDER_EMAIL},
        "to": [{"email": SENDER_EMAIL}],
        "subject": subject,
        "htmlContent": f"<p>{body}</p><p><small>Message automatique - GitHub Actions</small></p>"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"Alerte envoyee a {SENDER_EMAIL}")
    except Exception as e:
        print(f"Erreur envoi alerte: {e}")


def main():
    print("=" * 60)
    print("Veille Kinesitherapie - Officia")
    print(f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("ERREUR: ANTHROPIC_API_KEY manquante !")
        sys.exit(1)
    if not BREVO_API_KEY:
        print("ERREUR: BREVO_API_KEY manquante !")
        sys.exit(1)

    emails_valides = [e.strip() for e in DESTINATAIRES if e.strip()]
    if not emails_valides:
        print("ERREUR: Aucun destinataire ! Ajouter le secret KINE_EMAILS dans GitHub.")
        sys.exit(1)

    print("\n[1/2] Generation du contenu avec Claude...")
    titre, date_semaine = get_week_dates()
    try:
        contenu_html = generate_veille_with_claude(titre, date_semaine)
        print(f"Contenu genere : {titre}")
    except Exception as e:
        msg = f"Echec generation veille kine : {e}"
        print(f"ERREUR: {msg}")
        send_alert_email("ALERTE Officia - Veille kine non generee", msg)
        sys.exit(1)

    print("\n[2/2] Envoi par email via Brevo...")
    success = send_email(titre, contenu_html, DESTINATAIRES)

    if success:
        print("\n" + "=" * 60)
        print("SUCCES - Veille kine envoyee par email !")
        print("=" * 60)
    else:
        msg = "La veille kine a ete generee mais l envoi email a echoue."
        print(f"\nECHEC: {msg}")
        send_alert_email("ALERTE Officia - Veille kine non envoyee", msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
