# Système de Contrôle d'Accès par Geste (OpenCV, MediaPipe & MQTT)

Application temps réel en Python développée dans le cadre des projets **M2 IoT**.  
Le système capture le flux vidéo de la webcam, suit les articulations de la main, calcule la distance euclidienne en pixels entre l'extrémité du **pouce** et de l'**index**, et commande à distance l'état d'une LED via le protocole **MQTT** vers un broker public avec supervision dans **Node-RED**.

---

## 📑 Sommaire
1. [Architecture Globale](#-architecture-globale)
2. [Fonctionnalités & Jalons](#-fonctionnalités--jalons)
3. [Stack Technique](#-stack-technique)
4. [Installation & Prérequis](#-installation--prérequis)
5. [Guide d'Utilisation](#-guide-dutilisation)
   - [Lancement du Contrôleur de Geste](#1-lancement-du-contrôleur-de-geste-vision--mqtt)
   - [Lancement du Témoin Abonné (Subscriber)](#2-lancement-du-témoin-abonné-subscriber)
   - [Intégration Node-RED](#3-intégration-node-red-tableau-de-bord)
6. [Structure du Projet](#-structure-du-projet)
7. [Dépannage & Bonnes Pratiques](#-dépannage--bonnes-pratiques)

---

## 🏗 Architecture Globale

```
                      +---------------------------------------+
                      |           FLUX VIDÉO WEBCAM           |
                      +---------------------------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |      OPENCV & MEDIAPIPE HANDS         |
                      |  - Pouce (Point 4) & Index (Point 8)  |
                      |  - Calcul distance euclidienne (px)   |
                      +---------------------------------------+
                                          |
                      +-------------------+-------------------+
                      |                                       |
                      v                                       v
         [ Distance < 35 px ]                    [ Distance >= 35 px ]
         (Doigts en contact)                     (Doigts écartés ou absent)
                  |                                           |
                  v                                           v
            État: "ON"                                  État: "OFF"
            (Accès Autorisé)                            (Accès Verrouillé)
                  |                                           |
                  +-------------------+-----------------------+
                                      |
                                      v
                      +---------------------------------------+
                      |      PUBLICATION PAHO-MQTT            |
                      |    Topic: idet/led/status             |
                      +---------------------------------------+
                                      |
                                      v
                      +---------------------------------------+
                      |         BROKER MQTT PUBLIC            |
                      |        test.mosquitto.org:1883        |
                      +---------------------------------------+
                                      |
                       +--------------+--------------+
                       |                             |
                       v                             v
        +----------------------------+  +----------------------------+
        |   TABLEAU DE BORD NODE-RED |  |   RÉCEPTEUR IOT / CLIENT   |
        |   - Voyant LED virtuel     |  |   - subscriber.py          |
        |   - Journal des accès      |  |   - Carte ESP32 physique   |
        +----------------------------+  +----------------------------+
```

---

## 🎯 Fonctionnalités & Jalons

| Jalon | Description | Statut |
| :--- | :--- | :---: |
| **Jalon 1** | **Capture & Détection de la Main** : Initialisation webcam avec OpenCV, détection des landmarks avec MediaPipe Hands, isolation des coordonnées du pouce (point 4) et de l'index (point 8). | ✅ Validé |
| **Jalon 2** | **Calcul de Distance & Logique Métier** : Calcul de la distance euclidienne $d = \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}$, application du seuil ($d < 35$ px $\to$ ON, sinon $\to$ OFF), incrustation visuelle dynamique (« LED: ON » en vert, « LED: OFF » en rouge, jauge, FPS). | ✅ Validé |
| **Jalon 3** | **Intégration MQTT** : Connexion asynchrone au broker `test.mosquitto.org:1883`, publication de `"ON"` ou `"OFF"` sur le topic `idet/led/status` uniquement sur changement d'état (anti-saturation). | ✅ Validé |
| **Bonus** | **Supervision Node-RED & Outils** : Flux Node-RED complet (`node_red_flow.json`), script d'écoute (`subscriber.py`) et suite de test unitaire sans webcam (`test_simulation.py`). | ✅ Validé |

---

## 🛠 Stack Technique

- **Langage** : Python 3.10+
- **Vision par Ordinateur** : `opencv-python` (capture, traitement d'images, interface graphique HUD)
- **Détection Biomécanique** : `mediapipe` (MediaPipe Hands, tracking 21 articulations)
- **Protocole IoT** : `paho-mqtt` (client MQTT v2 & v1 compatible)
- **Broker MQTT** : `test.mosquitto.org` (port 1883)
- **Tableau de Bord IoT** : `Node-RED` (supervision web, jauge, LED virtuelle)

---

## 📦 Installation & Prérequis

### 1. Cloner ou ouvrir le dossier du projet
```powershell
cd c:\Users\pc\Desktop\M2\IOT\gesture-led-mqtt
```

### 2. Activer l'environnement virtuel (recommandé)
Un environnement virtuel pré-configuré `.venv` est présent dans le projet :
```powershell
.\.venv\Scripts\Activate.ps1
```

*(Si vous souhaitez recréer l'environnement depuis zéro)* :
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 🚀 Guide d'Utilisation

### 1. Lancement du Contrôleur de Geste (Vision & MQTT)
Pour lancer l'application principale avec la webcam :
```powershell
.\.venv\Scripts\python.exe gesture_controller.py
```

#### Raccourcis Clavier en direct :
- `+` ou `=` : Augmenter le seuil de distance (+2 pixels)
- `-` ou `_` : Diminuer le seuil de distance (-2 pixels)
- `q` ou `Échap` : Quitter proprement l'application

#### Options de Ligne de Commande :
```powershell
.\.venv\Scripts\python.exe gesture_controller.py --broker test.mosquitto.org --port 1883 --topic idet/led/status --threshold 35 --camera 0
```
- `--broker` : Adresse du broker MQTT (défaut: `test.mosquitto.org`)
- `--port` : Port du broker (défaut: `1883`)
- `--topic` : Topic de publication (défaut: `idet/led/status`)
- `--threshold` : Seuil de proximité en pixels (défaut: `35`)
- `--camera` : Index de la webcam (défaut: `0`)
- `--no-flip` : Désactiver l'effet miroir de la caméra

---

### 2. Lancement du Témoin Abonné (Subscriber)
Pour visualiser en console la réception des ordres MQTT en temps réel (dans un second terminal) :
```powershell
.\.venv\Scripts\python.exe subscriber.py
```
Dès que vous rapprochez vos doigts devant la caméra, le subscriber affiche :
```
[17:30:12] [MQTT <- idet/led/status]  ● LED ALLUMÉE (ON)  - [ACCÈS AUTORISÉ]
[17:30:15] [MQTT <- idet/led/status]  ○ LED ÉTEINTE (OFF) - [ACCÈS VERROUILLÉ]
```

---

### 3. Intégration Node-RED (Tableau de Bord)

Un flux Node-RED prêt à l'emploi est inclus dans le fichier [`node_red_flow.json`](file:///c:/Users/pc/Desktop/M2/IOT/gesture-led-mqtt/node_red_flow.json).

#### Étape 1 : Démarrer Node-RED
Dans un terminal PowerShell :
```powershell
node-red
```

#### Étape 2 : Importer le flux
1. Ouvrez votre navigateur sur `http://localhost:1880`.
2. Cliquez sur le menu en haut à droite (**≡**) $\to$ **Import**.
3. Sélectionnez le fichier `node_red_flow.json` (ou copiez-collez son contenu).
4. Cliquez sur **Deploy** (Déployer) en rouge en haut à droite.

#### Étape 3 : Accéder au Tableau de Bord Web
Le flux met à disposition une interface web moderne et réactive servie nativement par Node-RED :
👉 **Ouvrez dans votre navigateur** : `http://localhost:1880/led-dashboard`

Vous y verrez :
- Le voyant LED circulaire animé (Vert lumineux quand vos doigts se touchent, Rouge quand ils sont écartés).
- Le statut textuel de contrôle d'accès : `ACCÈS AUTORISÉ (LED ON)` / `ACCÈS VERROUILLÉ (LED OFF)`.
- Les détails MQTT (Broker, Topic, Horodatage de dernière réception).
- Une API REST JSON disponible à `http://localhost:1880/api/led-status`.

---

## 🧪 Tests Automatisés (Sans Webcam)
Pour valider l'intégrité de l'algorithme, des calculs de distance et de la connexion MQTT sans webcam physique :
```powershell
.\.venv\Scripts\python.exe test_simulation.py
```

Résultat attendu :
```
============================================================
   TEST DE VALIDATION DU SYSTÈME GESTE-LED-MQTT
============================================================
[TEST 1/3] Validation du calcul de distance euclidienne et seuil...
  -> Doigts proches : distance = 20.00 px (Seuil < 35) => LED ON [OK]
  -> Doigts écartés : distance = 80.00 px (Seuil >= 35) => LED OFF [OK]
[TEST 2/3] Validation du rendu graphique OpenCV...
  -> Rendu visuel OpenCV (LED ON & HUD) généré avec succès [OK]
[TEST 3/3] Validation de la connexion et publication MQTT...
  -> Connecté au broker MQTT test.mosquitto.org:1883 [OK]
  -> Publication de l'état 'ON' : True [OK]
  -> Publication de l'état 'OFF' : True [OK]
============================================================
   TOUS LES TESTS SONT VALIDES AVEC SUCCÈS !
============================================================
```

---

## 📁 Structure du Projet

```
gesture-led-mqtt/
├── gesture_controller.py   # Application principale (OpenCV, MediaPipe & Publication MQTT)
├── subscriber.py           # Client abonné MQTT pour test et validation en console
├── test_simulation.py      # Suite de tests unitaires et simulation
├── node_red_flow.json      # Flux Node-RED (MQTT in, Dashboard web, API JSON)
├── requirements.txt        # Dépendances Python (opencv-python, mediapipe, paho-mqtt)
└── README.md               # Documentation complète du projet
```

---

## 💡 Dépannage & Bonnes Pratiques

1. **La webcam ne s'ouvre pas** :
   - Assurez-vous qu'aucune autre application n'utilise la caméra (Teams, Zoom, navigateur).
   - Testez un autre index avec `--camera 1` si vous disposez d'une caméra externe.
2. **Le broker `test.mosquitto.org` ne répond pas** :
   - Il s'agit d'un broker public gratuit qui subit parfois des coupures momentanées.
   - Vous pouvez basculer sur un broker alternatif sans modifier le code :
     ```powershell
     python gesture_controller.py --broker broker.hivemq.com
     python subscriber.py --broker broker.hivemq.com
     ```
3. **Optimisation réseau MQTT** :
   - Le script implémente une publication événementielle (state-change) : il ne publie que lorsque l'état change ou après un intervalle de battement (heartbeat 5s), ce qui évite de spammer 30 messages par seconde sur le broker.
