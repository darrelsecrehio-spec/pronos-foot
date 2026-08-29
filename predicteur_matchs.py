"""
Prédicteur de matchs de football
==================================
Récupère les matchs du jour via l'API API-Football, puis calcule une
probabilité de victoire domicile / nul / victoire extérieur en combinant :
  - la forme générale récente de chaque équipe (moyenne pondérée, 8 derniers matchs)
  - la forme spécifique à domicile / à l'extérieur
  - un léger ajustement basé sur l'historique des confrontations directes
Le tout est converti en probabilités via un modèle de Poisson.

Avant de lancer :
1. Crée un compte gratuit sur https://www.api-football.com/
2. Récupère ta clé API (dashboard > API Key)
3. Remplace API_KEY ci-dessous, ou définis la variable d'environnement API_FOOTBALL_KEY

Installation :
    pip install requests scipy --break-system-packages
"""

import os
import math
import requests
from datetime import date
from scipy.stats import poisson

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("API_FOOTBALL_KEY", "COLLE_TA_CLE_ICI")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Quelques IDs de ligues courants sur API-Football (à ajuster si besoin)
LIGUES = {
    "Ligue 1": 61,
    "Premier League": 39,
    "Liga": 140,
    "Serie A": 135,
    "Bundesliga": 78,
}

SAISON = 2025  # à adapter selon la saison en cours


# ---------------------------------------------------------------------------
# Appels API
# ---------------------------------------------------------------------------

def get_fixtures_du_jour(league_id: int, jour: str | None = None) -> list[dict]:
    """Récupère les matchs prévus pour une ligue à une date donnée (par défaut aujourd'hui)."""
    jour = jour or date.today().isoformat()
    params = {"league": league_id, "season": SAISON, "date": jour}
    r = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("response", [])


def get_derniers_matchs(team_id: int, nb_matchs: int = 8, venue: str | None = None) -> list[dict]:
    """
    Récupère les N derniers matchs joués par une équipe, du plus récent au plus ancien.
    Si venue='home' ou venue='away', ne garde que les matchs joués à domicile / à l'extérieur
    (on demande davantage de matchs à l'API pour compenser le filtrage).
    """
    nb_a_demander = nb_matchs * 3 if venue else nb_matchs
    params = {"team": team_id, "last": nb_a_demander}
    r = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    fixtures = r.json().get("response", [])
    fixtures = sorted(fixtures, key=lambda m: m["fixture"]["date"], reverse=True)

    if venue == "home":
        fixtures = [m for m in fixtures if m["teams"]["home"]["id"] == team_id]
    elif venue == "away":
        fixtures = [m for m in fixtures if m["teams"]["away"]["id"] == team_id]

    return fixtures[:nb_matchs]


def get_confrontations_directes(team1_id: int, team2_id: int, nb_matchs: int = 5) -> list[dict]:
    """Récupère les derniers face-à-face entre deux équipes."""
    params = {"h2h": f"{team1_id}-{team2_id}", "last": nb_matchs}
    r = requests.get(f"{BASE_URL}/fixtures/headtohead", headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("response", [])


def get_stats_equipe(team_id: int, nb_matchs: int = 8, decay: float = 0.85, venue: str | None = None) -> dict:
    """
    Calcule une moyenne pondérée des buts marqués/encaissés sur les derniers matchs,
    en donnant plus de poids aux matchs les plus récents (pondération exponentielle).

    decay=0.85 signifie que chaque match plus ancien pèse 85% du poids du précédent.
    venue='home' -> ne considère que les matchs joués à domicile (idem pour 'away').
    """
    matchs = get_derniers_matchs(team_id, nb_matchs, venue=venue)

    if not matchs:
        return {"buts_marques_moy": 1.0, "buts_encaisses_moy": 1.0}  # valeur neutre par défaut

    total_poids = 0.0
    somme_marques = 0.0
    somme_encaisses = 0.0

    for i, match in enumerate(matchs):
        poids = decay ** i  # i=0 -> match le plus récent -> poids maximal

        est_domicile = match["teams"]["home"]["id"] == team_id
        buts_marques = match["goals"]["home"] if est_domicile else match["goals"]["away"]
        buts_encaisses = match["goals"]["away"] if est_domicile else match["goals"]["home"]

        if buts_marques is None or buts_encaisses is None:
            continue  # match pas encore joué ou données manquantes

        somme_marques += buts_marques * poids
        somme_encaisses += buts_encaisses * poids
        total_poids += poids

    if total_poids == 0:
        return {"buts_marques_moy": 1.0, "buts_encaisses_moy": 1.0}

    return {
        "buts_marques_moy": somme_marques / total_poids,
        "buts_encaisses_moy": somme_encaisses / total_poids,
    }


# ---------------------------------------------------------------------------
# Modèle de prédiction (Poisson)
# ---------------------------------------------------------------------------

def calcule_ajustement_h2h(team1_id: int, team2_id: int, nb_matchs: int = 5) -> float:
    """
    Regarde l'historique des face-à-face et renvoie un facteur d'ajustement
    en faveur de team1 (>1.0 si team1 a dominé historiquement, <1.0 sinon).
    Effet volontairement modéré : le H2H est un indice, pas la donnée principale.
    """
    confrontations = get_confrontations_directes(team1_id, team2_id, nb_matchs)
    if not confrontations:
        return 1.0

    buts_team1, buts_team2 = 0, 0
    for match in confrontations:
        est_home = match["teams"]["home"]["id"] == team1_id
        b1 = match["goals"]["home"] if est_home else match["goals"]["away"]
        b2 = match["goals"]["away"] if est_home else match["goals"]["home"]
        if b1 is None or b2 is None:
            continue
        buts_team1 += b1
        buts_team2 += b2

    if buts_team1 + buts_team2 == 0:
        return 1.0

    ratio = buts_team1 / max(buts_team2, 0.5)
    # On adoucit l'effet : un ratio de 2.0 ne devient qu'un bonus de +10%, pas +100%
    return 1.0 + 0.10 * (min(max(ratio, 0.5), 2.0) - 1.0)


def calcule_expected_goals(team_dom_id: int, team_ext_id: int, nb_matchs: int = 8, decay: float = 0.85) -> tuple[float, float]:
    """
    Estime le nombre de buts attendus pour chaque équipe en combinant :
    - la forme générale récente (tous matchs confondus)
    - la forme spécifique à domicile / à l'extérieur
    - un léger ajustement basé sur l'historique des face-à-face
    """
    forme_generale_dom = get_stats_equipe(team_dom_id, nb_matchs, decay)
    forme_generale_ext = get_stats_equipe(team_ext_id, nb_matchs, decay)
    forme_domicile = get_stats_equipe(team_dom_id, nb_matchs, decay, venue="home")
    forme_exterieur = get_stats_equipe(team_ext_id, nb_matchs, decay, venue="away")

    # 40% forme générale, 60% forme spécifique au lieu de jeu (plus pertinente ici)
    attaque_dom = 0.4 * forme_generale_dom["buts_marques_moy"] + 0.6 * forme_domicile["buts_marques_moy"]
    defense_dom = 0.4 * forme_generale_dom["buts_encaisses_moy"] + 0.6 * forme_domicile["buts_encaisses_moy"]
    attaque_ext = 0.4 * forme_generale_ext["buts_marques_moy"] + 0.6 * forme_exterieur["buts_marques_moy"]
    defense_ext = 0.4 * forme_generale_ext["buts_encaisses_moy"] + 0.6 * forme_exterieur["buts_encaisses_moy"]

    xg_domicile = (attaque_dom + defense_ext) / 2 or 0.1
    xg_exterieur = (attaque_ext + defense_dom) / 2 or 0.1

    ajustement = calcule_ajustement_h2h(team_dom_id, team_ext_id)
    xg_domicile *= ajustement
    xg_exterieur /= ajustement

    return xg_domicile, xg_exterieur


def calcule_probabilites(xg_domicile: float, xg_exterieur: float, max_buts: int = 6) -> dict:
    """
    À partir des xG (expected goals), calcule la probabilité de chaque
    score exact possible, puis agrège en victoire domicile / nul / victoire extérieur.
    """
    p_domicile = 0.0
    p_nul = 0.0
    p_exterieur = 0.0
    meilleur_score = (0, 0)
    meilleure_proba = 0.0

    for buts_dom in range(max_buts + 1):
        for buts_ext in range(max_buts + 1):
            p = poisson.pmf(buts_dom, xg_domicile) * poisson.pmf(buts_ext, xg_exterieur)

            if p > meilleure_proba:
                meilleure_proba = p
                meilleur_score = (buts_dom, buts_ext)

            if buts_dom > buts_ext:
                p_domicile += p
            elif buts_dom == buts_ext:
                p_nul += p
            else:
                p_exterieur += p

    total = p_domicile + p_nul + p_exterieur  # normalisation (arrondis Poisson)
    return {
        "domicile": round(100 * p_domicile / total, 1),
        "nul": round(100 * p_nul / total, 1),
        "exterieur": round(100 * p_exterieur / total, 1),
        "score_probable": f"{meilleur_score[0]}-{meilleur_score[1]}",
    }


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def predire_journee(nom_ligue: str) -> list[dict]:
    """Calcule les prédictions pour tous les matchs du jour d'une ligue et renvoie les résultats sous forme de liste."""
    league_id = LIGUES[nom_ligue]
    fixtures = get_fixtures_du_jour(league_id)

    resultats = []
    for match in fixtures:
        equipe_dom = match["teams"]["home"]
        equipe_ext = match["teams"]["away"]

        xg_dom, xg_ext = calcule_expected_goals(equipe_dom["id"], equipe_ext["id"])
        proba = calcule_probabilites(xg_dom, xg_ext)

        resultats.append({
            "equipe_domicile": equipe_dom["name"],
            "equipe_exterieur": equipe_ext["name"],
            "logo_domicile": equipe_dom.get("logo"),
            "logo_exterieur": equipe_ext.get("logo"),
            "heure": match["fixture"]["date"],
            "probabilites": {
                "domicile": proba["domicile"],
                "nul": proba["nul"],
                "exterieur": proba["exterieur"],
            },
            "score_probable": proba["score_probable"],
        })

    return resultats


if __name__ == "__main__":
    if API_KEY == "COLLE_TA_CLE_ICI":
        print("⚠️  Ajoute ta clé API-Football dans API_KEY ou dans la variable d'environnement API_FOOTBALL_KEY.")
    else:
        for r in predire_journee("Ligue 1"):
            print(f"\n{r['equipe_domicile']} vs {r['equipe_exterieur']}")
            p = r["probabilites"]
            print(f"  Domicile: {p['domicile']}%  |  Nul: {p['nul']}%  |  Extérieur: {p['exterieur']}%")
            print(f"  Score probable: {r['score_probable']}")
