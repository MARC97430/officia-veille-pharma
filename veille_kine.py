#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script GitHub Actions - Veille hebdomadaire Kinesitherapie
Officia - La Reunion

Genere une veille professionnelle pour masseurs-kinesitherapeutes
et l'envoie par email via Brevo.

Version corrigee (octobre 2026) :
- max_tokens augmente (la reponse etait coupee a 4000)
- nettoyage de la reponse de Claude (introduction, ```html, <style>...)
- verification que la reponse est complete avant d'envoyer
- si la reponse est coupee ou vide : alerte par email, PAS d'envoi aux kines
"""

import os
import re
import sys
import requests
from datetime import datetime, timedelta


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = "contact@officiaia.re"
SENDER_NAME = "Officia Veille Kine"

# Liste des destinataires (adresses email)
DESTINATAIRES = os.getenv("KINE_EMAILS", "").split(",")

# Nombre maximum de "mots" (tokens) que Claude a le droit d'ecrire
MAX_TOKENS = 8000


def get_week_dates():
    # La veille part le lundi : elle couvre la SEMAINE ECOULEE
    # (lundi precedent -> dimanche precedent), pas la semaine qui commence.
    today = datetime.now()
    monday = today - timedelta(days=today.weekday() + 7)
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
    elif monday.year != sunday.year:
        # Semaine a cheval sur deux annees (fin decembre / debut janvier)
        date_semaine = (f"{jour_debut} {mois_debut} {annee} au "
                        f"{jour_fin} {mois_fin} {sunday.strftime('%Y')}")
    else:
        date_semaine = f"{jour_debut} {mois_debut} au {jour_fin} {mois_fin} {annee}"
    titre = f"Veille Kinesitherapie - Semaine du {date_semaine}"
    return titre, date_semaine


# ---------------------------------------------------------------------------
# Nettoyage de la reponse de Claude
# ---------------------------------------------------------------------------

# Premiere balise qui marque le debut du vrai contenu
BALISES_DEBUT = re.compile(
    r"<(h1|h2|h3|p|div|section|header|article|ul|ol|table)\b", re.IGNORECASE
)

# Styles ecrits directement dans les balises (les emails n'acceptent pas
# les feuilles de style classiques)
STYLES = {
    "h2": "color:#2563eb; font-size:18px; margin:24px 0 8px; "
          "border-bottom:1px solid #e5e7eb; padding-bottom:4px;",
    "h3": "color:#1f2937; font-size:15px; margin:16px 0 6px;",
    "p": "margin:6px 0; line-height:1.6;",
    "ul": "margin:6px 0; padding-left:20px;",
    "li": "margin-bottom:4px; line-height:1.5;",
}


def extraire_texte_final(content):
    """Garde le texte ecrit APRES la derniere recherche web.

    Avant, Claude ecrit parfois des phrases du type "Je vais chercher...".
    Le vrai resultat arrive apres la derniere recherche.
    """
    dernier_outil = -1
    for i, block in enumerate(content):
        if getattr(block, "type", "") in ("server_tool_use", "web_search_tool_result"):
            dernier_outil = i
    texte = ""
    for block in content[dernier_outil + 1:]:
        if getattr(block, "type", "") == "text":
            texte += block.text
    return texte


def nettoyer_html(texte):
    """Retire tout ce qui ne doit pas apparaitre dans l'email."""
    # 1. Si la reponse contient un bloc ```html ... ```, garder l'interieur
    m = re.search(r"```(?:html)?\s*(.*?)```", texte, re.DOTALL | re.IGNORECASE)
    if m:
        texte = m.group(1)
    else:
        texte = re.sub(r"```(?:html)?", "", texte, flags=re.IGNORECASE)

    # 2. Retirer le code de style, les scripts et l'en-tete technique
    texte = re.sub(r"<style\b.*?</style>", "", texte, flags=re.DOTALL | re.IGNORECASE)
    texte = re.sub(r"<script\b.*?</script>", "", texte, flags=re.DOTALL | re.IGNORECASE)
    texte = re.sub(r"<head\b.*?</head>", "", texte, flags=re.DOTALL | re.IGNORECASE)

    # 3. Garder l'interieur de <body> s'il existe
    m = re.search(r"<body\b[^>]*>(.*?)(?:</body>|$)", texte, re.DOTALL | re.IGNORECASE)
    if m:
        texte = m.group(1)

    # 4. Retirer les balises de structure de page
    texte = re.sub(r"</?(?:html|body|!doctype)[^>]*>", "", texte, flags=re.IGNORECASE)

    # 5. Supprimer l'introduction avant la premiere balise de contenu
    m = BALISES_DEBUT.search(texte)
    if m:
        texte = texte[m.start():]

    # 6. Supprimer les "---" isoles a la fin
    texte = re.sub(r"(?:\s*---\s*)+$", "", texte.strip())
    return texte.strip()


def styliser(html):
    """Ajoute des styles simples aux balises qui n'en ont pas."""
    for balise, style in STYLES.items():
        html = re.sub(rf"<{balise}>", f'<{balise} style="{style}">', html)
    return html


def verifier_contenu(contenu):
    """Refuse un contenu trop court ou sans sections."""
    nb_sections = len(re.findall(r"<h2", contenu, re.IGNORECASE))
    if nb_sections < 3 or len(contenu) < 1500:
        raise RuntimeError(
            f"Contenu insuffisant ({nb_sections} sections, {len(contenu)} caracteres)"
        )


# ---------------------------------------------------------------------------
# Generation avec Claude
# ---------------------------------------------------------------------------

def generate_veille_with_claude(titre, date_semaine):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Tu es un assistant specialise en kinesitherapie et reeducation en France,
avec une attention particuliere aux specificites de La Reunion.

Recherche et synthetise l actualite professionnelle des masseurs-kinesitherapeutes
publiee pendant la semaine ecoulee, du {date_semaine}.
Ne retiens que des informations de cette periode (ou des textes entres en vigueur
pendant cette periode).

Effectue des recherches sur :
1. Actualites de l Ordre des masseurs-kinesitherapeutes (CNOMK)
2. Nouvelles recommandations HAS concernant la kinesitherapie et la reeducation
3. Evolutions de la NGAP (nomenclature des actes) et tarifs conventionnels MK
4. Nouveaux dispositifs medicaux et techniques de reeducation
5. Actualites formation continue / DPC pour les kinesitherapeutes
6. Specificites La Reunion : ARS Ocean Indien, pathologies tropicales, sport en milieu tropical

Structure du contenu, une section h2 par theme :
- Reglementation et convention (NGAP, tarifs, textes officiels)
- Recommandations cliniques (HAS, bonnes pratiques)
- Techniques et innovations (nouveaux dispositifs, nouvelles approches)
- Formation et DPC (opportunites, obligations)
- Actualites profession (Ordre, syndicats, vie professionnelle)
- La Reunion et Ocean Indien (si des informations existent)

REGLES IMPORTANTES :
- Ne rien inventer : ne rapporter que des informations verifiees
- Citer les sources (HAS, CNOMK, Journal Officiel, ARS)
- Vocabulaire professionnel adapte aux MK
- Si peu d actualites sur un theme, ecrire simplement : Aucune information trouvee
  pour cette periode (ne jamais affirmer qu il n existe rien)
- Tarifs et montants : ne donner que des chiffres retrouves dans une source citee,
  sans calcul ni rapprochement personnel
- N ecris jamais que les informations sont verifiees ou officielles
- 3 a 5 actualites maximum par section, phrases courtes
- Longueur totale : environ 800 a 1200 mots
- Terminer par cette note : Cette veille est generee automatiquement par Officia a
  partir de recherches sur le web. Les informations sont a verifier aupres des sources
  citees avant toute decision professionnelle.

FORMAT DE SORTIE (tres important) :
- Reponds UNIQUEMENT avec le contenu HTML, sans phrase d introduction ni de conclusion
- Commence directement par la premiere section en h2 (le titre est deja ajoute ailleurs)
- Pas de balises html, head, body, style ou script, pas de CSS, pas de ```
- Utilise seulement les balises h2, h3, p, ul, li, strong, a (avec href)
- Aucun attribut style ni class
"""

    messages = [{"role": "user", "content": prompt}]
    response = None
    # La recherche web peut mettre la reponse "en pause" : on continue (5 fois maximum)
    for _ in range(5):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=MAX_TOKENS,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
            messages=messages
        )
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    print(f"Fin de reponse : {response.stop_reason} "
          f"({response.usage.output_tokens} tokens ecrits sur {MAX_TOKENS} autorises)")

    # Reponse coupee ou en pause : on n'envoie rien aux kines
    if response.stop_reason != "end_turn":
        raise RuntimeError(
            f"Reponse incomplete (stop_reason={response.stop_reason}). Veille non envoyee."
        )

    contenu_html = nettoyer_html(extraire_texte_final(response.content))
    verifier_contenu(contenu_html)
    return styliser(contenu_html)


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
        <p>La Reunion | contact@officiaia.re</p>
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
