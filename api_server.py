"
API de prédictions de matchs
==============================
Petit serveur Flask qui expose predicteur_matchs.py en HTTP/JSON.
C'est le pont entre le moteur de calcul (Python) et l'interface
(web ou app mobile) : l'interface fait une requête GET, le serveur
répond avec les prédictions du jour.

Installation :
    pip install flask flask-cors requests scipy --break-system-packages

Lancement :
    python3 api_server.py
    -> serveur disponible sur http://localhost:5000

Endpoint principal :
    GET /predictions?ligue=Ligue 1
    -> renvoie la liste des matchs du jour avec leurs prédictions

    GET /ligues
    -> renvoie la liste des ligues disponibles
"""

from flask import Flask, jsonify, request
from flask_cors import CORS

from predicteur_matchs import predire_journee, LIGUES, API_KEY

app = Flask(__name__)
CORS(app)  # autorise l'interface (servie depuis un autre port/domaine) à appeler cette API


@app.route("/ligues", methods=["GET"])
def liste_ligues():
    return jsonify(sorted(LIGUES.keys()))


@app.route("/predictions", methods=["GET"])
def predictions():
    nom_ligue = request.args.get("ligue", "Ligue 1")

    if API_KEY == "COLLE_TA_CLE_ICI":
        return jsonify({"erreur": "Clé API-Football manquante. Configure API_FOOTBALL_KEY."}), 500

    if nom_ligue not in LIGUES:
        return jsonify({"erreur": f"Ligue inconnue: {nom_ligue}. Options: {list(LIGUES.keys())}"}), 400

    try:
        resultats = predire_journee(nom_ligue)
    except Exception as e:
        return jsonify({"erreur": str(e)}), 502

    return jsonify({"ligue": nom_ligue, "matchs": resultats})
