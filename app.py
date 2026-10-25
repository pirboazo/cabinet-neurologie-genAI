"""
app.py
------
Application Flask de gestion d'un cabinet de neurologie.

Pages disponibles :
    /patients        -> liste, création et modification des patients
    /rendez-vous     -> liste, création, modification et suppression des RDV
    /consultations   -> liste, saisie, détail et modification des comptes-rendus

Pour la lancer (depuis la racine du projet, avec (venv) actif) :
    python3 app.py
"""

import re
import sqlite3
from datetime import date, time

from flask import Flask, abort, redirect, request
from markupsafe import escape

app = Flask(__name__)


PAGES = [
    ("/patients", "Patients"),
    ("/rendez-vous", "Rendez-vous"),
    ("/consultations", "Consultations"),
]

CHAMPS_PATIENT = [
    ("nom", "Nom", "text"),
    ("prenom", "Prénom", "text"),
    ("date_naissance", "Date de naissance", "date"),
    ("sexe", "Sexe", "sexe"),
    ("telephone", "Téléphone", "tel"),
    ("email", "Email", "email"),
    ("adresse", "Adresse", "text"),
    ("antecedents", "Antécédents", "textarea"),
]
SEXES = ("", "F", "M", "Autre")

CHAMPS_RDV = [
    ("patient_id", "Patient", "patient"),
    ("date_rdv", "Date", "date"),
    ("heure_rdv", "Heure", "time"),
    ("motif", "Motif", "text"),
]
STATUTS_RDV = ("prévu", "honoré", "annulé")

CHAMPS_CONSULTATION = [
    ("patient_id", "Patient", "patient"),
    ("rendez_vous_id", "Rendez-vous", "rendez_vous"),
    ("date_consultation", "Date", "date"),
    ("motif", "Motif", "text"),
    ("observations", "Observations", "textarea"),
    ("diagnostic", "Diagnostic", "textarea"),
    ("traitement", "Traitement", "textarea"),
    ("medecin", "Médecin", "text"),
]

CSS = """
* { box-sizing: border-box; }
body {
    margin: 0;
    background: #ffffff;
    color: #222222;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5;
}
nav {
    display: flex;
    gap: 8px;
    padding: 12px 20px;
    background: #eeeeee;
    border-bottom: 1px solid #dddddd;
}
nav .bouton {
    background: #555555;
}
nav .bouton.actif {
    background: #222222;
    box-shadow: inset 0 0 0 2px #ffffff;
}
main {
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 20px 40px;
}
h1, h2 {
    color: #222222;
}
a {
    color: #0066cc;
}
.bouton {
    display: inline-block;
    padding: 6px 12px;
    border: none;
    border-radius: 4px;
    background: #0066cc;
    color: #ffffff;
    font-size: 14px;
    text-decoration: none;
    cursor: pointer;
}
.bouton:hover {
    opacity: 0.88;
}
.bouton.danger {
    background: #cc0000;
}
.actions, .champ-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 12px 0;
}
form.inline {
    display: inline;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 20px;
}
th, td {
    padding: 7px 8px;
    border-bottom: 1px solid #dddddd;
    text-align: left;
    vertical-align: top;
}
th {
    background: #f7f7f7;
}
.champ {
    margin: 12px 0;
}
.champ label {
    display: block;
    margin-bottom: 4px;
    font-weight: 600;
}
.champ input, .champ select, .champ textarea {
    width: 100%;
    max-width: 520px;
    padding: 6px;
    border: 1px solid #bbbbbb;
    border-radius: 4px;
    font: inherit;
}
.champ textarea {
    min-height: 90px;
    resize: vertical;
}
.erreur {
    padding: 8px 12px;
    border: 1px solid #e0b4b0;
    border-radius: 4px;
    background: #fdecea;
    color: #a00000;
}
.texte {
    white-space: pre-line;
}
"""


def se_connecter_a_la_base():
    connexion = sqlite3.connect("database/cabinet.db")
    connexion.row_factory = sqlite3.Row
    return connexion


def menu():
    liens = []
    for adresse, libelle in PAGES:
        actif = request.path == adresse or request.path.startswith(adresse + "/")
        classe = "bouton actif" if actif else "bouton"
        liens.append(f'<a class="{classe}" href="{adresse}">{libelle}</a>')
    return '<nav class="menu">' + "".join(liens) + "</nav>"


def page(titre, contenu):
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titre)}</title>
<style>{CSS}</style>
</head>
<body>
{menu()}
<main>
<h1>{escape(titre)}</h1>
{contenu}
</main>
</body>
</html>"""


def afficher(valeur):
    """Affiche une valeur de texte, ou un tiret cadratin si elle est vide."""
    if valeur is None or valeur == "":
        return "—"
    return escape(valeur)


def date_valide(valeur):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur or ""):
        return False
    try:
        date.fromisoformat(valeur)
    except ValueError:
        return False
    return True


def heure_valide(valeur):
    if not re.fullmatch(r"\d{2}:\d{2}", valeur or ""):
        return False
    try:
        time.fromisoformat(valeur)
    except ValueError:
        return False
    return True


def entier(valeur):
    valeur = (valeur or "").strip()
    if valeur == "":
        return None
    try:
        return int(valeur)
    except ValueError:
        return None


def valeur_ou_none(valeur):
    return valeur if valeur else None


def patient_existe(connexion, patient_id):
    return (
        connexion.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone()
        is not None
    )


def patients_et_rendez_vous(connexion):
    patients = connexion.execute(
        "SELECT id, nom, prenom FROM patients ORDER BY nom, prenom"
    ).fetchall()
    rendez_vous = connexion.execute(
        """
        SELECT r.id, r.date_rdv, r.heure_rdv, r.motif, p.nom, p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON p.id = r.patient_id
        ORDER BY r.date_rdv, r.heure_rdv, r.id
        """
    ).fetchall()
    return patients, rendez_vous


def champ(nom, libelle, type_champ, valeur="", patients=None, rendez_vous=None, statuts=None):
    valeur = "" if valeur is None else str(valeur)

    if type_champ == "textarea":
        controle = (
            f'<textarea id="{nom}" name="{nom}">{escape(valeur)}</textarea>'
        )
    elif type_champ == "sexe":
        options = ['<option value="">Non renseigné</option>']
        for sexe in SEXES[1:]:
            selection = " selected" if sexe == valeur else ""
            options.append(f'<option value="{sexe}"{selection}>{sexe}</option>')
        controle = f'<select id="{nom}" name="{nom}">{"".join(options)}</select>'
    elif type_champ == "patient":
        options = ['<option value="">— Choisir un patient —</option>']
        for patient in patients or []:
            identifiant = str(patient["id"])
            selection = " selected" if identifiant == valeur else ""
            options.append(
                f'<option value="{identifiant}"{selection}>'
                f'{escape(patient["nom"])} {escape(patient["prenom"])}</option>'
            )
        controle = f'<select id="{nom}" name="{nom}">{"".join(options)}</select>'
    elif type_champ == "rendez_vous":
        options = ['<option value="">— Aucun —</option>']
        for rdv in rendez_vous or []:
            identifiant = str(rdv["id"])
            selection = " selected" if identifiant == valeur else ""
            libelle_rdv = (
                f'{rdv["date_rdv"]} {rdv["heure_rdv"]} — '
                f'{rdv["prenom"]} {rdv["nom"]}'
            )
            if rdv["motif"]:
                libelle_rdv += f' ({rdv["motif"]})'
            options.append(
                f'<option value="{identifiant}"{selection}>'
                f"{escape(libelle_rdv)}</option>"
            )
        controle = f'<select id="{nom}" name="{nom}">{"".join(options)}</select>'
    elif type_champ == "statut":
        options = []
        for statut in statuts or STATUTS_RDV:
            selection = " selected" if statut == valeur else ""
            options.append(
                f'<option value="{escape(statut)}"{selection}>{escape(statut)}</option>'
            )
        controle = f'<select id="{nom}" name="{nom}">{"".join(options)}</select>'
    else:
        controle = (
            f'<input type="{type_champ}" id="{nom}" name="{nom}" '
            f'value="{escape(valeur)}">'
        )

    return (
        f'<div class="champ"><label for="{nom}">{escape(libelle)}</label>'
        f"{controle}</div>"
    )


def bloc_formulaire(action, champs, erreur=None, bouton="Enregistrer"):
    # Les messages proviennent uniquement des validateurs ci-dessus.
    message = f'<p class="erreur">{erreur}</p>' if erreur else ""
    return (
        f'<form method="post" action="{escape(action)}">'
        f"{message}{champs}"
        f'<div class="champ-actions">'
        f'<button type="submit" class="bouton">{escape(bouton)}</button>'
        f"</div></form>"
    )


def valeurs_depuis_formulaire_patient(formulaire):
    return {
        nom: formulaire.get(nom, "").strip()
        for nom, _, _ in CHAMPS_PATIENT
    }


def erreur_formulaire_patient(valeurs):
    if not valeurs["nom"] or not valeurs["prenom"]:
        return "Le nom et le prénom sont obligatoires."
    if valeurs["date_naissance"] and not date_valide(valeurs["date_naissance"]):
        return "La date de naissance n'est pas valide."
    if valeurs["sexe"] not in SEXES:
        return "La valeur choisie pour le sexe n'est pas valide."
    return None


def formulaire_patient(valeurs, erreur=None, action="", bouton="Enregistrer"):
    champs = "".join(
        champ(nom, libelle, type_champ, valeurs.get(nom, ""))
        for nom, libelle, type_champ in CHAMPS_PATIENT
    )
    return bloc_formulaire(action, champs, erreur, bouton)


def valider_rendez_vous(connexion, formulaire, edition=False):
    valeurs = {
        nom: formulaire.get(nom, "").strip()
        for nom, _, _ in CHAMPS_RDV
    }
    if edition:
        valeurs["statut"] = formulaire.get("statut", "").strip()

    patient_id = entier(valeurs["patient_id"])
    if patient_id is None or not patient_existe(connexion, patient_id):
        return valeurs, "Merci de choisir un patient.", None
    if not date_valide(valeurs["date_rdv"]) or not heure_valide(valeurs["heure_rdv"]):
        return valeurs, "Merci de saisir une date et une heure valides.", None
    if edition and valeurs["statut"] not in STATUTS_RDV:
        return valeurs, "Le statut choisi n'est pas valide.", None
    return valeurs, None, patient_id


def formulaire_rendez_vous(valeurs, patients, erreur=None, action="", edition=False):
    champs = "".join(
        champ(nom, libelle, type_champ, valeurs.get(nom, ""), patients=patients)
        for nom, libelle, type_champ in CHAMPS_RDV
    )
    if edition:
        statut = valeurs.get("statut") or STATUTS_RDV[0]
        champs += champ("statut", "Statut", "statut", statut, statuts=STATUTS_RDV)
    return bloc_formulaire(action, champs, erreur)


def valider_consultation(connexion, formulaire):
    valeurs = {
        nom: formulaire.get(nom, "").strip()
        for nom, _, _ in CHAMPS_CONSULTATION
    }

    patient_id = entier(valeurs["patient_id"])
    if patient_id is None or not patient_existe(connexion, patient_id):
        return valeurs, "Merci de choisir un patient.", None, None

    rendez_vous_id = None
    if valeurs["rendez_vous_id"]:
        rendez_vous_id = entier(valeurs["rendez_vous_id"])
        ligne = None
        if rendez_vous_id is not None:
            ligne = connexion.execute(
                "SELECT patient_id FROM rendez_vous WHERE id = ?",
                (rendez_vous_id,),
            ).fetchone()
        if ligne is None:
            return valeurs, "Le rendez-vous choisi n'existe pas.", None, None
        if ligne["patient_id"] != patient_id:
            return (
                valeurs,
                "Le rendez-vous choisi n'appartient pas à ce patient.",
                None,
                None,
            )

    if not date_valide(valeurs["date_consultation"]):
        return valeurs, "Merci de saisir une date valide.", None, None

    return valeurs, None, patient_id, rendez_vous_id


def formulaire_consultation(valeurs, patients, rendez_vous, erreur=None, action=""):
    champs = "".join(
        champ(
            nom,
            libelle,
            type_champ,
            valeurs.get(nom, ""),
            patients=patients,
            rendez_vous=rendez_vous,
        )
        for nom, libelle, type_champ in CHAMPS_CONSULTATION
    )
    return bloc_formulaire(action, champs, erreur)


def boutons_rdv(rendez_vous_id):
    return (
        f'<a class="bouton" href="/rendez-vous/{rendez_vous_id}/modifier">Modifier</a> '
        f'<form class="inline" method="post" '
        f'action="/rendez-vous/{rendez_vous_id}/supprimer" '
        f'onsubmit="return confirm(\'Supprimer ce rendez-vous ?\');">'
        f'<button type="submit" class="bouton danger">Supprimer</button></form>'
    )


@app.route("/")
def accueil():
    return redirect("/patients")


@app.route("/patients")
def liste_patients():
    connexion = se_connecter_a_la_base()
    patients = connexion.execute(
        "SELECT * FROM patients ORDER BY nom, prenom"
    ).fetchall()
    connexion.close()

    contenu = (
        '<div class="actions">'
        '<a class="bouton" href="/patients/nouveau">Ajouter un patient</a>'
        "</div>"
    )
    if patients:
        lignes = "".join(
            f"<tr>"
            f'<td><a href="/patients/{patient["id"]}">'
            f'{escape(patient["nom"])} {escape(patient["prenom"])}</a></td>'
            f'<td>{patient["date_naissance"] or "—"}</td>'
            f"</tr>"
            for patient in patients
        )
        contenu += (
            "<table><thead><tr><th>Nom et prénom</th>"
            "<th>Date de naissance</th></tr></thead>"
            f"<tbody>{lignes}</tbody></table>"
        )
    else:
        contenu += "<p>Aucun patient enregistré.</p>"

    return page("Patients", contenu)


@app.route("/patients/nouveau", methods=["GET", "POST"])
def nouveau_patient():
    if request.method == "POST":
        valeurs = valeurs_depuis_formulaire_patient(request.form)
        erreur = erreur_formulaire_patient(valeurs)
        if erreur is None:
            connexion = se_connecter_a_la_base()
            curseur = connexion.execute(
                """
                INSERT INTO patients
                    (nom, prenom, date_naissance, sexe, telephone, email,
                     adresse, antecedents)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    valeurs["nom"],
                    valeurs["prenom"],
                    valeur_ou_none(valeurs["date_naissance"]),
                    valeur_ou_none(valeurs["sexe"]),
                    valeur_ou_none(valeurs["telephone"]),
                    valeur_ou_none(valeurs["email"]),
                    valeur_ou_none(valeurs["adresse"]),
                    valeur_ou_none(valeurs["antecedents"]),
                ),
            )
            patient_id = curseur.lastrowid
            connexion.commit()
            connexion.close()
            return redirect(f"/patients/{patient_id}")
    else:
        valeurs = {nom: "" for nom, _, _ in CHAMPS_PATIENT}
        erreur = None

    contenu = formulaire_patient(
        valeurs, erreur, action="/patients/nouveau", bouton="Créer le patient"
    )
    return page("Nouveau patient", contenu)


@app.route("/patients/<int:patient_id>")
def fiche_patient(patient_id):
    connexion = se_connecter_a_la_base()
    patient = connexion.execute(
        "SELECT * FROM patients WHERE id = ?", (patient_id,)
    ).fetchone()
    if patient is None:
        connexion.close()
        abort(404)

    rendez_vous = connexion.execute(
        """
        SELECT * FROM rendez_vous
        WHERE patient_id = ?
        ORDER BY date_rdv, heure_rdv, id
        """,
        (patient_id,),
    ).fetchall()
    consultations = connexion.execute(
        """
        SELECT * FROM consultations
        WHERE patient_id = ?
        ORDER BY date_consultation, id
        """,
        (patient_id,),
    ).fetchall()
    connexion.close()

    identite = (
        "<h2>Identité</h2><table><tbody>"
        f"<tr><th>Date de naissance</th><td>{patient['date_naissance'] or '—'}</td></tr>"
        f"<tr><th>Sexe</th><td>{escape(patient['sexe']) if patient['sexe'] else '—'}</td></tr>"
        f"<tr><th>Téléphone</th><td>{afficher(patient['telephone'])}</td></tr>"
        f"<tr><th>Email</th><td>{afficher(patient['email'])}</td></tr>"
        f"<tr><th>Adresse</th><td>{afficher(patient['adresse'])}</td></tr>"
        f"<tr><th>Antécédents</th><td>{afficher(patient['antecedents'])}</td></tr>"
        "</tbody></table>"
        '<div class="actions">'
        f'<a class="bouton" href="/rendez-vous/nouveau?patient_id={patient_id}">'
        "Prendre un rendez-vous</a>"
        f'<a class="bouton" href="/patients/{patient_id}/modifier">'
        "Modifier le patient</a>"
        f'<a class="bouton" href="/consultations/nouveau?patient_id={patient_id}">'
        "Rédiger un compte-rendu</a>"
        "</div>"
    )

    if rendez_vous:
        lignes_rdv = "".join(
            f"<tr>"
            f'<td>{rdv["date_rdv"]}</td>'
            f'<td>{rdv["heure_rdv"]}</td>'
            f'<td>{afficher(rdv["motif"])}</td>'
            f'<td>{rdv["statut"]}</td>'
            f'<td class="actions">{boutons_rdv(rdv["id"])}</td>'
            f"</tr>"
            for rdv in rendez_vous
        )
        section_rdv = (
            "<table><thead><tr><th>Date</th><th>Heure</th><th>Motif</th>"
            "<th>Statut</th><th>Actions</th></tr></thead>"
            f"<tbody>{lignes_rdv}</tbody></table>"
        )
    else:
        section_rdv = "<p>Aucun rendez-vous pour ce patient.</p>"

    if consultations:
        lignes_consultations = "".join(
            f"<tr>"
            f'<td>{consultation["date_consultation"]}</td>'
            f'<td>{afficher(consultation["medecin"])}</td>'
            f'<td>{afficher(consultation["motif"])}</td>'
            f'<td class="actions">'
            f'<a class="bouton" href="/consultations/{consultation["id"]}">Voir</a> '
            f'<a class="bouton" '
            f'href="/consultations/{consultation["id"]}/modifier">Modifier</a>'
            f"</td></tr>"
            for consultation in consultations
        )
        section_consultations = (
            "<table><thead><tr><th>Date</th><th>Médecin</th><th>Motif</th>"
            "<th>Actions</th></tr></thead>"
            f"<tbody>{lignes_consultations}</tbody></table>"
        )
    else:
        section_consultations = "<p>Aucun compte-rendu pour ce patient.</p>"

    contenu = (
        f"{identite}<h2>Rendez-vous</h2>{section_rdv}"
        f"<h2>Comptes-rendus de consultation</h2>{section_consultations}"
    )
    return page(f"{patient['nom']} {patient['prenom']}", contenu)


@app.route("/patients/<int:patient_id>/modifier", methods=["GET", "POST"])
def modifier_patient(patient_id):
    connexion = se_connecter_a_la_base()
    patient = connexion.execute(
        "SELECT * FROM patients WHERE id = ?", (patient_id,)
    ).fetchone()
    if patient is None:
        connexion.close()
        abort(404)

    if request.method == "POST":
        valeurs = valeurs_depuis_formulaire_patient(request.form)
        erreur = erreur_formulaire_patient(valeurs)
        if erreur is None:
            connexion.execute(
                """
                UPDATE patients
                SET nom = ?, prenom = ?, date_naissance = ?, sexe = ?,
                    telephone = ?, email = ?, adresse = ?, antecedents = ?
                WHERE id = ?
                """,
                (
                    valeurs["nom"],
                    valeurs["prenom"],
                    valeur_ou_none(valeurs["date_naissance"]),
                    valeur_ou_none(valeurs["sexe"]),
                    valeur_ou_none(valeurs["telephone"]),
                    valeur_ou_none(valeurs["email"]),
                    valeur_ou_none(valeurs["adresse"]),
                    valeur_ou_none(valeurs["antecedents"]),
                    patient_id,
                ),
            )
            connexion.commit()
            connexion.close()
            return redirect(f"/patients/{patient_id}")
    else:
        valeurs = {
            nom: patient[nom] or "" for nom, _, _ in CHAMPS_PATIENT
        }
        erreur = None

    connexion.close()
    contenu = formulaire_patient(
        valeurs,
        erreur,
        action=f"/patients/{patient_id}/modifier",
        bouton="Enregistrer les modifications",
    )
    return page("Modifier le patient", contenu)


@app.route("/rendez-vous")
def liste_rendez_vous():
    connexion = se_connecter_a_la_base()
    rendez_vous = connexion.execute(
        """
        SELECT r.*, p.nom, p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON p.id = r.patient_id
        ORDER BY r.date_rdv, r.heure_rdv, r.id
        """
    ).fetchall()
    connexion.close()

    if rendez_vous:
        lignes = "".join(
            f"<tr>"
            f'<td>{rdv["date_rdv"]}</td>'
            f'<td>{rdv["heure_rdv"]}</td>'
            f'<td><a href="/patients/{rdv["patient_id"]}">'
            f'{escape(rdv["nom"])} {escape(rdv["prenom"])}</a></td>'
            f'<td>{afficher(rdv["motif"])}</td>'
            f'<td>{rdv["statut"]}</td>'
            f'<td class="actions">{boutons_rdv(rdv["id"])}</td>'
            f"</tr>"
            for rdv in rendez_vous
        )
        tableau = (
            "<table><thead><tr><th>Date</th><th>Heure</th><th>Patient</th>"
            "<th>Motif</th><th>Statut</th><th>Actions</th></tr></thead>"
            f"<tbody>{lignes}</tbody></table>"
        )
    else:
        tableau = "<p>Aucun rendez-vous enregistré.</p>"

    contenu = (
        '<div class="actions">'
        '<a class="bouton" href="/rendez-vous/nouveau">Prendre un rendez-vous</a>'
        f"</div>{tableau}"
    )
    return page("Rendez-vous", contenu)


@app.route("/rendez-vous/nouveau", methods=["GET", "POST"])
def nouveau_rendez_vous():
    connexion = se_connecter_a_la_base()

    if request.method == "POST":
        valeurs, erreur, patient_id = valider_rendez_vous(connexion, request.form)
        if erreur is None:
            connexion.execute(
                """
                INSERT INTO rendez_vous
                    (patient_id, date_rdv, heure_rdv, motif, statut)
                VALUES (?, ?, ?, ?, 'prévu')
                """,
                (
                    patient_id,
                    valeurs["date_rdv"],
                    valeurs["heure_rdv"],
                    valeur_ou_none(valeurs["motif"]),
                ),
            )
            connexion.commit()
            connexion.close()
            return redirect(f"/patients/{patient_id}")
    else:
        valeurs = {
            "patient_id": request.args.get("patient_id", ""),
            "date_rdv": "",
            "heure_rdv": "",
            "motif": "",
        }
        erreur = None

    patients, _ = patients_et_rendez_vous(connexion)
    connexion.close()
    contenu = formulaire_rendez_vous(
        valeurs, patients, erreur, action="/rendez-vous/nouveau"
    )
    return page("Nouveau rendez-vous", contenu)


@app.route("/rendez-vous/<int:rendez_vous_id>/modifier", methods=["GET", "POST"])
def modifier_rendez_vous(rendez_vous_id):
    connexion = se_connecter_a_la_base()
    rendez_vous = connexion.execute(
        "SELECT * FROM rendez_vous WHERE id = ?", (rendez_vous_id,)
    ).fetchone()
    if rendez_vous is None:
        connexion.close()
        abort(404)

    if request.method == "POST":
        valeurs, erreur, patient_id = valider_rendez_vous(
            connexion, request.form, edition=True
        )
        if erreur is None:
            connexion.execute(
                """
                UPDATE rendez_vous
                SET patient_id = ?, date_rdv = ?, heure_rdv = ?,
                    motif = ?, statut = ?
                WHERE id = ?
                """,
                (
                    patient_id,
                    valeurs["date_rdv"],
                    valeurs["heure_rdv"],
                    valeur_ou_none(valeurs["motif"]),
                    valeurs["statut"],
                    rendez_vous_id,
                ),
            )
            connexion.commit()
            connexion.close()
            return redirect("/rendez-vous")
    else:
        valeurs = {
            "patient_id": rendez_vous["patient_id"],
            "date_rdv": rendez_vous["date_rdv"],
            "heure_rdv": rendez_vous["heure_rdv"],
            "motif": rendez_vous["motif"] or "",
            "statut": rendez_vous["statut"],
        }
        erreur = None

    patients, _ = patients_et_rendez_vous(connexion)
    connexion.close()
    contenu = formulaire_rendez_vous(
        valeurs,
        patients,
        erreur,
        action=f"/rendez-vous/{rendez_vous_id}/modifier",
        edition=True,
    )
    return page("Modifier le rendez-vous", contenu)


@app.route("/rendez-vous/<int:rendez_vous_id>/supprimer", methods=["POST"])
def supprimer_rendez_vous(rendez_vous_id):
    connexion = se_connecter_a_la_base()
    rendez_vous = connexion.execute(
        "SELECT 1 FROM rendez_vous WHERE id = ?", (rendez_vous_id,)
    ).fetchone()
    if rendez_vous is None:
        connexion.close()
        abort(404)

    connexion.execute(
        "UPDATE consultations SET rendez_vous_id = NULL WHERE rendez_vous_id = ?",
        (rendez_vous_id,),
    )
    connexion.execute("DELETE FROM rendez_vous WHERE id = ?", (rendez_vous_id,))
    connexion.commit()
    connexion.close()
    return redirect("/rendez-vous")


@app.route("/consultations")
def liste_consultations():
    medecin = request.args.get("medecin", "").strip()

    connexion = se_connecter_a_la_base()
    medecins = [
        ligne["medecin"]
        for ligne in connexion.execute(
            """
            SELECT DISTINCT medecin FROM consultations
            WHERE medecin IS NOT NULL AND TRIM(medecin) <> ''
            ORDER BY medecin
            """
        ).fetchall()
    ]
    if medecin and medecin not in medecins:
        medecins.append(medecin)
        medecins.sort()

    requete = """
        SELECT c.id, c.date_consultation, c.medecin,
               p.id AS patient_id, p.nom, p.prenom
        FROM consultations AS c
        JOIN patients AS p ON p.id = c.patient_id
    """
    parametres = ()
    if medecin:
        requete += " WHERE c.medecin = ?"
        parametres = (medecin,)
    requete += " ORDER BY c.date_consultation, c.id"

    consultations = connexion.execute(requete, parametres).fetchall()
    connexion.close()

    options = ['<option value="">Tous les médecins</option>']
    for valeur in medecins:
        selection = " selected" if valeur == medecin else ""
        options.append(
            f'<option value="{escape(valeur)}"{selection}>{escape(valeur)}</option>'
        )
    filtre = (
        '<form method="get" action="/consultations" class="actions">'
        '<label for="medecin">Médecin :</label> '
        '<select id="medecin" name="medecin">'
        f'{"".join(options)}</select>'
        '<button type="submit" class="bouton">Filtrer</button>'
        "</form>"
    )

    if consultations:
        lignes = "".join(
            f"<tr>"
            f'<td><a href="/consultations/{consultation["id"]}">'
            f'{escape(consultation["nom"])} {escape(consultation["prenom"])}</a></td>'
            f'<td>{afficher(consultation["medecin"])}</td>'
            f'<td>{consultation["date_consultation"]}</td>'
            f"</tr>"
            for consultation in consultations
        )
        tableau = (
            "<table><thead><tr><th>Patient</th><th>Médecin</th>"
            f"<th>Date</th></tr></thead><tbody>{lignes}</tbody></table>"
        )
    elif medecin:
        tableau = "<p>Aucun compte-rendu pour ce médecin.</p>"
    else:
        tableau = "<p>Aucun compte-rendu enregistré.</p>"

    contenu = (
        '<div class="actions">'
        '<a class="bouton" href="/consultations/nouveau">'
        "Rédiger un compte-rendu</a></div>"
        f"{filtre}{tableau}"
    )
    return page("Consultations", contenu)


@app.route("/consultations/nouveau", methods=["GET", "POST"])
def nouveau_compte_rendu():
    connexion = se_connecter_a_la_base()

    if request.method == "POST":
        valeurs, erreur, patient_id, rendez_vous_id = valider_consultation(
            connexion, request.form
        )
        if erreur is None:
            connexion.execute(
                """
                INSERT INTO consultations
                    (patient_id, rendez_vous_id, date_consultation, motif,
                     observations, diagnostic, traitement, medecin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    rendez_vous_id,
                    valeurs["date_consultation"],
                    valeur_ou_none(valeurs["motif"]),
                    valeur_ou_none(valeurs["observations"]),
                    valeur_ou_none(valeurs["diagnostic"]),
                    valeur_ou_none(valeurs["traitement"]),
                    valeur_ou_none(valeurs["medecin"]),
                ),
            )
            connexion.commit()
            connexion.close()
            return redirect("/consultations")
    else:
        valeurs = {nom: "" for nom, _, _ in CHAMPS_CONSULTATION}
        valeurs["patient_id"] = request.args.get("patient_id", "")
        valeurs["rendez_vous_id"] = request.args.get("rendez_vous_id", "")
        valeurs["date_consultation"] = date.today().isoformat()
        erreur = None

    patients, rendez_vous = patients_et_rendez_vous(connexion)
    connexion.close()
    contenu = formulaire_consultation(
        valeurs,
        patients,
        rendez_vous,
        erreur,
        action="/consultations/nouveau",
    )
    return page("Nouveau compte-rendu", contenu)


@app.route("/consultations/<int:consultation_id>")
def detail_consultation(consultation_id):
    connexion = se_connecter_a_la_base()
    consultation = connexion.execute(
        """
        SELECT c.*, p.nom, p.prenom
        FROM consultations AS c
        JOIN patients AS p ON p.id = c.patient_id
        WHERE c.id = ?
        """,
        (consultation_id,),
    ).fetchone()
    if consultation is None:
        connexion.close()
        abort(404)

    rendez_vous = None
    if consultation["rendez_vous_id"] is not None:
        rendez_vous = connexion.execute(
            "SELECT * FROM rendez_vous WHERE id = ?",
            (consultation["rendez_vous_id"],),
        ).fetchone()
    connexion.close()

    if rendez_vous is not None:
        ligne_rdv = (
            f"<p><strong>Rendez-vous :</strong> "
            f'{rendez_vous["date_rdv"]} à {rendez_vous["heure_rdv"]}</p>'
        )
    else:
        ligne_rdv = "<p><strong>Rendez-vous :</strong> —</p>"

    contenu = (
        f'<p><strong>Patient :</strong> '
        f'<a href="/patients/{consultation["patient_id"]}">'
        f'{escape(consultation["nom"])} {escape(consultation["prenom"])}</a></p>'
        f'<p><strong>Médecin :</strong> {afficher(consultation["medecin"])}</p>'
        f'<p><strong>Date :</strong> {consultation["date_consultation"]}</p>'
        f"{ligne_rdv}"
        f'<h2>Compte-rendu</h2>'
        f'<p><strong>Motif :</strong></p>'
        f'<div class="texte">{afficher(consultation["motif"])}</div>'
        f'<p><strong>Observations :</strong></p>'
        f'<div class="texte">{afficher(consultation["observations"])}</div>'
        f'<p><strong>Diagnostic :</strong></p>'
        f'<div class="texte">{afficher(consultation["diagnostic"])}</div>'
        f'<p><strong>Traitement :</strong></p>'
        f'<div class="texte">{afficher(consultation["traitement"])}</div>'
        '<div class="actions">'
        f'<a class="bouton" href="/consultations/{consultation_id}/modifier">'
        "Modifier ce compte-rendu</a></div>"
    )
    return page("Compte-rendu de consultation", contenu)


@app.route("/consultations/<int:consultation_id>/modifier", methods=["GET", "POST"])
def modifier_compte_rendu(consultation_id):
    connexion = se_connecter_a_la_base()
    consultation = connexion.execute(
        "SELECT * FROM consultations WHERE id = ?", (consultation_id,)
    ).fetchone()
    if consultation is None:
        connexion.close()
        abort(404)

    if request.method == "POST":
        valeurs, erreur, patient_id, rendez_vous_id = valider_consultation(
            connexion, request.form
        )
        if erreur is None:
            connexion.execute(
                """
                UPDATE consultations
                SET patient_id = ?, rendez_vous_id = ?, date_consultation = ?,
                    motif = ?, observations = ?, diagnostic = ?,
                    traitement = ?, medecin = ?
                WHERE id = ?
                """,
                (
                    patient_id,
                    rendez_vous_id,
                    valeurs["date_consultation"],
                    valeur_ou_none(valeurs["motif"]),
                    valeur_ou_none(valeurs["observations"]),
                    valeur_ou_none(valeurs["diagnostic"]),
                    valeur_ou_none(valeurs["traitement"]),
                    valeur_ou_none(valeurs["medecin"]),
                    consultation_id,
                ),
            )
            connexion.commit()
            connexion.close()
            return redirect(f"/consultations/{consultation_id}")
    else:
        valeurs = {
            nom: consultation[nom] if consultation[nom] is not None else ""
            for nom, _, _ in CHAMPS_CONSULTATION
        }
        erreur = None

    patients, rendez_vous = patients_et_rendez_vous(connexion)
    connexion.close()
    contenu = formulaire_consultation(
        valeurs,
        patients,
        rendez_vous,
        erreur,
        action=f"/consultations/{consultation_id}/modifier",
    )
    return page("Modifier le compte-rendu", contenu)


if __name__ == "__main__":
    app.run(debug=True)
