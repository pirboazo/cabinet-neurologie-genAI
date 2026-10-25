"""
Application Flask — Gestion de cabinet de neurologie
Voir SPECIFICATION.md pour le comportement attendu.
"""

from __future__ import annotations

import sqlite3
from datetime import date, time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import Flask, abort, redirect, request, url_for
from markupsafe import escape

app = Flask(__name__)

# Menu principal
PAGES: List[Tuple[str, str]] = [
    ("/patients", "Patients"),
    ("/rendez-vous", "Rendez-vous"),
    ("/consultations", "Consultations"),
]

# Constantes de formulaires
CHAMPS_PATIENT = [
    ("nom", "Nom"),
    ("prenom", "Prénom"),
    ("date_naissance", "Date de naissance"),
    ("sexe", "Sexe"),
    ("telephone", "Téléphone"),
    ("email", "Email"),
    ("adresse", "Adresse"),
    ("antecedents", "Antécédents"),
]
SEXES = ["", "F", "M", "Autre"]

CHAMPS_RDV = ["patient_id", "date_rdv", "heure_rdv", "motif", "statut"]
STATUTS_RDV = ["prévu", "honoré", "annulé"]

CHAMPS_CONSULTATION = [
    "patient_id",
    "rendez_vous_id",
    "date_consultation",
    "motif",
    "observations",
    "diagnostic",
    "traitement",
    "medecin",
]


def se_connecter_a_la_base() -> sqlite3.Connection:
    connexion = sqlite3.connect("database/cabinet.db")
    connexion.row_factory = sqlite3.Row
    return connexion


def menu(actif: str) -> str:
    items = []
    for href, libelle in PAGES:
        cls = "actif" if href == actif else ""
        items.append(f'<a class="bouton {cls}" href="{href}">{escape(libelle)}</a>')
    return "<nav>" + "".join(items) + "</nav>"


def page(titre: str, contenu: str, onglet: str) -> str:
    # CSS inline minimal commun à toutes les pages
    css = """
    <style>
    :root {
        --gris: #555;
        --gris-actif: #333;
        --bleu: #0066cc;
        --rouge: #cc0000;
        --bord: #ddd;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji", sans-serif; background: #fff; color: #111; }
    nav { padding: 12px; border-bottom: 1px solid var(--bord); display: flex; gap: 8px; }
    nav .bouton { background: var(--gris); color: #fff; text-decoration: none; padding: 8px 12px; border-radius: 6px; font-weight: 600; }
    nav .bouton.actif { background: var(--gris-actif); }
    main { max-width: 1000px; margin: 24px auto; padding: 0 16px 48px; }
    h1 { font-size: 24px; margin: 0 0 16px 0; }
    h2 { font-size: 18px; margin: 24px 0 8px 0; }
    .boutons { margin: 12px 0 20px; display: flex; flex-wrap: wrap; gap: 8px; }
    a.bouton, button.bouton { display: inline-block; background: var(--bleu); color: #fff; text-decoration: none; padding: 8px 12px; border-radius: 6px; font-weight: 600; border: none; cursor: pointer; }
    .danger { background: var(--rouge) !important; }
    .muted { color: #666; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0 16px; }
    th, td { border-bottom: 1px solid var(--bord); text-align: left; padding: 8px; vertical-align: top; }
    th { background: #f7f7f7; }
    form .champ { margin: 10px 0; display: flex; flex-direction: column; }
    form label { font-weight: 600; margin-bottom: 4px; }
    form input[type="text"], form input[type="date"], form input[type="time"], form input[type="email"], form input[type="tel"], form select, form textarea {
        width: 100%; padding: 8px; border: 1px solid var(--bord); border-radius: 6px; font: inherit;
    }
    form textarea { min-height: 90px; }
    .erreur { padding: 10px 12px; border: 1px solid #f3c2c2; background: #fff3f3; color: #900; border-radius: 6px; margin: 10px 0; }
    .sections { display: grid; grid-template-columns: 1fr; gap: 20px; }
    @media (min-width: 900px) { .sections { grid-template-columns: 1fr 1fr; } }
    .vide { padding: 10px; border: 1px dashed var(--bord); color: #666; border-radius: 6px; }
    .tag { display:inline-block; padding:2px 6px; border-radius:4px; background:#eef; border:1px solid #cde; color:#225; font-size:12px; }
    </style>
    """
    head = f"<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>{css}<title>{escape(titre)}</title></head>"
    body = f"<body>{menu(onglet)}<main><h1>{escape(titre)}</h1>{contenu}</main></body></html>"
    return head + body


# -------------------- Helpers validation --------------------
def _strp_date(val: str) -> Optional[str]:
    if not val:
        return None
    try:
        # Valide AAAA-MM-JJ
        date.fromisoformat(val)
        return val
    except ValueError:
        return None


def _strp_heure(val: str) -> Optional[str]:
    if not val:
        return None
    try:
        # Python accepte HH:MM[:SS]; on force HH:MM.
        t = time.fromisoformat(val)
        return f"{t.hour:02d}:{t.minute:02d}"
    except ValueError:
        return None


def _champ(form: Dict[str, str], cle: str) -> str:
    return (form.get(cle) or "").strip()


def _existe_patient(conn: sqlite3.Connection, patient_id: int) -> bool:
    cur = conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,))
    return cur.fetchone() is not None


def _existe_rdv(conn: sqlite3.Connection, rdv_id: int) -> bool:
    cur = conn.execute("SELECT 1 FROM rendez_vous WHERE id = ?", (rdv_id,))
    return cur.fetchone() is not None


def _rdv_appartient_a_patient(conn: sqlite3.Connection, rdv_id: int, patient_id: int) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM rendez_vous WHERE id = ? AND patient_id = ?", (rdv_id, patient_id)
    )
    return cur.fetchone() is not None


# -------------------- Formulaire Patients --------------------
def valeurs_depuis_formulaire_patient(form: Dict[str, str]) -> Dict[str, Optional[str]]:
    vals: Dict[str, Optional[str]] = {}
    for cle, _ in CHAMPS_PATIENT:
        vals[cle] = _champ(form, cle)
    # Normalisation vide -> None à l'écriture (sera géré à l'INSERT/UPDATE)
    return vals


def erreur_formulaire_patient(vals: Dict[str, Optional[str]]) -> Optional[str]:
    nom = (vals.get("nom") or "").strip()
    prenom = (vals.get("prenom") or "").strip()
    if not nom or not prenom:
        return "Le nom et le prénom sont obligatoires."
    dn = vals.get("date_naissance") or ""
    if dn and not _strp_date(dn):
        return "La date de naissance n'est pas valide."
    sexe = vals.get("sexe") or ""
    if sexe not in SEXES:
        return "La valeur choisie pour le sexe n'est pas valide."
    return None


def formulaire_patient(action: str, valeurs: Dict[str, Optional[str]], erreur: Optional[str] = None) -> str:
    def v(cle: str) -> str:
        return escape(valeurs.get(cle) or "")

    options_sexe = "".join(
        f'<option value="{escape(val)}" {"selected" if (valeurs.get("sexe") or "")==val else ""}>{escape(val or "— Non précisé —")}</option>'
        for val in SEXES
    )
    bloc_erreur = f'<div class="erreur">{escape(erreur)}</div>' if erreur else ""
    html = [
        bloc_erreur,
        f'<form method="post" action="{escape(action)}">',
        '<div class="champ"><label>Nom</label><input type="text" name="nom" value="' + v("nom") + '"></div>',
        '<div class="champ"><label>Prénom</label><input type="text" name="prenom" value="' + v("prenom") + '"></div>',
        '<div class="champ"><label>Date de naissance</label><input type="date" name="date_naissance" value="' + v("date_naissance") + '"></div>',
        f'<div class="champ"><label>Sexe</label><select name="sexe">{options_sexe}</select></div>',
        '<div class="champ"><label>Téléphone</label><input type="tel" name="telephone" value="' + v("telephone") + '"></div>',
        '<div class="champ"><label>Email</label><input type="email" name="email" value="' + v("email") + '"></div>',
        '<div class="champ"><label>Adresse</label><textarea name="adresse">' + v("adresse") + "</textarea></div>",
        '<div class="champ"><label>Antécédents</label><textarea name="antecedents">' + v("antecedents") + "</textarea></div>",
        '<div class="champ"><button class="bouton" type="submit">Enregistrer</button></div>',
        "</form>",
    ]
    return "".join(html)


# -------------------- Formulaire Rendez-vous --------------------
def valider_rendez_vous(conn: sqlite3.Connection, form: Dict[str, str], edition: bool = False) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    vals: Dict[str, Optional[str]] = {}
    pid_raw = _champ(form, "patient_id")
    try:
        pid = int(pid_raw)
    except ValueError:
        pid = 0
    if pid <= 0 or not _existe_patient(conn, pid):
        return {}, "Merci de choisir un patient."
    vals["patient_id"] = str(pid)

    d = _strp_date(_champ(form, "date_rdv"))
    h = _strp_heure(_champ(form, "heure_rdv"))
    if not d or not h:
        return {}, "Merci de saisir une date et une heure valides."
    vals["date_rdv"] = d
    vals["heure_rdv"] = h

    vals["motif"] = _champ(form, "motif")

    if edition:
        st = _champ(form, "statut")
        if st not in STATUTS_RDV:
            return {}, "Le statut choisi n'est pas valide."
        vals["statut"] = st
    else:
        vals["statut"] = "prévu"

    return vals, None


def formulaire_rendez_vous(
    conn: sqlite3.Connection,
    action: str,
    valeurs: Dict[str, Optional[str]],
    erreur: Optional[str] = None,
    edition: bool = False,
) -> str:
    # Liste des patients
    patients = conn.execute("SELECT id, nom, prenom FROM patients ORDER BY nom, prenom").fetchall()
    pid_sel = (valeurs.get("patient_id") or "")
    opts_patients = ['<option value="">— Choisir un patient —</option>']
    for p in patients:
        sel = " selected" if str(p["id"]) == str(pid_sel) else ""
        opts_patients.append(f'<option value="{p["id"]}"{sel}>{escape(p["nom"])} {escape(p["prenom"])}</option>')
    bloc_erreur = f'<div class="erreur">{escape(erreur)}</div>' if erreur else ""
    statut_select = ""
    if edition:
        options_statut = "".join(
            f'<option value="{escape(s)}" {"selected" if (valeurs.get("statut") or "")==s else ""}>{escape(s)}</option>'
            for s in STATUTS_RDV
        )
        statut_select = f'<div class="champ"><label>Statut</label><select name="statut">{options_statut}</select></div>'
    html = [
        bloc_erreur,
        f'<form method="post" action="{escape(action)}">',
        f'<div class="champ"><label>Patient</label><select name="patient_id">{"".join(opts_patients)}</select></div>',
        f'<div class="champ"><label>Date</label><input type="date" name="date_rdv" value="{escape(valeurs.get("date_rdv") or "")}"></div>',
        f'<div class="champ"><label>Heure</label><input type="time" name="heure_rdv" value="{escape(valeurs.get("heure_rdv") or "")}"></div>',
        f'<div class="champ"><label>Motif (facultatif)</label><input type="text" name="motif" value="{escape(valeurs.get("motif") or "")}"></div>',
        statut_select,
        '<div class="champ"><button class="bouton" type="submit">Enregistrer</button></div>',
        "</form>",
    ]
    return "".join(html)


def boutons_rdv(rdv_id: int) -> str:
    # Modifier (GET) + Supprimer (POST + confirm)
    form_suppr = (
        f'<form method="post" action="{url_for("supprimer_rendez_vous", id=rdv_id)}" style="display:inline;" '
        'onsubmit="return confirm(\'Supprimer ce rendez-vous ? Cette action est irréversible.\');">'
        '<button class="bouton danger" type="submit">Supprimer</button></form>'
    )
    return (
        f'<a class="bouton" href="{url_for("modifier_rendez_vous", id=rdv_id)}">Modifier</a> ' + form_suppr
    )


# -------------------- Formulaire Consultation --------------------
def patients_et_rendez_vous(conn: sqlite3.Connection, patient_id: Optional[int]) -> Tuple[List[sqlite3.Row], List[sqlite3.Row]]:
    pats = conn.execute("SELECT id, nom, prenom FROM patients ORDER BY nom, prenom").fetchall()
    rdvs: List[sqlite3.Row] = []
    if patient_id:
        rdvs = conn.execute(
            "SELECT id, date_rdv, heure_rdv, motif FROM rendez_vous WHERE patient_id = ? ORDER BY date_rdv, heure_rdv",
            (patient_id,),
        ).fetchall()
    return pats, rdvs


def valider_consultation(conn: sqlite3.Connection, form: Dict[str, str]) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    vals: Dict[str, Optional[str]] = {}
    pid_raw = _champ(form, "patient_id")
    try:
        pid = int(pid_raw)
    except ValueError:
        pid = 0
    if pid <= 0 or not _existe_patient(conn, pid):
        return {}, "Merci de choisir un patient."
    vals["patient_id"] = str(pid)

    d = _strp_date(_champ(form, "date_consultation"))
    if not d:
        return {}, "Merci de saisir une date valide."
    vals["date_consultation"] = d

    rdv_raw = _champ(form, "rendez_vous_id")
    if not rdv_raw:
        vals["rendez_vous_id"] = None
    else:
        try:
            rdv_id = int(rdv_raw)
        except ValueError:
            return {}, "Le rendez-vous choisi n'existe pas."
        if not _existe_rdv(conn, rdv_id):
            return {}, "Le rendez-vous choisi n'existe pas."
        if not _rdv_appartient_a_patient(conn, rdv_id, pid):
            return {}, "Le rendez-vous choisi n'appartient pas à ce patient."
        vals["rendez_vous_id"] = str(rdv_id)

    # Champs libres
    for cle in ("motif", "observations", "diagnostic", "traitement", "medecin"):
        vals[cle] = _champ(form, cle)
    return vals, None


def formulaire_consultation(
    conn: sqlite3.Connection,
    action: str,
    valeurs: Dict[str, Optional[str]],
    erreur: Optional[str] = None,
) -> str:
    # Patients
    pid_sel = int(valeurs.get("patient_id") or 0) if (valeurs.get("patient_id") or "").isdigit() else None
    pats, rdvs = patients_et_rendez_vous(conn, pid_sel)
    opts_pats = ['<option value="">— Choisir un patient —</option>']
    for p in pats:
        sel = " selected" if str(p["id"]) == str(valeurs.get("patient_id") or "") else ""
        opts_pats.append(f'<option value="{p["id"]}"{sel}>{escape(p["nom"])} {escape(p["prenom"])}</option>')
    # RDV de ce patient seulement (sinon vide)
    opts_rdvs: List[str] = ['<option value="">— Aucun —</option>']
    for r in rdvs:
        lib = f'{r["date_rdv"]} {r["heure_rdv"]} — {r["motif"] or ""}'
        sel = " selected" if str(r["id"]) == str(valeurs.get("rendez_vous_id") or "") else ""
        opts_rdvs.append(f'<option value="{r["id"]}"{sel}>{escape(lib)}</option>')
    bloc_erreur = f'<div class="erreur">{escape(erreur)}</div>' if erreur else ""
    html = [
        bloc_erreur,
        f'<form method="post" action="{escape(action)}">',
        f'<div class="champ"><label>Patient</label><select name="patient_id">{"".join(opts_pats)}</select></div>',
        f'<div class="champ"><label>Date</label><input type="date" name="date_consultation" value="{escape(valeurs.get("date_consultation") or str(date.today()))}"></div>',
        f'<div class="champ"><label>Rendez-vous lié (facultatif)</label><select name="rendez_vous_id">{"".join(opts_rdvs)}</select></div>',
        f'<div class="champ"><label>Motif (facultatif)</label><input type="text" name="motif" value="{escape(valeurs.get("motif") or "")}"></div>',
        f'<div class="champ"><label>Observations</label><textarea name="observations">{escape(valeurs.get("observations") or "")}</textarea></div>',
        f'<div class="champ"><label>Diagnostic</label><textarea name="diagnostic">{escape(valeurs.get("diagnostic") or "")}</textarea></div>',
        f'<div class="champ"><label>Traitement</label><textarea name="traitement">{escape(valeurs.get("traitement") or "")}</textarea></div>',
        f'<div class="champ"><label>Médecin (facultatif)</label><input type="text" name="medecin" value="{escape(valeurs.get("medecin") or "")}"></div>',
        '<div class="champ"><button class="bouton" type="submit">Enregistrer</button></div>',
        "</form>",
    ]
    return "".join(html)


# -------------------- Routes --------------------
@app.get("/")
def accueil():
    return redirect(url_for("liste_patients"))


@app.get("/patients")
def liste_patients():
    conn = se_connecter_a_la_base()
    patients = conn.execute(
        "SELECT id, nom, prenom, date_naissance FROM patients ORDER BY nom, prenom"
    ).fetchall()
    conn.close()
    lignes = []
    for p in patients:
        lien = f'<a href="{url_for("fiche_patient", id=p["id"])}">{escape(p["nom"])} {escape(p["prenom"])}</a>'
        dn = p["date_naissance"] or "—"
        lignes.append(f"<tr><td>{lien}</td><td>{dn}</td></tr>")
    contenu = [
        '<div class="boutons"><a class="bouton" href="/patients/nouveau">Ajouter un patient</a></div>',
        '<table><thead><tr><th>Nom – Prénom</th><th>Date de naissance</th></tr></thead><tbody>',
        "".join(lignes) or '<tr><td colspan="2" class="muted">Aucun patient enregistré.</td></tr>',
        "</tbody></table>",
    ]
    return page("Liste des patients", "".join(contenu), "/patients")


@app.route("/patients/nouveau", methods=["GET", "POST"])
def nouveau_patient():
    if request.method == "GET":
        vals = {k: "" for k, _ in CHAMPS_PATIENT}
        return page("Nouveau patient", formulaire_patient("/patients/nouveau", vals), "/patients")
    # POST
    vals = valeurs_depuis_formulaire_patient(request.form)  # type: ignore[arg-type]
    erreur = erreur_formulaire_patient(vals)
    if erreur:
        return page("Nouveau patient", formulaire_patient("/patients/nouveau", vals, erreur), "/patients")
    # Ecriture
    conn = se_connecter_a_la_base()
    champs = [k for k, _ in CHAMPS_PATIENT]
    valeurs: List[Optional[str]] = []
    for c in champs:
        v = (vals.get(c) or "").strip()
        valeurs.append(v or None)
    placeholders = ",".join("?" for _ in champs)
    conn.execute(f"INSERT INTO patients ({','.join(champs)}) VALUES ({placeholders})", valeurs)
    nouveau_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return redirect(url_for("fiche_patient", id=nouveau_id))


@app.get("/patients/<int:id>")
def fiche_patient(id: int):
    conn = se_connecter_a_la_base()
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (id,)).fetchone()
    if not p:
        conn.close()
        abort(404)
    rdvs = conn.execute(
        "SELECT * FROM rendez_vous WHERE patient_id = ? ORDER BY date_rdv, heure_rdv", (id,)
    ).fetchall()
    crs = conn.execute(
        "SELECT id, date_consultation, medecin, motif FROM consultations WHERE patient_id = ? ORDER BY date_consultation",
        (id,),
    ).fetchall()
    conn.close()
    # Identité
    ident = [
        "<div>",
        f"<div><strong>Nom</strong> : {escape(p['nom'])} {escape(p['prenom'])}</div>",
        f"<div><strong>Date de naissance</strong> : {p['date_naissance'] or '—'}</div>",
        f"<div><strong>Sexe</strong> : {escape(p['sexe'] or '—')}</div>",
        f"<div><strong>Téléphone</strong> : {escape(p['telephone'] or '—')}</div>",
        f"<div><strong>Email</strong> : {escape(p['email'] or '—')}</div>",
        f"<div><strong>Adresse</strong> : {escape(p['adresse'] or '—')}</div>",
        f"<div><strong>Antécédents</strong> : {escape(p['antecedents'] or '—')}</div>",
        "</div>",
    ]
    actions = [
        '<div class="boutons">',
        f'<a class="bouton" href="{url_for("nouveau_rendez_vous")}?patient_id={p["id"]}">Prendre un rendez-vous</a>',
        f'<a class="bouton" href="{url_for("modifier_patient", id=p["id"])}">Modifier le patient</a>',
        f'<a class="bouton" href="{url_for("nouveau_compte_rendu")}?patient_id={p["id"]}">Rédiger un compte-rendu</a>',
        "</div>",
    ]
    # RDV
    lignes_rdvs = []
    for r in rdvs:
        lib = f'{r["date_rdv"]} {r["heure_rdv"]}'
        motif = escape(r["motif"] or "—")
        statut = r["statut"] or "—"
        actions_r = boutons_rdv(r["id"])
        lignes_rdvs.append(
            f"<tr><td>{lib}</td><td>{motif}</td><td><span class='tag'>{statut}</span></td><td>{actions_r}</td></tr>"
        )
    bloc_rdvs = "".join(
        [
            "<h2>Rendez-vous</h2>",
            '<table><thead><tr><th>Date/heure</th><th>Motif</th><th>Statut</th><th>Actions</th></tr></thead><tbody>',
            "".join(lignes_rdvs) or '<tr><td colspan="4" class="muted">Aucun rendez-vous pour ce patient.</td></tr>',
            "</tbody></table>",
        ]
    )
    # Comptes-rendus
    lignes_cr = []
    for c in crs:
        lien = f'<a href="{url_for("detail_consultation", id=c["id"])}">Voir</a>'
        modif = f'<a class="bouton" href="{url_for("modifier_compte_rendu", id=c["id"])}">Modifier</a>'
        lignes_cr.append(
            f"<tr><td>{c['date_consultation']}</td><td>{escape(c['medecin'] or '—')}</td><td>{escape(c['motif'] or '—')}</td><td>{lien} {modif}</td></tr>"
        )
    bloc_cr = "".join(
        [
            "<h2>Comptes-rendus de consultation</h2>",
            '<table><thead><tr><th>Date</th><th>Médecin</th><th>Motif</th><th>Actions</th></tr></thead><tbody>',
            "".join(lignes_cr) or '<tr><td colspan="4" class="muted">Aucun compte-rendu pour ce patient.</td></tr>',
            "</tbody></table>",
        ]
    )
    contenu = "".join(ident + actions + ['<div class="sections">', f"<section>{bloc_rdvs}</section>", f"<section>{bloc_cr}</section>", "</div>"])
    return page(f"Fiche patient — {p['prenom']} {p['nom']}", contenu, "/patients")


@app.route("/patients/<int:id>/modifier", methods=["GET", "POST"])
def modifier_patient(id: int):
    conn = se_connecter_a_la_base()
    p = conn.execute("SELECT * FROM patients WHERE id = ?", (id,)).fetchone()
    if not p:
        conn.close()
        abort(404)
    if request.method == "GET":
        vals = {k: p[k] for k, _ in CHAMPS_PATIENT}
        conn.close()
        return page("Modifier le patient", formulaire_patient(f"/patients/{id}/modifier", vals), "/patients")
    # POST
    vals = valeurs_depuis_formulaire_patient(request.form)  # type: ignore[arg-type]
    erreur = erreur_formulaire_patient(vals)
    if erreur:
        conn.close()
        return page("Modifier le patient", formulaire_patient(f"/patients/{id}/modifier", vals, erreur), "/patients")
    champs = [k for k, _ in CHAMPS_PATIENT]
    valeurs: List[Optional[str]] = []
    for c in champs:
        v = (vals.get(c) or "").strip()
        valeurs.append(v or None)
    set_clause = ", ".join(f"{c} = ?" for c in champs)
    conn.execute(f"UPDATE patients SET {set_clause} WHERE id = ?", (*valeurs, id))
    conn.commit()
    conn.close()
    return redirect(url_for("fiche_patient", id=id))


@app.get("/rendez-vous")
def liste_rendez_vous():
    conn = se_connecter_a_la_base()
    rdvs = conn.execute(
        """
        SELECT r.id, r.date_rdv, r.heure_rdv, r.motif, r.statut,
               p.id AS patient_id, p.nom, p.prenom
        FROM rendez_vous AS r
        JOIN patients AS p ON r.patient_id = p.id
        ORDER BY r.date_rdv, r.heure_rdv
        """
    ).fetchall()
    conn.close()
    lignes = []
    for r in rdvs:
        p_lien = f'<a href="{url_for("fiche_patient", id=r["patient_id"])}">{escape(r["prenom"])} {escape(r["nom"])}</a>'
        actions_r = boutons_rdv(r["id"])
        lignes.append(
            f"<tr><td>{r['date_rdv']}</td><td>{r['heure_rdv']}</td><td>{p_lien}</td><td>{escape(r['motif'] or '—')}</td><td>{r['statut'] or '—'}</td><td>{actions_r}</td></tr>"
        )
    contenu = [
        '<div class="boutons"><a class="bouton" href="/rendez-vous/nouveau">Nouveau rendez-vous</a></div>',
        '<table><thead><tr><th>Date</th><th>Heure</th><th>Patient</th><th>Motif</th><th>Statut</th><th>Actions</th></tr></thead><tbody>',
        "".join(lignes) or '<tr><td colspan="6" class="muted">Aucun rendez-vous.</td></tr>',
        "</tbody></table>",
    ]
    return page("Liste des rendez-vous", "".join(contenu), "/rendez-vous")


@app.route("/rendez-vous/nouveau", methods=["GET", "POST"])
def nouveau_rendez_vous():
    conn = se_connecter_a_la_base()
    if request.method == "GET":
        pid = request.args.get("patient_id", "", type=str)
        vals = {"patient_id": pid or "", "date_rdv": "", "heure_rdv": "", "motif": "", "statut": "prévu"}
        contenu = formulaire_rendez_vous(conn, "/rendez-vous/nouveau", vals, edition=False)
        conn.close()
        return page("Nouveau rendez-vous", contenu, "/rendez-vous")
    # POST
    vals, err = valider_rendez_vous(conn, request.form, edition=False)  # type: ignore[arg-type]
    if err:
        contenu = formulaire_rendez_vous(conn, "/rendez-vous/nouveau", request.form, err, edition=False)  # type: ignore[arg-type]
        conn.close()
        return page("Nouveau rendez-vous", contenu, "/rendez-vous")
    conn.execute(
        "INSERT INTO rendez_vous (patient_id, date_rdv, heure_rdv, motif, statut) VALUES (?, ?, ?, ?, 'prévu')",
        (int(vals["patient_id"] or "0"), vals["date_rdv"], vals["heure_rdv"], (vals["motif"] or None)),
    )
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Redirection vers la fiche du patient
    pid = int(vals["patient_id"] or "0")
    conn.commit()
    conn.close()
    return redirect(url_for("fiche_patient", id=pid))


@app.route("/rendez-vous/<int:id>/modifier", methods=["GET", "POST"])
def modifier_rendez_vous(id: int):
    conn = se_connecter_a_la_base()
    r = conn.execute("SELECT * FROM rendez_vous WHERE id = ?", (id,)).fetchone()
    if not r:
        conn.close()
        abort(404)
    if request.method == "GET":
        vals = {
            "patient_id": str(r["patient_id"]),
            "date_rdv": r["date_rdv"],
            "heure_rdv": r["heure_rdv"],
            "motif": r["motif"] or "",
            "statut": r["statut"] or "prévu",
        }
        contenu = formulaire_rendez_vous(conn, f"/rendez-vous/{id}/modifier", vals, edition=True)
        conn.close()
        return page("Modifier le rendez-vous", contenu, "/rendez-vous")
    # POST
    vals, err = valider_rendez_vous(conn, request.form, edition=True)  # type: ignore[arg-type]
    if err:
        contenu = formulaire_rendez_vous(conn, f"/rendez-vous/{id}/modifier", request.form, err, edition=True)  # type: ignore[arg-type]
        conn.close()
        return page("Modifier le rendez-vous", contenu, "/rendez-vous")
    conn.execute(
        "UPDATE rendez_vous SET patient_id = ?, date_rdv = ?, heure_rdv = ?, motif = ?, statut = ? WHERE id = ?",
        (
            int(vals["patient_id"] or "0"),
            vals["date_rdv"],
            vals["heure_rdv"],
            vals["motif"] or None,
            vals["statut"],
            id,
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("liste_rendez_vous"))


@app.post("/rendez-vous/<int:id>/supprimer")
def supprimer_rendez_vous(id: int):
    conn = se_connecter_a_la_base()
    r = conn.execute("SELECT id FROM rendez_vous WHERE id = ?", (id,)).fetchone()
    if not r:
        conn.close()
        abort(404)
    # Détacher les comptes-rendus liés
    conn.execute("UPDATE consultations SET rendez_vous_id = NULL WHERE rendez_vous_id = ?", (id,))
    # Supprimer le RDV
    conn.execute("DELETE FROM rendez_vous WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("liste_rendez_vous"))


@app.get("/consultations")
def liste_consultations():
    medecin_filtre = request.args.get("medecin", "", type=str)
    conn = se_connecter_a_la_base()
    # Valeurs distinctes non vides
    medecins = [
        r["medecin"]
        for r in conn.execute(
            "SELECT DISTINCT medecin FROM consultations WHERE medecin IS NOT NULL AND medecin <> '' ORDER BY medecin"
        ).fetchall()
    ]
    params: Tuple[Any, ...] = tuple()
    where = ""
    if medecin_filtre:
        where = "WHERE c.medecin = ?"
        params = (medecin_filtre,)
    crs = conn.execute(
        f"""
        SELECT c.id, c.date_consultation, c.medecin,
               p.nom, p.prenom
        FROM consultations AS c
        JOIN patients AS p ON c.patient_id = p.id
        {where}
        ORDER BY c.date_consultation
        """,
        params,
    ).fetchall()
    conn.close()
    # Filtre
    opts = ['<option value="">— Tous les médecins —</option>']
    for m in medecins:
        sel = " selected" if m == medecin_filtre else ""
        opts.append(f'<option value="{escape(m)}"{sel}>{escape(m)}</option>')
    filtre = [
        '<form method="get" action="/consultations" style="margin-bottom:12px; display:flex; gap:8px; align-items:center;">',
        '<label for="med">Filtrer par médecin</label>',
        f'<select id="med" name="medecin">{"".join(opts)}</select>',
        '<button class="bouton" type="submit">Filtrer</button>',
        "</form>",
    ]
    # Tableau
    lignes = []
    for c in crs:
        lien = f'<a href="{url_for("detail_consultation", id=c["id"])}">{escape(c["prenom"])} {escape(c["nom"])}</a>'
        lignes.append(f"<tr><td>{lien}</td><td>{escape(c['medecin'] or '—')}</td><td>{c['date_consultation']}</td></tr>")
    corps = "".join(lignes) or (
        '<tr><td colspan="3" class="muted">'
        + ("Aucun compte-rendu pour ce médecin." if medecin_filtre else "Aucun compte-rendu.")
        + "</td></tr>"
    )
    contenu = [
        '<div class="boutons"><a class="bouton" href="/consultations/nouveau">Nouveau compte-rendu</a></div>',
        *filtre,
        '<table><thead><tr><th>Patient</th><th>Médecin</th><th>Date</th></tr></thead><tbody>',
        corps,
        "</tbody></table>",
    ]
    return page("Comptes-rendus de consultation", "".join(contenu), "/consultations")


@app.route("/consultations/nouveau", methods=["GET", "POST"])
def nouveau_compte_rendu():
    conn = se_connecter_a_la_base()
    if request.method == "GET":
        pid = request.args.get("patient_id", "", type=str)
        rdv_id = request.args.get("rendez_vous_id", "", type=str)
        vals = {
            "patient_id": pid or "",
            "rendez_vous_id": rdv_id or "",
            "date_consultation": str(date.today()),
            "motif": "",
            "observations": "",
            "diagnostic": "",
            "traitement": "",
            "medecin": "",
        }
        contenu = formulaire_consultation(conn, "/consultations/nouveau", vals)
        conn.close()
        return page("Nouveau compte-rendu", contenu, "/consultations")
    # POST
    vals, err = valider_consultation(conn, request.form)  # type: ignore[arg-type]
    if err:
        contenu = formulaire_consultation(conn, "/consultations/nouveau", {**request.form}, err)  # type: ignore[arg-type]
        conn.close()
        return page("Nouveau compte-rendu", contenu, "/consultations")
    conn.execute(
        """
        INSERT INTO consultations (patient_id, rendez_vous_id, date_consultation, motif, observations, diagnostic, traitement, medecin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(vals["patient_id"] or "0"),
            (int(vals["rendez_vous_id"]) if vals["rendez_vous_id"] else None),
            vals["date_consultation"],
            vals["motif"] or None,
            vals["observations"] or None,
            vals["diagnostic"] or None,
            vals["traitement"] or None,
            vals["medecin"] or None,
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("liste_consultations"))


@app.get("/consultations/<int:id>")
def detail_consultation(id: int):
    conn = se_connecter_a_la_base()
    c = conn.execute(
        """
        SELECT c.*, p.nom, p.prenom,
               r.date_rdv AS rdv_date, r.heure_rdv AS rdv_heure
        FROM consultations AS c
        JOIN patients AS p ON c.patient_id = p.id
        LEFT JOIN rendez_vous AS r ON c.rendez_vous_id = r.id
        WHERE c.id = ?
        """,
        (id,),
    ).fetchone()
    if not c:
        conn.close()
        abort(404)
    conn.close()
    # Détail
    lignes = [
        f'<div><strong>Patient</strong> : <a href="{url_for("fiche_patient", id=c["patient_id"])}">{escape(c["prenom"])} {escape(c["nom"])}</a></div>',
        f"<div><strong>Médecin</strong> : {escape(c['medecin'] or '—')}</div>",
        f"<div><strong>Date</strong> : {c['date_consultation']}</div>",
    ]
    if c["rendez_vous_id"]:
        lignes.append(f"<div><strong>Rendez-vous lié</strong> : {c['rdv_date'] or '—'} {c['rdv_heure'] or ''}</div>")
    lignes += [
        f"<div><strong>Motif</strong> : {escape(c['motif'] or '—')}</div>",
        f"<div><strong>Observations</strong> : {escape(c['observations'] or '—')}</div>",
        f"<div><strong>Diagnostic</strong> : {escape(c['diagnostic'] or '—')}</div>",
        f"<div><strong>Traitement</strong> : {escape(c['traitement'] or '—')}</div>",
    ]
    actions = f'<div class="boutons"><a class="bouton" href="{url_for("modifier_compte_rendu", id=id)}">Modifier ce compte-rendu</a></div>'
    contenu = actions + "<div>" + "".join(lignes) + "</div>"
    return page("Détail du compte-rendu", contenu, "/consultations")


@app.route("/consultations/<int:id>/modifier", methods=["GET", "POST"])
def modifier_compte_rendu(id: int):
    conn = se_connecter_a_la_base()
    c = conn.execute("SELECT * FROM consultations WHERE id = ?", (id,)).fetchone()
    if not c:
        conn.close()
        abort(404)
    if request.method == "GET":
        vals = {
            "patient_id": str(c["patient_id"]),
            "rendez_vous_id": str(c["rendez_vous_id"] or "") if c["rendez_vous_id"] is not None else "",
            "date_consultation": c["date_consultation"],
            "motif": c["motif"] or "",
            "observations": c["observations"] or "",
            "diagnostic": c["diagnostic"] or "",
            "traitement": c["traitement"] or "",
            "medecin": c["medecin"] or "",
        }
        contenu = formulaire_consultation(conn, f"/consultations/{id}/modifier", vals)
        conn.close()
        return page("Modifier le compte-rendu", contenu, "/consultations")
    # POST
    vals, err = valider_consultation(conn, request.form)  # type: ignore[arg-type]
    if err:
        contenu = formulaire_consultation(conn, f"/consultations/{id}/modifier", {**request.form}, err)  # type: ignore[arg-type]
        conn.close()
        return page("Modifier le compte-rendu", contenu, "/consultations")
    conn.execute(
        """
        UPDATE consultations
        SET patient_id = ?, rendez_vous_id = ?, date_consultation = ?,
            motif = ?, observations = ?, diagnostic = ?, traitement = ?, medecin = ?
        WHERE id = ?
        """,
        (
            int(vals["patient_id"] or "0"),
            (int(vals["rendez_vous_id"]) if vals["rendez_vous_id"] else None),
            vals["date_consultation"],
            vals["motif"] or None,
            vals["observations"] or None,
            vals["diagnostic"] or None,
            vals["traitement"] or None,
            vals["medecin"] or None,
            id,
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("detail_consultation", id=id))


if __name__ == "__main__":
    # Usage local uniquement (debug ON)
    app.run(debug=True)

