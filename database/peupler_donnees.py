"""
peupler_donnees.py
-------------------
Ce script remplit la base de données avec des données FICTIVES,
pour pouvoir tester l'application avant d'utiliser de vrais patients.

Il ajoute :
    - 10 patients
    - 1 rendez-vous pour chacun (donc 10 rendez-vous)
    - 5 comptes-rendus de consultation (pour les 5 premiers patients,
      qui sont donc déjà venus à leur rendez-vous)

À lancer UNE SEULE FOIS, depuis la racine du projet :
    python3 database/peupler_donnees.py
"""

import sqlite3

# ------------------------------------------------------------------
# ÉTAPE 1 : connexion à la base de données existante
# ------------------------------------------------------------------
connexion = sqlite3.connect("database/cabinet.db")
curseur = connexion.cursor()


# ------------------------------------------------------------------
# ÉTAPE 2 : liste des 10 patients fictifs
# ------------------------------------------------------------------
# Chaque patient est une liste de 8 informations, dans le MÊME ORDRE
# que les colonnes de la table "patients" :
# nom, prenom, date_naissance, sexe, telephone, email, adresse, antecedents
patients = [
    ["Dupont",    "Jean",     "1975-03-12", "M", "0791234501", "jean.dupont@exemple.com",     "Rue de la Gare 10, Winterthur",     "Migraines chroniques depuis 2015"],
    ["Meier",     "Anna",     "1988-07-24", "F", "0791234502", "anna.meier@exemple.com",      "Bahnhofstrasse 5, Winterthur",      "Épilepsie, suivie depuis 2019"],
    ["Keller",    "Marc",     "1962-11-02", "M", "0791234503", "marc.keller@exemple.com",     "Technikumstrasse 22, Winterthur",   "Antécédent d'AVC en 2020"],
    ["Fischer",   "Laura",    "1995-01-30", "F", "0791234504", "laura.fischer@exemple.com",   "Neuwiesenstrasse 8, Winterthur",    "Suspicion de sclérose en plaques"],
    ["Schmid",    "Peter",    "1980-05-17", "M", "0791234505", "peter.schmid@exemple.com",    "Zürcherstrasse 40, Winterthur",     "Douleurs neuropathiques"],
    ["Weber",     "Sophie",   "1970-09-09", "F", "0791234506", "sophie.weber@exemple.com",    "Stadthausstrasse 3, Winterthur",    "Maladie de Parkinson, diagnostiquée 2021"],
    ["Huber",     "Thomas",   "1990-12-15", "M", "0791234507", "thomas.huber@exemple.com",    "Wülflingerstrasse 60, Winterthur",  "Céphalées de tension"],
    ["Frei",      "Nadia",    "1985-04-22", "F", "0791234508", "nadia.frei@exemple.com",      "Schaffhauserstrasse 12, Winterthur","Aucun antécédent notable"],
    ["Baumann",   "Lukas",    "1958-06-30", "M", "0791234509", "lukas.baumann@exemple.com",   "Rychenbergstrasse 18, Winterthur",  "Suivi post-traumatisme crânien"],
    ["Moser",     "Elena",    "2000-02-14", "F", "0791234510", "elena.moser@exemple.com",     "Obertorstrasse 2, Winterthur",      "Première consultation en neurologie"],
]

# On garde en mémoire les identifiants attribués à chaque patient,
# car on en aura besoin pour créer leurs rendez-vous juste après.
ids_patients = []

for p in patients:
    curseur.execute("""
        INSERT INTO patients (nom, prenom, date_naissance, sexe, telephone, email, adresse, antecedents)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, p)
    ids_patients.append(curseur.lastrowid)

print(f"✅ {len(ids_patients)} patients ajoutés (identifiants {ids_patients[0]} à {ids_patients[-1]})")


# ------------------------------------------------------------------
# ÉTAPE 3 : un rendez-vous pour chaque patient
# ------------------------------------------------------------------
# Motifs et dates variés, juste pour que les données soient réalistes.
# Les 5 premiers rendez-vous sont marqués "honoré" (le patient est déjà venu),
# les 5 suivants sont "prévu" (rendez-vous à venir).
rendez_vous = [
    ("2026-08-01", "09:00", "Suivi migraines",              "honoré"),
    ("2026-08-01", "10:00", "Contrôle épilepsie",            "honoré"),
    ("2026-08-02", "09:30", "Suivi post-AVC",                "honoré"),
    ("2026-08-02", "11:00", "Bilan neurologique",            "honoré"),
    ("2026-08-03", "14:00", "Suivi douleurs neuropathiques", "honoré"),
    ("2026-09-15", "09:00", "Contrôle Parkinson",            "prévu"),
    ("2026-09-15", "10:30", "Suivi céphalées",               "prévu"),
    ("2026-09-16", "09:00", "Première consultation",         "prévu"),
    ("2026-09-16", "11:00", "Suivi traumatisme crânien",     "prévu"),
    ("2026-09-17", "14:30", "Première consultation",         "prévu"),
]

# On garde aussi les identifiants des rendez-vous, pour les 5 premiers
# (ceux qui sont "honorés"), car on va leur associer un compte-rendu.
ids_rdv = []

for patient_id, rdv in zip(ids_patients, rendez_vous):
    date_rdv, heure_rdv, motif, statut = rdv
    curseur.execute("""
        INSERT INTO rendez_vous (patient_id, date_rdv, heure_rdv, motif, statut)
        VALUES (?, ?, ?, ?, ?)
    """, (patient_id, date_rdv, heure_rdv, motif, statut))
    ids_rdv.append(curseur.lastrowid)

print(f"✅ {len(ids_rdv)} rendez-vous ajoutés")


# ------------------------------------------------------------------
# ÉTAPE 4 : un compte-rendu de consultation pour les 5 premiers patients
# ------------------------------------------------------------------
# Ce sont ceux dont le rendez-vous est marqué "honoré" plus haut.
consultations = [
    ("Suivi migraines",              "Patient rapporte 3 crises/mois, intensité modérée.",       "Migraine chronique sans aura",         "Poursuite du traitement de fond, réévaluation dans 3 mois", "Dr. Martin"),
    ("Contrôle épilepsie",           "Aucune crise depuis la dernière consultation.",             "Épilepsie stable sous traitement",     "Maintien du traitement actuel",                              "Dr. Martin"),
    ("Suivi post-AVC",               "Récupération motrice progressive, légère faiblesse résiduelle.", "Séquelles motrices mineures post-AVC", "Poursuite de la rééducation, contrôle IRM dans 6 mois",      "Dr. Martin"),
    ("Bilan neurologique",           "Examen neurologique dans les limites de la normale.",       "Bilan neurologique normal",            "Aucun traitement nécessaire, contrôle si symptômes",         "Dr. Martin"),
    ("Suivi douleurs neuropathiques","Douleurs partiellement soulagées par le traitement actuel.", "Douleurs neuropathiques chroniques",   "Ajustement de la posologie",                                 "Dr. Martin"),
]

for i in range(5):
    patient_id = ids_patients[i]
    rdv_id = ids_rdv[i]
    motif, observations, diagnostic, traitement, medecin = consultations[i]
    date_consultation = rendez_vous[i][0]  # même date que le rendez-vous

    curseur.execute("""
        INSERT INTO consultations
            (patient_id, rendez_vous_id, date_consultation, motif, observations, diagnostic, traitement, medecin)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (patient_id, rdv_id, date_consultation, motif, observations, diagnostic, traitement, medecin))

print("✅ 5 comptes-rendus de consultation ajoutés")


# ------------------------------------------------------------------
# ÉTAPE 5 : on enregistre tout, puis on ferme la connexion
# ------------------------------------------------------------------
connexion.commit()
connexion.close()

print("\n🎉 Base de données peuplée avec succès !")
print("   - 10 patients")
print("   - 10 rendez-vous (5 honorés, 5 à venir)")
print("   - 5 comptes-rendus de consultation")
