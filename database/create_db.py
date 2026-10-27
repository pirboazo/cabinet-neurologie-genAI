"""
create_db.py
-------------
Ce script crée la base de données SQLite du cabinet de neurologie.
On l'exécute UNE SEULE FOIS pour créer le fichier "cabinet.db"
et les tables qu'il contient (patients, rendez_vous, consultations).

Pour l'exécuter : ouvrir un terminal à la racine du projet et taper :
    python3 database/create_db.py
"""

import sqlite3

# 1. On se connecte à la base de données.
#    Si le fichier "cabinet.db" n'existe pas encore, SQLite le crée automatiquement.
connexion = sqlite3.connect("database/cabinet.db")

# 2. Le "curseur" est l'objet qui nous permet d'exécuter des commandes SQL.
curseur = connexion.cursor()

# 3. Création de la table "patients"
#    Chaque patient a un identifiant unique (id), généré automatiquement.
curseur.execute("""
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    prenom TEXT NOT NULL,
    date_naissance DATE,
    sexe TEXT,
    telephone TEXT,
    email TEXT,
    adresse TEXT,
    antecedents TEXT,
    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 4. Création de la table "rendez_vous"
#    "patient_id" fait le lien vers la table patients (clé étrangère).
curseur.execute("""
CREATE TABLE IF NOT EXISTS rendez_vous (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    date_rdv DATE NOT NULL,
    heure_rdv TIME NOT NULL,
    motif TEXT,
    statut TEXT DEFAULT 'prévu',
    FOREIGN KEY (patient_id) REFERENCES patients (id)
)
""")

# 5. Création de la table "consultations"
#    Elle est liée à un patient, et optionnellement à un rendez-vous.
curseur.execute("""
CREATE TABLE IF NOT EXISTS consultations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    rendez_vous_id INTEGER,
    date_consultation DATE NOT NULL,
    motif TEXT,
    observations TEXT,
    diagnostic TEXT,
    traitement TEXT,
    medecin TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients (id),
    FOREIGN KEY (rendez_vous_id) REFERENCES rendez_vous (id)
)
""")

# 6. On enregistre (valide) les changements dans le fichier.
connexion.commit()

# 7. On ferme proprement la connexion.
connexion.close()

print("✅ Base de données 'cabinet.db' créée avec succès, avec les tables :")
print("   - patients")
print("   - rendez_vous")
print("   - consultations")
