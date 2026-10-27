"""
app.py
------
Application Flask du cabinet de neurologie (voir SPECIFICATION.md).

Pages disponibles :
    /patients      -> liste, création, fiche et modification des patients
    /rendez-vous   -> liste, création, modification et suppression des rendez-vous
    /consultations -> liste filtrable, saisie, détail et modification des comptes-rendus

Tout le HTML est construit ici (aucun template externe). Chaque requête ouvre
sa propre connexion SQLite, exécute des requêtes paramétrées et la referme.

Pour la lancer (depuis la racine du projet, avec (venv) actif) :
    python3 app.py
"""

import re
import sqlite3
from contextlib import closing
from datetime import date, datetime

from flask import Flask, abort, redirect, request
from markupsafe import escape

app = Flask(__name__)


# ------------------------------------------------------------------
# Constantes
# ------------------------------------------------------------------

PAGES = [
    ("/patients", "Patients"),
    ("/rendez-vous", "Rendez-vous"),
    ("/consultations", "Consultations"),
]

CHAMPS_PATIENT = [
    "nom", "prenom", "date_naissance", "sexe",
    "telephone", "email", "adresse", "antecedents",
]
SEXES = ["", "F", "M", "Autre"]

CHAMPS_RDV = ["patient_id", "date_rdv", "heure_rdv", "motif", "statut"]
STATUTS_RDV = ["prévu", "honoré", "annulé"]

CHAMPS_CONSULTATION = [
    "patient_id", "rendez_vous_id", "date_consultation", "motif",
    "observations", "diagnostic", "traitement", "medecin",
]

# Plus grand entier accepté par SQLite : au-delà, sqlite3 lève OverflowError.
ID_MAX = 2**63 - 1

CSS = """
body { font-family: sans-serif; margin: 0; color: #222; }
nav { background: #eee; padding: 10px 20px; border-bottom: 1px solid #ccc; }
main { padding: 10px 20px 30px; }
.bouton { display: inline-block; padding: 6px 12px; margin: 2px; border: none;
          border-radius: 4px; background: #0066cc; color: #fff; font-size: 14px;
          text-decoration: none; cursor: pointer; }
nav .bouton { background: #555; }
nav .bouton.actif { background: #222; font-weight: bold; }
.bouton.danger { background: #c0392b; }
form.en-ligne { display: inline; margin: 0; }
table { border-collapse: collapse; margin: 10px 0; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f4f4f4; }
label { display: block; margin-top: 10px; font-weight: bold; }
input, select, textarea { font-size: 14px; padding: 4px; min-width: 300px; }
textarea { min-height: 70px; }
.erreur { color: #b00020; font-weight: bold; }
.texte { white-space: pre-wrap; }
"""


# ------------------------------------------------------------------
# Base de données et utilitaires
# ------------------------------------------------------------------

def se_connecter_a_la_base():
    connexion = sqlite3.connect("database/cabinet.db")
    connexion.row_factory = sqlite3.Row
    return connexion


def entier(texte):
    """Identifiant strictement positif représentable par SQLite, sinon None."""
    if not texte or not re.fullmatch(r"[0-9]+", texte):
        return None
    valeur = int(texte)
    return valeur if 0 < valeur <= ID_MAX else None


def date_valide(texte):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texte):
        return False
    try:
        datetime.strptime(texte, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def heure_valide(texte):
    if not re.fullmatch(r"\d{2}:\d{2}", texte):
        return False
    try:
        datetime.strptime(texte, "%H:%M")
    except ValueError:
        return False
    return True


def chercher_ou_404(connexion, requete, identifiant):
    """Exécute `requete` (un seul paramètre : l'identifiant) ou renvoie 404."""
    if identifiant > ID_MAX:
        abort(404)
    ligne = connexion.execute(requete, (identifiant,)).fetchone()
    if ligne is None:
        abort(404)
    return ligne


def patient_existe(connexion, patient_id):
    identifiant = entier(patient_id)
    if identifiant is None:
        return False
    return connexion.execute(
        "SELECT 1 FROM patients WHERE id = ?", (identifiant,)
    ).fetchone() is not None


def liste_des_patients(connexion):
    return connexion.execute(
        "SELECT id, nom, prenom FROM patients ORDER BY nom, prenom"
    ).fetchall()


def lire_formulaire(champs):
    return {champ: request.form.get(champ, "").strip() for champ in champs}


def valeurs_depuis_ligne(ligne, champs):
    return {champ: "" if ligne[champ] is None else str(ligne[champ]) for champ in champs}


def ou_null(valeurs, champs):
    """Valeurs à enregistrer, dans l'ordre de `champs` ; chaîne vide -> NULL."""
    return [valeurs[champ] or None for champ in champs]


def afficher(valeur):
    """Valeur échappée, ou « — » si elle est vide."""
    if valeur is None or valeur == "":
        return "—"
    return str(escape(valeur))


# ------------------------------------------------------------------
# Rendu HTML commun
# ------------------------------------------------------------------

def menu():
    liens = ""
    for adresse, libelle in PAGES:
        actif = request.path == adresse or request.path.startswith(adresse + "/")
        classe = "bouton actif" if actif else "bouton"
        liens += f'<a class="{classe}" href="{adresse}">{libelle}</a> '
    return f"<nav>{liens}</nav>"


def page(titre, contenu):
    titre = escape(titre)
    return (
        "<!DOCTYPE html>"
        '<html lang="fr"><head><meta charset="utf-8">'
        f"<title>{titre} — Cabinet de neurologie</title>"
        f"<style>{CSS}</style></head>"
        f"<body>{menu()}<main><h1>{titre}</h1>{contenu}</main></body></html>"
    )


def bouton(adresse, libelle):
    return f'<a class="bouton" href="{adresse}">{libelle}</a>'


def message_erreur(erreur):
    return f'<p class="erreur">{escape(erreur)}</p>' if erreur else ""


def champ_saisie(nom, libelle, valeurs, type_="text", requis=False):
    obligatoire = " required" if requis else ""
    return (
        f'<label for="{nom}">{libelle}</label>'
        f'<input type="{type_}" id="{nom}" name="{nom}" '
        f'value="{escape(valeurs.get(nom, ""))}"{obligatoire}>'
    )


def champ_texte_long(nom, libelle, valeurs):
    return (
        f'<label for="{nom}">{libelle}</label>'
        f'<textarea id="{nom}" name="{nom}">{escape(valeurs.get(nom, ""))}</textarea>'
    )


def champ_liste(nom, libelle, options, selection, requis=False):
    """`options` : liste de couples (valeur, libellé déjà échappé)."""
    obligatoire = " required" if requis else ""
    html = f'<label for="{nom}">{libelle}</label><select id="{nom}" name="{nom}"{obligatoire}>'
    for valeur, texte in options:
        choisi = " selected" if str(valeur) == selection else ""
        html += f'<option value="{escape(valeur)}"{choisi}>{texte}</option>'
    return html + "</select>"


def options_patients(patients):
    options = [("", "— Choisir un patient —")]
    for p in patients:
        options.append((p["id"], f"{escape(p['nom'])} {escape(p['prenom'])}"))
    return options


def formulaire(action, contenu, libelle_bouton, erreur):
    return (
        message_erreur(erreur)
        + f'<form method="post" action="{action}">{contenu}'
        + f'<p><button class="bouton" type="submit">{libelle_bouton}</button></p></form>'
    )


# ------------------------------------------------------------------
# Patients
# ------------------------------------------------------------------

def valeurs_depuis_formulaire_patient():
    return lire_formulaire(CHAMPS_PATIENT)


def erreur_formulaire_patient(valeurs):
    if not valeurs["nom"] or not valeurs["prenom"]:
        return "Le nom et le prénom sont obligatoires."
    if valeurs["date_naissance"] and not date_valide(valeurs["date_naissance"]):
        return "La date de naissance n'est pas valide."
    if valeurs["sexe"] not in SEXES:
        return "La valeur choisie pour le sexe n'est pas valide."
    return None


def formulaire_patient(action, valeurs, libelle_bouton, erreur=None):
    sexes = [("", "—"), ("F", "F"), ("M", "M"), ("Autre", "Autre")]
    contenu = (
        champ_saisie("nom", "Nom", valeurs, requis=True)
        + champ_saisie("prenom", "Prénom", valeurs, requis=True)
        + champ_saisie("date_naissance", "Date de naissance", valeurs, type_="date")
        + champ_liste("sexe", "Sexe", sexes, valeurs.get("sexe", ""))
        + champ_saisie("telephone", "Téléphone", valeurs, type_="tel")
        + champ_saisie("email", "Email", valeurs, type_="email")
        + champ_saisie("adresse", "Adresse", valeurs)
        + champ_texte_long("antecedents", "Antécédents", valeurs)
    )
    return formulaire(action, contenu, libelle_bouton, erreur)


@app.route("/")
def accueil():
    return redirect("/patients")


@app.route("/patients")
def liste_patients():
    with closing(se_connecter_a_la_base()) as connexion:
        patients = connexion.execute(
            "SELECT id, nom, prenom, date_naissance FROM patients ORDER BY nom, prenom"
        ).fetchall()

    html = f"<p>{bouton('/patients/nouveau', 'Ajouter un patient')}</p>"
    if not patients:
        return page("Patients", html + "<p>Aucun patient enregistré.</p>")

    html += "<table><tr><th>Nom</th><th>Prénom</th><th>Date de naissance</th></tr>"
    for p in patients:
        lien = f"/patients/{p['id']}"
        html += (
            f'<tr><td><a href="{lien}">{escape(p["nom"])}</a></td>'
            f'<td><a href="{lien}">{escape(p["prenom"])}</a></td>'
            f"<td>{afficher(p['date_naissance'])}</td></tr>"
        )
    html += "</table>"
    return page("Patients", html)


@app.route("/patients/nouveau", methods=["GET", "POST"])
def nouveau_patient():
    valeurs = {champ: "" for champ in CHAMPS_PATIENT}
    erreur = None
    if request.method == "POST":
        valeurs = valeurs_depuis_formulaire_patient()
        erreur = erreur_formulaire_patient(valeurs)
        if erreur is None:
            with closing(se_connecter_a_la_base()) as connexion:
                curseur = connexion.execute(
                    f"INSERT INTO patients ({', '.join(CHAMPS_PATIENT)}) "
                    f"VALUES ({', '.join('?' * len(CHAMPS_PATIENT))})",
                    ou_null(valeurs, CHAMPS_PATIENT),
                )
                connexion.commit()
                return redirect(f"/patients/{curseur.lastrowid}")

    return page(
        "Nouveau patient",
        formulaire_patient("/patients/nouveau", valeurs, "Enregistrer", erreur),
    )


@app.route("/patients/<int:patient_id>")
def fiche_patient(patient_id):
    with closing(se_connecter_a_la_base()) as connexion:
        patient = chercher_ou_404(
            connexion, "SELECT * FROM patients WHERE id = ?", patient_id
        )
        rendez_vous = connexion.execute(
            "SELECT id, date_rdv, heure_rdv, motif, statut FROM rendez_vous "
            "WHERE patient_id = ? ORDER BY date_rdv, heure_rdv",
            (patient_id,),
        ).fetchall()
        comptes_rendus = connexion.execute(
            "SELECT id, date_consultation, medecin, motif FROM consultations "
            "WHERE patient_id = ? ORDER BY date_consultation, id",
            (patient_id,),
        ).fetchall()

    html = (
        "<table>"
        f"<tr><th>Date de naissance</th><td>{afficher(patient['date_naissance'])}</td></tr>"
        f"<tr><th>Téléphone</th><td>{afficher(patient['telephone'])}</td></tr>"
        f"<tr><th>Email</th><td>{afficher(patient['email'])}</td></tr>"
        "</table><p>"
        + bouton(f"/rendez-vous/nouveau?patient_id={patient_id}", "Prendre un rendez-vous")
        + bouton(f"/patients/{patient_id}/modifier", "Modifier le patient")
        + bouton(f"/consultations/nouveau?patient_id={patient_id}", "Rédiger un compte-rendu")
        + "</p><h2>Rendez-vous</h2>"
    )

    if rendez_vous:
        html += "<table><tr><th>Date</th><th>Heure</th><th>Motif</th><th>Statut</th><th>Actions</th></tr>"
        for rdv in rendez_vous:
            html += (
                f"<tr><td>{afficher(rdv['date_rdv'])}</td><td>{afficher(rdv['heure_rdv'])}</td>"
                f"<td>{afficher(rdv['motif'])}</td><td>{afficher(rdv['statut'])}</td>"
                f"<td>{boutons_rdv(rdv['id'])}</td></tr>"
            )
        html += "</table>"
    else:
        html += "<p>Aucun rendez-vous pour ce patient.</p>"

    html += "<h2>Comptes-rendus de consultation</h2>"
    if comptes_rendus:
        html += "<table><tr><th>Date</th><th>Médecin</th><th>Motif</th><th>Actions</th></tr>"
        for cr in comptes_rendus:
            html += (
                f"<tr><td>{afficher(cr['date_consultation'])}</td>"
                f"<td>{afficher(cr['medecin'])}</td><td>{afficher(cr['motif'])}</td>"
                f"<td>{bouton(f'/consultations/{cr['id']}', 'Voir')}"
                f"{bouton(f'/consultations/{cr['id']}/modifier', 'Modifier')}</td></tr>"
            )
        html += "</table>"
    else:
        html += "<p>Aucun compte-rendu de consultation pour ce patient.</p>"

    return page(f"{patient['prenom']} {patient['nom']}", html)


@app.route("/patients/<int:patient_id>/modifier", methods=["GET", "POST"])
def modifier_patient(patient_id):
    with closing(se_connecter_a_la_base()) as connexion:
        patient = chercher_ou_404(
            connexion, "SELECT * FROM patients WHERE id = ?", patient_id
        )
        valeurs = valeurs_depuis_ligne(patient, CHAMPS_PATIENT)
        erreur = None
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_patient()
            erreur = erreur_formulaire_patient(valeurs)
            if erreur is None:
                connexion.execute(
                    f"UPDATE patients SET {', '.join(c + ' = ?' for c in CHAMPS_PATIENT)} "
                    "WHERE id = ?",
                    [*ou_null(valeurs, CHAMPS_PATIENT), patient_id],
                )
                connexion.commit()
                return redirect(f"/patients/{patient_id}")

    return page(
        f"Modifier {patient['prenom']} {patient['nom']}",
        formulaire_patient(f"/patients/{patient_id}/modifier", valeurs, "Enregistrer", erreur),
    )


# ------------------------------------------------------------------
# Rendez-vous
# ------------------------------------------------------------------

def valider_rendez_vous(connexion, valeurs, edition):
    if not patient_existe(connexion, valeurs["patient_id"]):
        return "Merci de choisir un patient."
    if not date_valide(valeurs["date_rdv"]) or not heure_valide(valeurs["heure_rdv"]):
        return "Merci de saisir une date et une heure valides."
    if edition and valeurs["statut"] not in STATUTS_RDV:
        return "Le statut choisi n'est pas valide."
    return None


def formulaire_rendez_vous(action, valeurs, patients, edition, libelle_bouton, erreur=None):
    contenu = (
        champ_liste("patient_id", "Patient", options_patients(patients),
                    valeurs["patient_id"], requis=True)
        + champ_saisie("date_rdv", "Date", valeurs, type_="date", requis=True)
        + champ_saisie("heure_rdv", "Heure", valeurs, type_="time", requis=True)
        + champ_saisie("motif", "Motif", valeurs)
    )
    if edition:
        contenu += champ_liste(
            "statut", "Statut", [(s, s) for s in STATUTS_RDV], valeurs["statut"]
        )
    return formulaire(action, contenu, libelle_bouton, erreur)


def boutons_rdv(rdv_id):
    return (
        bouton(f"/rendez-vous/{rdv_id}/modifier", "Modifier")
        + f'<form class="en-ligne" method="post" action="/rendez-vous/{rdv_id}/supprimer" '
        "onsubmit=\"return confirm('Supprimer ce rendez-vous ?');\">"
        '<button class="bouton danger" type="submit">Supprimer</button></form>'
    )


@app.route("/rendez-vous")
def liste_rendez_vous():
    with closing(se_connecter_a_la_base()) as connexion:
        rendez_vous = connexion.execute("""
            SELECT r.id, r.patient_id, r.date_rdv, r.heure_rdv, r.motif, r.statut,
                   p.nom, p.prenom
            FROM rendez_vous AS r
            JOIN patients AS p ON r.patient_id = p.id
            ORDER BY r.date_rdv, r.heure_rdv
        """).fetchall()

    html = f"<p>{bouton('/rendez-vous/nouveau', 'Nouveau rendez-vous')}</p>"
    if not rendez_vous:
        return page("Rendez-vous", html + "<p>Aucun rendez-vous enregistré.</p>")

    html += (
        "<table><tr><th>Date</th><th>Heure</th><th>Patient</th>"
        "<th>Motif</th><th>Statut</th><th>Actions</th></tr>"
    )
    for rdv in rendez_vous:
        html += (
            f"<tr><td>{afficher(rdv['date_rdv'])}</td><td>{afficher(rdv['heure_rdv'])}</td>"
            f'<td><a href="/patients/{rdv["patient_id"]}">'
            f"{escape(rdv['prenom'])} {escape(rdv['nom'])}</a></td>"
            f"<td>{afficher(rdv['motif'])}</td><td>{afficher(rdv['statut'])}</td>"
            f"<td>{boutons_rdv(rdv['id'])}</td></tr>"
        )
    html += "</table>"
    return page("Rendez-vous", html)


@app.route("/rendez-vous/nouveau", methods=["GET", "POST"])
def nouveau_rendez_vous():
    with closing(se_connecter_a_la_base()) as connexion:
        valeurs = {champ: "" for champ in CHAMPS_RDV}
        valeurs["patient_id"] = request.args.get("patient_id", "")
        erreur = None
        if request.method == "POST":
            valeurs = lire_formulaire(CHAMPS_RDV)
            valeurs["statut"] = "prévu"
            erreur = valider_rendez_vous(connexion, valeurs, edition=False)
            if erreur is None:
                valeurs["patient_id"] = str(entier(valeurs["patient_id"]))
                connexion.execute(
                    f"INSERT INTO rendez_vous ({', '.join(CHAMPS_RDV)}) "
                    f"VALUES ({', '.join('?' * len(CHAMPS_RDV))})",
                    ou_null(valeurs, CHAMPS_RDV),
                )
                connexion.commit()
                return redirect(f"/patients/{valeurs['patient_id']}")
        patients = liste_des_patients(connexion)

    return page(
        "Nouveau rendez-vous",
        formulaire_rendez_vous("/rendez-vous/nouveau", valeurs, patients,
                               False, "Enregistrer", erreur),
    )


@app.route("/rendez-vous/<int:rdv_id>/modifier", methods=["GET", "POST"])
def modifier_rendez_vous(rdv_id):
    with closing(se_connecter_a_la_base()) as connexion:
        rdv = chercher_ou_404(connexion, "SELECT * FROM rendez_vous WHERE id = ?", rdv_id)
        valeurs = valeurs_depuis_ligne(rdv, CHAMPS_RDV)
        erreur = None
        if request.method == "POST":
            valeurs = lire_formulaire(CHAMPS_RDV)
            erreur = valider_rendez_vous(connexion, valeurs, edition=True)
            if erreur is None:
                valeurs["patient_id"] = str(entier(valeurs["patient_id"]))
                connexion.execute(
                    f"UPDATE rendez_vous SET {', '.join(c + ' = ?' for c in CHAMPS_RDV)} "
                    "WHERE id = ?",
                    [*ou_null(valeurs, CHAMPS_RDV), rdv_id],
                )
                connexion.commit()
                return redirect("/rendez-vous")
        patients = liste_des_patients(connexion)

    return page(
        "Modifier le rendez-vous",
        formulaire_rendez_vous(f"/rendez-vous/{rdv_id}/modifier", valeurs, patients,
                               True, "Enregistrer", erreur),
    )


@app.route("/rendez-vous/<int:rdv_id>/supprimer", methods=["POST"])
def supprimer_rendez_vous(rdv_id):
    with closing(se_connecter_a_la_base()) as connexion:
        chercher_ou_404(connexion, "SELECT id FROM rendez_vous WHERE id = ?", rdv_id)
        # Les comptes-rendus liés sont conservés, simplement détachés du RDV.
        connexion.execute(
            "UPDATE consultations SET rendez_vous_id = NULL WHERE rendez_vous_id = ?",
            (rdv_id,),
        )
        connexion.execute("DELETE FROM rendez_vous WHERE id = ?", (rdv_id,))
        connexion.commit()
    return redirect("/rendez-vous")


# ------------------------------------------------------------------
# Comptes-rendus de consultation
# ------------------------------------------------------------------

def patients_et_rendez_vous(connexion):
    patients = liste_des_patients(connexion)
    rendez_vous = connexion.execute("""
        SELECT r.id, r.date_rdv, r.heure_rdv, r.motif, p.nom, p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON r.patient_id = p.id
        ORDER BY r.date_rdv, r.heure_rdv
    """).fetchall()
    return patients, rendez_vous


def valider_consultation(connexion, valeurs):
    if not patient_existe(connexion, valeurs["patient_id"]):
        return "Merci de choisir un patient."
    if valeurs["rendez_vous_id"]:
        rdv_id = entier(valeurs["rendez_vous_id"])
        rdv = None
        if rdv_id is not None:
            rdv = connexion.execute(
                "SELECT patient_id FROM rendez_vous WHERE id = ?", (rdv_id,)
            ).fetchone()
        if rdv is None:
            return "Le rendez-vous choisi n'existe pas."
        if rdv["patient_id"] != entier(valeurs["patient_id"]):
            return "Le rendez-vous choisi n'appartient pas à ce patient."
    if not date_valide(valeurs["date_consultation"]):
        return "Merci de saisir une date valide."
    return None


def normaliser_consultation(valeurs):
    """Identifiants validés convertis en forme canonique avant écriture."""
    valeurs["patient_id"] = str(entier(valeurs["patient_id"]))
    if valeurs["rendez_vous_id"]:
        valeurs["rendez_vous_id"] = str(entier(valeurs["rendez_vous_id"]))


def formulaire_consultation(action, valeurs, patients, rendez_vous, libelle_bouton, erreur=None):
    options_rdv = [("", "— Aucun —")]
    for r in rendez_vous:
        libelle = f"{escape(r['date_rdv'])} {escape(r['heure_rdv'])} — {escape(r['prenom'])} {escape(r['nom'])}"
        if r["motif"]:
            libelle += f" — {escape(r['motif'])}"
        options_rdv.append((r["id"], libelle))

    contenu = (
        champ_liste("patient_id", "Patient", options_patients(patients),
                    valeurs["patient_id"], requis=True)
        + champ_liste("rendez_vous_id", "Rendez-vous lié", options_rdv, valeurs["rendez_vous_id"])
        + champ_saisie("date_consultation", "Date", valeurs, type_="date", requis=True)
        + champ_saisie("medecin", "Médecin", valeurs)
        + champ_saisie("motif", "Motif", valeurs)
        + champ_texte_long("observations", "Observations", valeurs)
        + champ_texte_long("diagnostic", "Diagnostic", valeurs)
        + champ_texte_long("traitement", "Traitement", valeurs)
    )
    return formulaire(action, contenu, libelle_bouton, erreur)


@app.route("/consultations")
def liste_consultations():
    filtre = request.args.get("medecin", "")
    with closing(se_connecter_a_la_base()) as connexion:
        medecins = [
            ligne["medecin"] for ligne in connexion.execute(
                "SELECT DISTINCT medecin FROM consultations "
                "WHERE medecin IS NOT NULL AND medecin <> '' ORDER BY medecin"
            )
        ]
        requete = """
            SELECT c.id, c.date_consultation, c.medecin, p.nom, p.prenom
            FROM consultations AS c
            JOIN patients AS p ON c.patient_id = p.id
        """
        parametres = []
        if filtre:
            requete += " WHERE c.medecin = ?"
            parametres.append(filtre)
        requete += " ORDER BY c.date_consultation, c.id"
        comptes_rendus = connexion.execute(requete, parametres).fetchall()

    # Un médecin demandé mais absent de la liste reste sélectionné.
    if filtre and filtre not in medecins:
        medecins.append(filtre)
    options = [("", "Tous les médecins")] + [(m, escape(m)) for m in medecins]

    html = (
        f"<p>{bouton('/consultations/nouveau', 'Rédiger un compte-rendu')}</p>"
        '<form method="get" action="/consultations">'
        + champ_liste("medecin", "Médecin", options, filtre)
        + ' <button class="bouton" type="submit">Filtrer</button></form>'
    )

    if not comptes_rendus:
        message = "Aucun compte-rendu pour ce médecin." if filtre else "Aucun compte-rendu enregistré."
        return page("Comptes-rendus de consultation", html + f"<p>{message}</p>")

    html += "<table><tr><th>Patient</th><th>Médecin</th><th>Date</th></tr>"
    for cr in comptes_rendus:
        html += (
            f'<tr><td><a href="/consultations/{cr["id"]}">'
            f"{escape(cr['prenom'])} {escape(cr['nom'])}</a></td>"
            f"<td>{afficher(cr['medecin'])}</td>"
            f"<td>{afficher(cr['date_consultation'])}</td></tr>"
        )
    html += "</table>"
    return page("Comptes-rendus de consultation", html)


@app.route("/consultations/nouveau", methods=["GET", "POST"])
def nouveau_compte_rendu():
    with closing(se_connecter_a_la_base()) as connexion:
        valeurs = {champ: "" for champ in CHAMPS_CONSULTATION}
        valeurs["patient_id"] = request.args.get("patient_id", "")
        valeurs["rendez_vous_id"] = request.args.get("rendez_vous_id", "")
        valeurs["date_consultation"] = date.today().isoformat()
        erreur = None
        if request.method == "POST":
            valeurs = lire_formulaire(CHAMPS_CONSULTATION)
            erreur = valider_consultation(connexion, valeurs)
            if erreur is None:
                normaliser_consultation(valeurs)
                connexion.execute(
                    f"INSERT INTO consultations ({', '.join(CHAMPS_CONSULTATION)}) "
                    f"VALUES ({', '.join('?' * len(CHAMPS_CONSULTATION))})",
                    ou_null(valeurs, CHAMPS_CONSULTATION),
                )
                connexion.commit()
                return redirect("/consultations")
        patients, rendez_vous = patients_et_rendez_vous(connexion)

    return page(
        "Nouveau compte-rendu",
        formulaire_consultation("/consultations/nouveau", valeurs, patients,
                                rendez_vous, "Enregistrer", erreur),
    )


@app.route("/consultations/<int:consultation_id>")
def detail_consultation(consultation_id):
    with closing(se_connecter_a_la_base()) as connexion:
        cr = chercher_ou_404(connexion, """
            SELECT c.*, p.nom, p.prenom,
                   r.date_rdv, r.heure_rdv, r.motif AS motif_rdv
            FROM consultations AS c
            JOIN patients AS p ON c.patient_id = p.id
            LEFT JOIN rendez_vous AS r ON c.rendez_vous_id = r.id
            WHERE c.id = ?
        """, consultation_id)

    rdv = "—"
    if cr["date_rdv"] is not None:
        rdv = f"{escape(cr['date_rdv'])} à {escape(cr['heure_rdv'])}"
        if cr["motif_rdv"]:
            rdv += f" — {escape(cr['motif_rdv'])}"

    html = (
        "<table>"
        f'<tr><th>Patient</th><td><a href="/patients/{cr["patient_id"]}">'
        f"{escape(cr['prenom'])} {escape(cr['nom'])}</a></td></tr>"
        f"<tr><th>Médecin</th><td>{afficher(cr['medecin'])}</td></tr>"
        f"<tr><th>Date</th><td>{afficher(cr['date_consultation'])}</td></tr>"
        f"<tr><th>Rendez-vous lié</th><td>{rdv}</td></tr>"
        "</table>"
    )
    for champ, libelle in [
        ("motif", "Motif"),
        ("observations", "Observations"),
        ("diagnostic", "Diagnostic"),
        ("traitement", "Traitement"),
    ]:
        html += f'<h2>{libelle}</h2><p class="texte">{afficher(cr[champ])}</p>'
    html += f"<p>{bouton(f'/consultations/{consultation_id}/modifier', 'Modifier ce compte-rendu')}</p>"

    return page(f"Compte-rendu du {cr['date_consultation']}", html)


@app.route("/consultations/<int:consultation_id>/modifier", methods=["GET", "POST"])
def modifier_compte_rendu(consultation_id):
    with closing(se_connecter_a_la_base()) as connexion:
        cr = chercher_ou_404(
            connexion, "SELECT * FROM consultations WHERE id = ?", consultation_id
        )
        valeurs = valeurs_depuis_ligne(cr, CHAMPS_CONSULTATION)
        erreur = None
        if request.method == "POST":
            valeurs = lire_formulaire(CHAMPS_CONSULTATION)
            erreur = valider_consultation(connexion, valeurs)
            if erreur is None:
                normaliser_consultation(valeurs)
                connexion.execute(
                    "UPDATE consultations SET "
                    f"{', '.join(c + ' = ?' for c in CHAMPS_CONSULTATION)} WHERE id = ?",
                    [*ou_null(valeurs, CHAMPS_CONSULTATION), consultation_id],
                )
                connexion.commit()
                return redirect(f"/consultations/{consultation_id}")
        patients, rendez_vous = patients_et_rendez_vous(connexion)

    return page(
        "Modifier le compte-rendu",
        formulaire_consultation(f"/consultations/{consultation_id}/modifier", valeurs,
                                patients, rendez_vous, "Enregistrer", erreur),
    )


if __name__ == "__main__":
    app.run(debug=True)
