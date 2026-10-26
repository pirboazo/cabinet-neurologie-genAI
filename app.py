"""
app.py
------
Application Flask du cabinet de neurologie.

Pages disponibles :
    /patients                -> liste, fiche, création et modification des patients
    /rendez-vous             -> liste, prise, modification et suppression des rendez-vous
    /consultations           -> comptes-rendus de consultation (liste, saisie, détail, modification)

Toutes les pages sont générées côté serveur, sans gabarit externe.

Pour la lancer (depuis la racine du projet, avec (venv) actif) :
    python3 app.py
"""

import re
import sqlite3
from contextlib import closing
from datetime import date, datetime

from flask import Flask, abort, redirect, request, url_for
from markupsafe import escape

app = Flask(__name__)

PAGES = [
    ("/patients", "Patients"),
    ("/rendez-vous", "Rendez-vous"),
    ("/consultations", "Consultations"),
]

SEXES = ["", "F", "M", "Autre"]
STATUTS_RDV = ["prévu", "honoré", "annulé"]

CHAMPS_PATIENT = [
    "nom", "prenom", "date_naissance", "sexe",
    "telephone", "email", "adresse", "antecedents",
]
CHAMPS_RDV = ["patient_id", "date_rdv", "heure_rdv", "motif", "statut"]
CHAMPS_CONSULTATION = [
    "patient_id", "rendez_vous_id", "date_consultation", "motif",
    "observations", "diagnostic", "traitement", "medecin",
]

CSS = """
body { font-family: system-ui, sans-serif; margin: 0; color: #222; }
nav { display: flex; gap: 8px; padding: 12px 24px; background: #f4f4f4; border-bottom: 1px solid #ccc; }
main { max-width: 960px; padding: 24px; }
h1 { font-size: 1.6em; margin-top: 0; }
h2 { font-size: 1.2em; margin-top: 28px; }
.bouton { display: inline-block; padding: 6px 12px; border: none; border-radius: 4px; background: #0066cc; color: #fff; font: inherit; text-decoration: none; cursor: pointer; }
nav .bouton { background: #555; }
nav .bouton.actif { background: #222; }
.bouton.danger { background: #b00020; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
.en-ligne { display: inline; }
.erreur { color: #b00020; font-weight: bold; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th, td { padding: 6px 8px; text-align: left; vertical-align: top; border-bottom: 1px solid #ddd; }
form label { display: block; margin-top: 12px; }
form input, form select, form textarea { display: block; width: 100%; max-width: 480px; padding: 6px; font: inherit; box-sizing: border-box; }
form.filtre { display: flex; align-items: flex-end; gap: 8px; }
form.filtre label { margin-top: 0; }
form.filtre select { width: auto; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; }
dt { font-weight: bold; }
dd { margin: 0; white-space: pre-line; }
"""


# ---------------------------------------------------------------------------
# Base de données et utilitaires
# ---------------------------------------------------------------------------

def se_connecter_a_la_base():
    connexion = sqlite3.connect("database/cabinet.db")
    connexion.row_factory = sqlite3.Row
    return connexion


def chercher_ou_404(connexion, table, identifiant):
    """Ligne de `table` d'identifiant donné, ou erreur 404.

    `table` est un nom écrit en dur dans ce fichier, jamais une saisie."""
    ligne = connexion.execute(f"SELECT * FROM {table} WHERE id = ?", (identifiant,)).fetchone()
    if ligne is None:
        abort(404)
    return ligne


def echapper(valeur):
    """Texte sûr pour le HTML : toute saisie passe par ici avant affichage."""
    return str(escape("" if valeur is None else valeur))


def afficher(valeur):
    """Comme echapper(), mais « — » pour un champ vide."""
    if valeur is None or valeur == "":
        return "—"
    return echapper(valeur)


def valeur_ou_null(valeur):
    return valeur if valeur else None


def id_valide(valeur):
    """Entier écrit en chiffres, sinon None."""
    if re.fullmatch(r"[0-9]+", valeur or ""):
        return int(valeur)
    return None


def date_valide(texte):
    return _format_valide(texte, r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "%Y-%m-%d")


def heure_valide(texte):
    return _format_valide(texte, r"[0-9]{2}:[0-9]{2}", "%H:%M")


def _format_valide(texte, motif, format_):
    if not re.fullmatch(motif, texte):
        return False
    try:
        datetime.strptime(texte, format_)
    except ValueError:
        return False
    return True


def patient_existe(connexion, valeur):
    patient_id = id_valide(valeur)
    if patient_id is None:
        return False
    return connexion.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is not None


# ---------------------------------------------------------------------------
# Rendu HTML commun
# ---------------------------------------------------------------------------

def menu():
    section = "/" + request.path.strip("/").split("/")[0]
    liens = ""
    for adresse, libelle in PAGES:
        classe = "bouton actif" if adresse == section else "bouton"
        liens += f'<a class="{classe}" href="{adresse}">{libelle}</a>'
    return f"<nav>{liens}</nav>"


def page(titre, contenu):
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{echapper(titre)} — Cabinet de neurologie</title>
<style>{CSS}</style>
</head>
<body>
{menu()}
<main>
<h1>{echapper(titre)}</h1>
{contenu}
</main>
</body>
</html>"""


def erreur_html(erreur):
    return f'<p class="erreur">{echapper(erreur)}</p>' if erreur else ""


def tableau(entetes, lignes):
    tete = "".join(f"<th>{entete}</th>" for entete in entetes)
    return f"<table><thead><tr>{tete}</tr></thead><tbody>{lignes}</tbody></table>"


def champ_texte(nom, libelle, valeurs, type_="text", requis=False):
    attribut_requis = " required" if requis else ""
    return (
        f'<label>{libelle}<input type="{type_}" name="{nom}" '
        f'value="{echapper(valeurs.get(nom))}"{attribut_requis}></label>'
    )


def champ_zone(nom, libelle, valeurs):
    return f'<label>{libelle}<textarea name="{nom}" rows="4">{echapper(valeurs.get(nom))}</textarea></label>'


def champ_select(nom, libelle, options, valeur_courante):
    html = f'<label>{libelle}<select name="{nom}">'
    for valeur, texte in options:
        selection = " selected" if str(valeur) == str(valeur_courante or "") else ""
        html += f'<option value="{echapper(valeur)}"{selection}>{echapper(texte)}</option>'
    return html + "</select></label>"


def boutons_rdv(rendez_vous_id):
    modifier = url_for("modifier_rendez_vous", rendez_vous_id=rendez_vous_id)
    supprimer = url_for("supprimer_rendez_vous", rendez_vous_id=rendez_vous_id)
    return (
        f'<a class="bouton" href="{modifier}">Modifier</a>'
        f'<form class="en-ligne" method="post" action="{supprimer}" '
        f'onsubmit="return confirm(\'Supprimer ce rendez-vous ?\');">'
        f'<button class="bouton danger" type="submit">Supprimer</button></form>'
    )


def liens_compte_rendu(consultation_id):
    voir = url_for("detail_consultation", consultation_id=consultation_id)
    modifier = url_for("modifier_compte_rendu", consultation_id=consultation_id)
    return (
        f'<a class="bouton" href="{voir}">Voir</a>'
        f'<a class="bouton" href="{modifier}">Modifier</a>'
    )


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

def valeurs_depuis_formulaire_patient():
    return {champ: request.form.get(champ, "").strip() for champ in CHAMPS_PATIENT}


def erreur_formulaire_patient(valeurs):
    if not valeurs["nom"] or not valeurs["prenom"]:
        return "Le nom et le prénom sont obligatoires."
    if valeurs["date_naissance"] and not date_valide(valeurs["date_naissance"]):
        return "La date de naissance n'est pas valide."
    if valeurs["sexe"] not in SEXES:
        return "La valeur choisie pour le sexe n'est pas valide."
    return None


def formulaire_patient(valeurs, erreur):
    sexes = [("", "— non renseigné —")] + [(sexe, sexe) for sexe in SEXES if sexe]
    return (
        erreur_html(erreur)
        + '<form method="post">'
        + champ_texte("nom", "Nom", valeurs, requis=True)
        + champ_texte("prenom", "Prénom", valeurs, requis=True)
        + champ_texte("date_naissance", "Date de naissance", valeurs, type_="date")
        + champ_select("sexe", "Sexe", sexes, valeurs.get("sexe"))
        + champ_texte("telephone", "Téléphone", valeurs, type_="tel")
        + champ_texte("email", "Email", valeurs, type_="email")
        + champ_texte("adresse", "Adresse", valeurs)
        + champ_zone("antecedents", "Antécédents", valeurs)
        + '<div class="actions"><button class="bouton" type="submit">Enregistrer</button></div>'
        + "</form>"
    )


@app.route("/")
def accueil():
    return redirect(url_for("liste_patients"))


@app.route("/patients")
def liste_patients():
    with closing(se_connecter_a_la_base()) as connexion:
        patients = connexion.execute(
            "SELECT id, nom, prenom, date_naissance FROM patients ORDER BY nom, prenom"
        ).fetchall()

    actions = f'<div class="actions"><a class="bouton" href="{url_for("nouveau_patient")}">Ajouter un patient</a></div>'
    if not patients:
        return page("Patients", actions + "<p>Aucun patient enregistré.</p>")

    lignes = ""
    for patient in patients:
        lien = url_for("fiche_patient", patient_id=patient["id"])
        lignes += (
            f'<tr><td><a href="{lien}">{echapper(patient["nom"])}</a></td>'
            f'<td><a href="{lien}">{echapper(patient["prenom"])}</a></td>'
            f'<td>{afficher(patient["date_naissance"])}</td></tr>'
        )
    tab = tableau(["Nom", "Prénom", "Date de naissance"], lignes)
    return page("Patients", actions + tab)


@app.route("/patients/nouveau", methods=["GET", "POST"])
def nouveau_patient():
    if request.method == "POST":
        valeurs = valeurs_depuis_formulaire_patient()
        erreur = erreur_formulaire_patient(valeurs)
        if erreur is None:
            with closing(se_connecter_a_la_base()) as connexion:
                curseur = connexion.execute(
                    "INSERT INTO patients (nom, prenom, date_naissance, sexe, telephone, email, adresse, antecedents) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [valeur_ou_null(valeurs[champ]) for champ in CHAMPS_PATIENT],
                )
                patient_id = curseur.lastrowid
                connexion.commit()
            return redirect(url_for("fiche_patient", patient_id=patient_id))
    else:
        valeurs, erreur = {}, None
    return page("Nouveau patient", formulaire_patient(valeurs, erreur))


@app.route("/patients/<int:patient_id>")
def fiche_patient(patient_id):
    with closing(se_connecter_a_la_base()) as connexion:
        patient = chercher_ou_404(connexion, "patients", patient_id)
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

    identite = (
        "<dl>"
        f"<dt>Date de naissance</dt><dd>{afficher(patient['date_naissance'])}</dd>"
        f"<dt>Téléphone</dt><dd>{afficher(patient['telephone'])}</dd>"
        f"<dt>Email</dt><dd>{afficher(patient['email'])}</dd>"
        f"<dt>Adresse</dt><dd>{afficher(patient['adresse'])}</dd>"
        f"<dt>Antécédents</dt><dd>{afficher(patient['antecedents'])}</dd>"
        "</dl>"
    )
    actions = (
        '<div class="actions">'
        f'<a class="bouton" href="{url_for("nouveau_rendez_vous", patient_id=patient_id)}">Prendre un rendez-vous</a>'
        f'<a class="bouton" href="{url_for("modifier_patient", patient_id=patient_id)}">Modifier le patient</a>'
        f'<a class="bouton" href="{url_for("nouveau_compte_rendu", patient_id=patient_id)}">Rédiger un compte-rendu</a>'
        "</div>"
    )

    if rendez_vous:
        lignes = "".join(
            f'<tr><td>{rdv["date_rdv"]}</td><td>{rdv["heure_rdv"]}</td>'
            f'<td>{afficher(rdv["motif"])}</td><td>{rdv["statut"]}</td>'
            f'<td class="actions">{boutons_rdv(rdv["id"])}</td></tr>'
            for rdv in rendez_vous
        )
        section_rdv = tableau(["Date", "Heure", "Motif", "Statut", ""], lignes)
    else:
        section_rdv = "<p>Aucun rendez-vous pour ce patient.</p>"

    if comptes_rendus:
        lignes = "".join(
            f'<tr><td>{cr["date_consultation"]}</td><td>{afficher(cr["medecin"])}</td>'
            f'<td>{afficher(cr["motif"])}</td>'
            f'<td class="actions">{liens_compte_rendu(cr["id"])}</td></tr>'
            for cr in comptes_rendus
        )
        section_cr = tableau(["Date", "Médecin", "Motif", ""], lignes)
    else:
        section_cr = "<p>Aucun compte-rendu de consultation pour ce patient.</p>"

    contenu = (
        identite
        + actions
        + "<h2>Rendez-vous</h2>"
        + section_rdv
        + "<h2>Comptes-rendus de consultation</h2>"
        + section_cr
    )
    return page(f"{patient['prenom']} {patient['nom']}", contenu)


@app.route("/patients/<int:patient_id>/modifier", methods=["GET", "POST"])
def modifier_patient(patient_id):
    with closing(se_connecter_a_la_base()) as connexion:
        patient = chercher_ou_404(connexion, "patients", patient_id)
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_patient()
            erreur = erreur_formulaire_patient(valeurs)
            if erreur is None:
                connexion.execute(
                    "UPDATE patients SET nom = ?, prenom = ?, date_naissance = ?, sexe = ?, "
                    "telephone = ?, email = ?, adresse = ?, antecedents = ? WHERE id = ?",
                    [valeur_ou_null(valeurs[champ]) for champ in CHAMPS_PATIENT] + [patient_id],
                )
                connexion.commit()
                return redirect(url_for("fiche_patient", patient_id=patient_id))
        else:
            valeurs, erreur = dict(patient), None
    return page("Modifier le patient", formulaire_patient(valeurs, erreur))


# ---------------------------------------------------------------------------
# Rendez-vous
# ---------------------------------------------------------------------------

def liste_des_patients(connexion):
    return connexion.execute("SELECT id, nom, prenom FROM patients ORDER BY nom, prenom").fetchall()


def valeurs_depuis_formulaire_rendez_vous():
    return {champ: request.form.get(champ, "").strip() for champ in CHAMPS_RDV}


def valider_rendez_vous(connexion, valeurs, avec_statut):
    if not patient_existe(connexion, valeurs["patient_id"]):
        return "Merci de choisir un patient."
    if not (date_valide(valeurs["date_rdv"]) and heure_valide(valeurs["heure_rdv"])):
        return "Merci de saisir une date et une heure valides."
    if avec_statut and valeurs["statut"] not in STATUTS_RDV:
        return "Le statut choisi n'est pas valide."
    return None


def formulaire_rendez_vous(valeurs, patients, erreur, avec_statut):
    options_patients = [("", "— choisir un patient —")] + [
        (patient["id"], f"{patient['prenom']} {patient['nom']}") for patient in patients
    ]
    html = (
        erreur_html(erreur)
        + '<form method="post">'
        + champ_select("patient_id", "Patient", options_patients, valeurs.get("patient_id"))
        + champ_texte("date_rdv", "Date", valeurs, type_="date", requis=True)
        + champ_texte("heure_rdv", "Heure", valeurs, type_="time", requis=True)
        + champ_texte("motif", "Motif", valeurs)
    )
    if avec_statut:
        html += champ_select("statut", "Statut", [(statut, statut) for statut in STATUTS_RDV], valeurs.get("statut"))
    html += '<div class="actions"><button class="bouton" type="submit">Enregistrer</button></div></form>'
    return html


@app.route("/rendez-vous")
def liste_rendez_vous():
    with closing(se_connecter_a_la_base()) as connexion:
        rendez_vous = connexion.execute(
            """
            SELECT r.id, r.date_rdv, r.heure_rdv, r.motif, r.statut,
                   p.id AS patient_id, p.nom, p.prenom
            FROM rendez_vous AS r
            JOIN patients AS p ON p.id = r.patient_id
            ORDER BY r.date_rdv, r.heure_rdv
            """
        ).fetchall()

    if not rendez_vous:
        return page("Rendez-vous", "<p>Aucun rendez-vous enregistré.</p>")

    lignes = ""
    for rdv in rendez_vous:
        lien = url_for("fiche_patient", patient_id=rdv["patient_id"])
        lignes += (
            f'<tr><td>{rdv["date_rdv"]}</td><td>{rdv["heure_rdv"]}</td>'
            f'<td><a href="{lien}">{echapper(rdv["prenom"])} {echapper(rdv["nom"])}</a></td>'
            f'<td>{afficher(rdv["motif"])}</td><td>{rdv["statut"]}</td>'
            f'<td class="actions">{boutons_rdv(rdv["id"])}</td></tr>'
        )
    return page("Rendez-vous", tableau(["Date", "Heure", "Patient", "Motif", "Statut", ""], lignes))


@app.route("/rendez-vous/nouveau", methods=["GET", "POST"])
def nouveau_rendez_vous():
    with closing(se_connecter_a_la_base()) as connexion:
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_rendez_vous()
            erreur = valider_rendez_vous(connexion, valeurs, avec_statut=False)
            if erreur is None:
                connexion.execute(
                    "INSERT INTO rendez_vous (patient_id, date_rdv, heure_rdv, motif, statut) "
                    "VALUES (?, ?, ?, ?, 'prévu')",
                    (int(valeurs["patient_id"]), valeurs["date_rdv"], valeurs["heure_rdv"],
                     valeur_ou_null(valeurs["motif"])),
                )
                connexion.commit()
                return redirect(url_for("fiche_patient", patient_id=int(valeurs["patient_id"])))
        else:
            valeurs = {"patient_id": request.args.get("patient_id", "")}
            erreur = None
        patients = liste_des_patients(connexion)
    return page("Nouveau rendez-vous", formulaire_rendez_vous(valeurs, patients, erreur, avec_statut=False))


@app.route("/rendez-vous/<int:rendez_vous_id>/modifier", methods=["GET", "POST"])
def modifier_rendez_vous(rendez_vous_id):
    with closing(se_connecter_a_la_base()) as connexion:
        rdv = chercher_ou_404(connexion, "rendez_vous", rendez_vous_id)
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_rendez_vous()
            erreur = valider_rendez_vous(connexion, valeurs, avec_statut=True)
            if erreur is None:
                connexion.execute(
                    "UPDATE rendez_vous SET patient_id = ?, date_rdv = ?, heure_rdv = ?, motif = ?, statut = ? "
                    "WHERE id = ?",
                    (int(valeurs["patient_id"]), valeurs["date_rdv"], valeurs["heure_rdv"],
                     valeur_ou_null(valeurs["motif"]), valeurs["statut"], rendez_vous_id),
                )
                connexion.commit()
                return redirect(url_for("liste_rendez_vous"))
        else:
            valeurs, erreur = dict(rdv), None
        patients = liste_des_patients(connexion)
    return page("Modifier le rendez-vous", formulaire_rendez_vous(valeurs, patients, erreur, avec_statut=True))


@app.route("/rendez-vous/<int:rendez_vous_id>/supprimer", methods=["POST"])
def supprimer_rendez_vous(rendez_vous_id):
    with closing(se_connecter_a_la_base()) as connexion:
        chercher_ou_404(connexion, "rendez_vous", rendez_vous_id)
        # Les comptes-rendus liés sont conservés, seul leur lien est retiré.
        connexion.execute(
            "UPDATE consultations SET rendez_vous_id = NULL WHERE rendez_vous_id = ?",
            (rendez_vous_id,),
        )
        connexion.execute("DELETE FROM rendez_vous WHERE id = ?", (rendez_vous_id,))
        connexion.commit()
    return redirect(url_for("liste_rendez_vous"))


# ---------------------------------------------------------------------------
# Comptes-rendus de consultation
# ---------------------------------------------------------------------------

def valeurs_depuis_formulaire_consultation():
    return {champ: request.form.get(champ, "").strip() for champ in CHAMPS_CONSULTATION}


def valider_consultation(connexion, valeurs):
    if not patient_existe(connexion, valeurs["patient_id"]):
        return "Merci de choisir un patient."
    if valeurs["rendez_vous_id"]:
        rdv = None
        rdv_id = id_valide(valeurs["rendez_vous_id"])
        if rdv_id is not None:
            rdv = connexion.execute(
                "SELECT patient_id FROM rendez_vous WHERE id = ?", (rdv_id,)
            ).fetchone()
        if rdv is None:
            return "Le rendez-vous choisi n'existe pas."
        if rdv["patient_id"] != int(valeurs["patient_id"]):
            return "Le rendez-vous choisi n'appartient pas à ce patient."
    if not date_valide(valeurs["date_consultation"]):
        return "Merci de saisir une date valide."
    return None


def parametres_consultation(valeurs):
    """Valeurs dans l'ordre des colonnes de CHAMPS_CONSULTATION, vides → NULL.

    Suppose la validation déjà passée (identifiants numériques)."""
    return (
        int(valeurs["patient_id"]),
        int(valeurs["rendez_vous_id"]) if valeurs["rendez_vous_id"] else None,
        valeurs["date_consultation"],
        valeur_ou_null(valeurs["motif"]),
        valeur_ou_null(valeurs["observations"]),
        valeur_ou_null(valeurs["diagnostic"]),
        valeur_ou_null(valeurs["traitement"]),
        valeur_ou_null(valeurs["medecin"]),
    )


def patients_et_rendez_vous(connexion):
    rendez_vous = connexion.execute(
        """
        SELECT r.id, r.date_rdv, r.heure_rdv, p.nom, p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON p.id = r.patient_id
        ORDER BY r.date_rdv, r.heure_rdv
        """
    ).fetchall()
    return liste_des_patients(connexion), rendez_vous


def formulaire_consultation(valeurs, patients, rendez_vous, erreur):
    options_patients = [("", "— choisir un patient —")] + [
        (patient["id"], f"{patient['prenom']} {patient['nom']}") for patient in patients
    ]
    options_rdv = [("", "— aucun —")] + [
        (rdv["id"], f"{rdv['date_rdv']} {rdv['heure_rdv']} — {rdv['prenom']} {rdv['nom']}")
        for rdv in rendez_vous
    ]
    return (
        erreur_html(erreur)
        + '<form method="post">'
        + champ_select("patient_id", "Patient", options_patients, valeurs.get("patient_id"))
        + champ_select("rendez_vous_id", "Rendez-vous (facultatif)", options_rdv, valeurs.get("rendez_vous_id"))
        + champ_texte("date_consultation", "Date de la consultation", valeurs, type_="date", requis=True)
        + champ_texte("motif", "Motif", valeurs)
        + champ_zone("observations", "Observations", valeurs)
        + champ_zone("diagnostic", "Diagnostic", valeurs)
        + champ_zone("traitement", "Traitement", valeurs)
        + champ_texte("medecin", "Médecin", valeurs)
        + '<div class="actions"><button class="bouton" type="submit">Enregistrer</button></div>'
        + "</form>"
    )


@app.route("/consultations")
def liste_consultations():
    medecin = request.args.get("medecin", "")
    with closing(se_connecter_a_la_base()) as connexion:
        medecins = [
            ligne["medecin"]
            for ligne in connexion.execute(
                "SELECT DISTINCT medecin FROM consultations "
                "WHERE medecin IS NOT NULL AND medecin <> '' ORDER BY medecin"
            )
        ]
        # `? = ''` : pas de filtre si aucun médecin n'est demandé.
        comptes_rendus = connexion.execute(
            """
            SELECT c.id, c.date_consultation, c.medecin, p.nom, p.prenom
            FROM consultations AS c
            JOIN patients AS p ON p.id = c.patient_id
            WHERE ? = '' OR c.medecin = ?
            ORDER BY c.date_consultation, c.id
            """,
            (medecin, medecin),
        ).fetchall()

    options = [("", "Tous les médecins")] + [(nom, nom) for nom in medecins]
    # Un médecin demandé sans résultat doit rester sélectionnable.
    if medecin and medecin not in medecins:
        options.append((medecin, medecin))
    filtre = (
        '<form method="get" class="filtre">'
        + champ_select("medecin", "Médecin", options, medecin)
        + '<button class="bouton" type="submit">Filtrer</button></form>'
    )

    if not comptes_rendus:
        if medecin:
            message = "<p>Aucun compte-rendu pour ce médecin.</p>"
        else:
            message = "<p>Aucun compte-rendu enregistré.</p>"
        return page("Consultations", filtre + message)

    lignes = ""
    for cr in comptes_rendus:
        lien = url_for("detail_consultation", consultation_id=cr["id"])
        lignes += (
            f'<tr><td><a href="{lien}">{echapper(cr["prenom"])} {echapper(cr["nom"])}</a></td>'
            f'<td>{afficher(cr["medecin"])}</td><td>{cr["date_consultation"]}</td></tr>'
        )
    return page("Consultations", filtre + tableau(["Patient", "Médecin", "Date"], lignes))


@app.route("/consultations/nouveau", methods=["GET", "POST"])
def nouveau_compte_rendu():
    with closing(se_connecter_a_la_base()) as connexion:
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_consultation()
            erreur = valider_consultation(connexion, valeurs)
            if erreur is None:
                connexion.execute(
                    "INSERT INTO consultations "
                    "(patient_id, rendez_vous_id, date_consultation, motif, observations, diagnostic, traitement, medecin) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    parametres_consultation(valeurs),
                )
                connexion.commit()
                return redirect(url_for("liste_consultations"))
        else:
            valeurs = {
                "patient_id": request.args.get("patient_id", ""),
                "rendez_vous_id": request.args.get("rendez_vous_id", ""),
                "date_consultation": date.today().isoformat(),
            }
            erreur = None
        patients, rendez_vous = patients_et_rendez_vous(connexion)
    return page("Nouveau compte-rendu", formulaire_consultation(valeurs, patients, rendez_vous, erreur))


@app.route("/consultations/<int:consultation_id>")
def detail_consultation(consultation_id):
    with closing(se_connecter_a_la_base()) as connexion:
        cr = connexion.execute(
            """
            SELECT c.*, p.nom, p.prenom, r.date_rdv, r.heure_rdv
            FROM consultations AS c
            JOIN patients AS p ON p.id = c.patient_id
            LEFT JOIN rendez_vous AS r ON r.id = c.rendez_vous_id
            WHERE c.id = ?
            """,
            (consultation_id,),
        ).fetchone()
    if cr is None:
        abort(404)

    rdv_texte = f"{cr['date_rdv']} à {cr['heure_rdv']}" if cr["date_rdv"] else None
    lien_patient = url_for("fiche_patient", patient_id=cr["patient_id"])
    modifier = url_for("modifier_compte_rendu", consultation_id=consultation_id)
    contenu = (
        "<dl>"
        f'<dt>Patient</dt><dd><a href="{lien_patient}">{echapper(cr["prenom"])} {echapper(cr["nom"])}</a></dd>'
        f"<dt>Médecin</dt><dd>{afficher(cr['medecin'])}</dd>"
        f"<dt>Date</dt><dd>{cr['date_consultation']}</dd>"
        f"<dt>Rendez-vous</dt><dd>{afficher(rdv_texte)}</dd>"
        f"<dt>Motif</dt><dd>{afficher(cr['motif'])}</dd>"
        f"<dt>Observations</dt><dd>{afficher(cr['observations'])}</dd>"
        f"<dt>Diagnostic</dt><dd>{afficher(cr['diagnostic'])}</dd>"
        f"<dt>Traitement</dt><dd>{afficher(cr['traitement'])}</dd>"
        "</dl>"
        f'<div class="actions"><a class="bouton" href="{modifier}">Modifier ce compte-rendu</a></div>'
    )
    return page(f"Consultation du {cr['date_consultation']}", contenu)


@app.route("/consultations/<int:consultation_id>/modifier", methods=["GET", "POST"])
def modifier_compte_rendu(consultation_id):
    with closing(se_connecter_a_la_base()) as connexion:
        cr = chercher_ou_404(connexion, "consultations", consultation_id)
        if request.method == "POST":
            valeurs = valeurs_depuis_formulaire_consultation()
            erreur = valider_consultation(connexion, valeurs)
            if erreur is None:
                connexion.execute(
                    "UPDATE consultations SET patient_id = ?, rendez_vous_id = ?, date_consultation = ?, "
                    "motif = ?, observations = ?, diagnostic = ?, traitement = ?, medecin = ? WHERE id = ?",
                    parametres_consultation(valeurs) + (consultation_id,),
                )
                connexion.commit()
                return redirect(url_for("detail_consultation", consultation_id=consultation_id))
        else:
            valeurs, erreur = dict(cr), None
        patients, rendez_vous = patients_et_rendez_vous(connexion)
    return page("Modifier le compte-rendu", formulaire_consultation(valeurs, patients, rendez_vous, erreur))


if __name__ == "__main__":
    app.run(debug=True)
