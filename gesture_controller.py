#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Système de Contrôle d'Accès par Geste (OpenCV, MediaPipe & MQTT)
================================================================
Analyse en temps réel le flux vidéo de la webcam pour mesurer la distance
entre le pouce (point 4) et l'index (point 8). Selon cette distance, l'application
commande l'état d'une LED ("ON" si doigts proches, "OFF" sinon) et transmet
l'ordre à un broker MQTT public (ex: test.mosquitto.org) pour affichage /
traitement dans Node-RED ou un récepteur IoT.

Stack technique :
- OpenCV (cv2) : Capture et traitement vidéo
- MediaPipe : Suivi précis des articulations de la main
- paho-mqtt : Communication MQTT (publication temps réel)
- Node-RED : Supervision et tableau de bord IoT
"""

import sys
import time
import math
import argparse
import logging
from typing import Optional, Tuple

import cv2
import mediapipe as mp
import paho.mqtt.client as mqtt

# Configuration de la journalisation (logging)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("GestureAccessControl")


# =====================================================================
# GESTIONNAIRE DE COMMUNICATION MQTT (Jalon 3)
# =====================================================================
class MQTTClientHandler:
    """
    Gère la connexion, reconnexion et publication des messages MQTT.
    Compatible avec paho-mqtt 1.x et 2.x.
    """

    def __init__(self, broker: str = "test.mosquitto.org", port: int = 1883,
                 topic: str = "idet/led/status", client_id: Optional[str] = None):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client_id = client_id or f"GestureClient_{int(time.time() * 1000) % 100000}"
        self.is_connected = False
        self.last_published_state: Optional[str] = None
        self.last_publish_time: float = 0.0

        # Initialisation du client paho-mqtt avec rétrocompatibilité v1/v2
        try:
            from paho.mqtt.enums import CallbackAPIVersion
            self.client = mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=self.client_id
            )
            self._uses_v2 = True
        except (AttributeError, TypeError, ImportError):
            self.client = mqtt.Client(client_id=self.client_id)
            self._uses_v2 = False

        self._setup_callbacks()

    def _setup_callbacks(self):
        """Définit les fonctions de rappel pour les événements MQTT."""
        if self._uses_v2:
            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    self.is_connected = True
                    logger.info(f"Connecté avec succès au broker MQTT {self.broker}:{self.port}")
                else:
                    self.is_connected = False
                    logger.warning(f"Échec de connexion MQTT (code retour: {rc})")

            def on_disconnect(client, userdata, flags, rc, properties=None):
                self.is_connected = False
                logger.warning(f"Déconnecté du broker MQTT (code: {rc})")

            def on_publish(client, userdata, mid, reason_codes=None, properties=None):
                logger.debug(f"Message MQTT publié (mid: {mid})")

        else:
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    self.is_connected = True
                    logger.info(f"Connecté avec succès au broker MQTT {self.broker}:{self.port}")
                else:
                    self.is_connected = False
                    logger.warning(f"Échec de connexion MQTT (code retour: {rc})")

            def on_disconnect(client, userdata, rc):
                self.is_connected = False
                logger.warning(f"Déconnecté du broker MQTT (code: {rc})")

            def on_publish(client, userdata, mid):
                logger.debug(f"Message MQTT publié (mid: {mid})")

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_publish = on_publish

    def start(self):
        """Démarre la connexion et la boucle d'événements en tâche de fond."""
        logger.info(f"Connexion au broker MQTT [{self.broker}:{self.port}]...")
        try:
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Erreur d'initialisation de la connexion MQTT : {e}")

    def publish_state(self, new_state: str, force: bool = False, qos: int = 0, retain: bool = False) -> bool:
        """
        Publie l'état ("ON" ou "OFF") sur le topic dédié.
        Ne publie que si l'état a changé ou si le paramètre force est True,
        afin d'éviter de saturer le broker MQTT à chaque image de la webcam (30 fps).
        """
        now = time.time()
        # Émission uniquement sur changement d'état ou après un heartbeat (ex: toutes les 5s)
        if new_state != self.last_published_state or force or (now - self.last_publish_time > 5.0):
            try:
                result = self.client.publish(self.topic, payload=new_state, qos=qos, retain=retain)
                self.last_published_state = new_state
                self.last_publish_time = now
                logger.info(f"[MQTT -> {self.topic}] État LED publié : {new_state} (statut connectivité: {self.is_connected})")
                return result.rc == mqtt.MQTT_ERR_SUCCESS
            except Exception as e:
                logger.error(f"Erreur lors de la publication MQTT : {e}")
                return False
        return False

    def stop(self):
        """Arrêt propre du client MQTT."""
        logger.info("Fermeture de la connexion MQTT...")
        try:
            # Publier un état OFF de sécurité à l'arrêt
            if self.is_connected:
                self.client.publish(self.topic, payload="OFF", qos=0)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            logger.warning(f"Erreur lors de la déconnexion MQTT : {e}")


# =====================================================================
# DÉTECTEUR DE GESTES AVEC MEDIAPIPE (Jalons 1 & 2)
# =====================================================================
class HandGestureDetector:
    """
    Détecte la main et calcule la distance euclidienne en pixels entre le
    pouce (point 4) et l'index (point 8).
    """

    # Indices des landmarks définis par MediaPipe Hands
    THUMB_TIP_ID = 4   # Pointe du pouce
    INDEX_TIP_ID = 8   # Pointe de l'index

    def __init__(self, static_mode: bool = False, max_hands: int = 1,
                 min_detection_confidence: float = 0.7,
                 min_tracking_confidence: float = 0.5):
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.hands = self.mp_hands.Hands(
            static_image_mode=static_mode,
            max_num_hands=max_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence
        )

    def process(self, frame_bgr):
        """Traite l'image BGR et renvoie les détections de mains."""
        # MediaPipe requiert une image en espace de couleur RGB
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False
        results = self.hands.process(frame_rgb)
        frame_rgb.flags.writeable = True
        return results

    def extract_thumb_and_index(self, frame, hand_landmarks) -> Tuple[float, Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
        """
        Isole les coordonnées de la pointe du pouce (point 4) et de la
        pointe de l'index (point 8) puis calcule la distance euclidienne en pixels.
        
        Retourne :
        (distance_pixels, (thumb_x, thumb_y), (index_x, index_y), (mid_x, mid_y))
        """
        h, w, _ = frame.shape

        thumb_landmark = hand_landmarks.landmark[self.THUMB_TIP_ID]
        index_landmark = hand_landmarks.landmark[self.INDEX_TIP_ID]

        # Conversion des coordonnées normalisées [0, 1] en pixels
        thumb_x = int(thumb_landmark.x * w)
        thumb_y = int(thumb_landmark.y * h)

        index_x = int(index_landmark.x * w)
        index_y = int(index_landmark.y * h)

        # Calcul de la distance euclidienne en pixels (Jalon 2)
        # distance = sqrt((x2 - x1)^2 + (y2 - y1)^2)
        distance = math.hypot(index_x - thumb_x, index_y - thumb_y)

        # Point milieu entre les deux doigts (pour repère visuel)
        mid_x = (thumb_x + index_x) // 2
        mid_y = (thumb_y + index_y) // 2

        return distance, (thumb_x, thumb_y), (index_x, index_y), (mid_x, mid_y)

    def draw_skeleton(self, frame, hand_landmarks):
        """Dessine les points d'articulation et les connexions de la main."""
        self.mp_drawing.draw_landmarks(
            frame,
            hand_landmarks,
            self.mp_hands.HAND_CONNECTIONS,
            self.mp_drawing_styles.get_default_hand_landmarks_style(),
            self.mp_drawing_styles.get_default_hand_connections_style()
        )

    def close(self):
        """Libère les ressources MediaPipe."""
        self.hands.close()


# =====================================================================
# INTERFACE GRAPHIQUE ET AFFICHAGE VISUEL (Jalon 2)
# =====================================================================
class VisualFeedbackRenderer:
    """
    Affiche dynamiquement sur le flux vidéo l'état LED, la distance,
    le seuil, le statut MQTT et les repères graphiques.
    """

    # Couleurs en format BGR
    COLOR_GREEN = (0, 230, 70)       # Vert vif (LED ON)
    COLOR_RED = (50, 50, 240)        # Rouge vif (LED OFF)
    COLOR_CYAN = (255, 220, 0)       # Cyan/Jaune pour repères
    COLOR_WHITE = (255, 255, 255)
    COLOR_BLACK = (20, 20, 20)
    COLOR_DARK_GRAY = (40, 40, 40)
    COLOR_ORANGE = (0, 140, 255)

    @classmethod
    def render(cls, frame, distance: Optional[float], is_led_on: bool,
               threshold: float, is_mqtt_connected: bool, broker: str,
               topic: str, fps: float, finger_coords=None):
        """Incruste l'ensemble des éléments graphiques sur l'image."""
        h, w, _ = frame.shape

        # -------------------------------------------------------------
        # 1. Repères visuels sur les doigts si détectés
        # -------------------------------------------------------------
        if finger_coords is not None:
            (tx, ty), (ix, iy), (mx, my) = finger_coords
            line_color = cls.COLOR_GREEN if is_led_on else cls.COLOR_RED

            # Cercles sur les extrémités (pouce et index)
            cv2.circle(frame, (tx, ty), 10, cls.COLOR_CYAN, cv2.FILLED)
            cv2.circle(frame, (tx, ty), 12, cls.COLOR_WHITE, 2)

            cv2.circle(frame, (ix, iy), 10, cls.COLOR_CYAN, cv2.FILLED)
            cv2.circle(frame, (ix, iy), 12, cls.COLOR_WHITE, 2)

            # Ligne reliant le pouce et l'index
            cv2.line(frame, (tx, ty), (ix, iy), line_color, 3)

            # Point milieu avec taille dynamique selon la distance
            mid_radius = 8 if is_led_on else 6
            cv2.circle(frame, (mx, my), mid_radius, line_color, cv2.FILLED)
            cv2.circle(frame, (mx, my), mid_radius + 2, cls.COLOR_WHITE, 1)

            # Étiquette affichant la distance près des doigts
            dist_label = f"{distance:.1f} px"
            cv2.putText(frame, dist_label, (mx + 12, my - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, cls.COLOR_WHITE, 2, cv2.LINE_AA)

        # -------------------------------------------------------------
        # 2. Panneau supérieur (HUD / Dashboard)
        # -------------------------------------------------------------
        # Fond translucide pour le bandeau d'informations
        overlay = frame.copy()
        cv2.rectangle(overlay, (15, 15), (w - 15, 125), cls.COLOR_DARK_GRAY, cv2.FILLED)
        cv2.addWeighted(overlay, 0.70, frame, 0.30, 0, frame)
        cv2.rectangle(frame, (15, 15), (w - 15, 125), (80, 80, 80), 1)

        # -------------------------------------------------------------
        # 3. Badge d'état de la LED (LED ON / LED OFF)
        # -------------------------------------------------------------
        led_color = cls.COLOR_GREEN if is_led_on else cls.COLOR_RED
        led_text = "LED: ON" if is_led_on else "LED: OFF"

        # Boîte LED colorée
        badge_x1, badge_y1 = 30, 28
        badge_x2, badge_y2 = 210, 80
        cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), led_color, cv2.FILLED)
        cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), cls.COLOR_WHITE, 2)

        # Cercle lumineux type voyant LED
        circle_x, circle_y = badge_x1 + 25, (badge_y1 + badge_y2) // 2
        cv2.circle(frame, (circle_x, circle_y), 12, cls.COLOR_WHITE, cv2.FILLED)
        cv2.circle(frame, (circle_x, circle_y), 9, (0, 255, 255) if is_led_on else (0, 0, 180), cv2.FILLED)

        # Texte dans le badge
        cv2.putText(frame, led_text, (circle_x + 20, circle_y + 8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.85, cls.COLOR_WHITE, 2, cv2.LINE_AA)

        # -------------------------------------------------------------
        # 4. Informations métriques (Distance & Seuil)
        # -------------------------------------------------------------
        if distance is not None:
            dist_str = f"Distance : {distance:5.1f} px"
        else:
            dist_str = "Distance : -- (Aucune main)"

        thresh_str = f"Seuil : {threshold:.0f} px"

        cv2.putText(frame, dist_str, (230, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, cls.COLOR_WHITE, 2, cv2.LINE_AA)
        cv2.putText(frame, thresh_str, (230, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, cls.COLOR_ORANGE, 2, cv2.LINE_AA)

        # Barre visuelle de jauge (proximité)
        bar_x = 440
        bar_y = 38
        bar_w = min(180, w - bar_x - 30)
        bar_h = 24
        if bar_w > 60:
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (30, 30, 30), cv2.FILLED)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (120, 120, 120), 1)

            # Remplissage dynamique selon ratio distance / seuil
            if distance is not None:
                max_display_dist = threshold * 2.5
                ratio = max(0.0, min(1.0, distance / max_display_dist))
                fill_w = int(bar_w * ratio)
                bar_fill_color = cls.COLOR_GREEN if is_led_on else cls.COLOR_RED
                cv2.rectangle(frame, (bar_x + 1, bar_y + 1), (bar_x + fill_w, bar_y + bar_h - 1),
                              bar_fill_color, cv2.FILLED)

            # Marqueur du seuil sur la jauge
            thresh_marker_x = bar_x + int(bar_w * (1.0 / 2.5))
            cv2.line(frame, (thresh_marker_x, bar_y - 2), (thresh_marker_x, bar_y + bar_h + 2),
                     cls.COLOR_WHITE, 2)

        # -------------------------------------------------------------
        # 5. Informations MQTT et réseau (ligne inférieure du bandeau)
        # -------------------------------------------------------------
        mqtt_status_str = "MQTT: Connecte" if is_mqtt_connected else "MQTT: Deconnecte"
        mqtt_status_color = cls.COLOR_GREEN if is_mqtt_connected else cls.COLOR_RED

        cv2.circle(frame, (35, 105), 6, mqtt_status_color, cv2.FILLED)
        cv2.putText(frame, f"{mqtt_status_str} [{broker}]", (50, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, cls.COLOR_WHITE, 1, cv2.LINE_AA)

        cv2.putText(frame, f"Topic: {topic}", (300, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

        # FPS
        cv2.putText(frame, f"FPS: {fps:.0f}", (w - 110, 110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, cls.COLOR_CYAN, 1, cv2.LINE_AA)

        # -------------------------------------------------------------
        # 6. Raccourcis clavier (pied de fenêtre)
        # -------------------------------------------------------------
        cv2.putText(frame, "[+] / [-] : Ajuster le seuil    |    [Q] ou [ESC] : Quitter",
                    (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (220, 220, 220), 1, cv2.LINE_AA)


# =====================================================================
# CONTRÔLEUR PRINCIPAL DE L'APPLICATION
# =====================================================================
class GestureAccessController:
    """
    Coordonne la capture vidéo, la détection des gestes, la logique métier
    et la communication MQTT.
    """

    def __init__(self, camera_id: int = 0, threshold: float = 35.0,
                 broker: str = "test.mosquitto.org", port: int = 1883,
                 topic: str = "idet/led/status", flip_horizontal: bool = True):
        self.camera_id = camera_id
        self.threshold = threshold
        self.broker = broker
        self.port = port
        self.topic = topic
        self.flip_horizontal = flip_horizontal

        # Instanciation des composants modulaires
        self.mqtt_handler = MQTTClientHandler(
            broker=self.broker,
            port=self.port,
            topic=self.topic
        )
        self.detector = HandGestureDetector()
        self.is_led_on = False

    def run(self):
        """Boucle principale de traitement vidéo."""
        logger.info("=" * 65)
        logger.info("   SYSTÈME DE CONTRÔLE D'ACCÈS PAR GESTE (OpenCV & MQTT)")
        logger.info("=" * 65)
        logger.info(f"Paramètres : Seuil={self.threshold}px | Topic='{self.topic}' | Broker='{self.broker}'")

        # Démarrage de la connexion MQTT
        self.mqtt_handler.start()

        # Initialisation de la webcam (Jalon 1)
        logger.info(f"Initialisation de la webcam (Device ID: {self.camera_id})...")
        cap = cv2.VideoCapture(self.camera_id)

        # Optimisation de la résolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            logger.error(f"Impossible d'ouvrir la webcam (ID {self.camera_id}). Vérifiez qu'elle est branchée et libre.")
            self.mqtt_handler.stop()
            sys.exit(1)

        logger.info("Webcam active. Rapprochez le pouce et l'index pour allumer la LED !")

        # Variables pour le calcul des FPS
        prev_time = time.time()
        fps = 0.0

        try:
            while True:
                success, frame = cap.read()
                if not success or frame is None:
                    logger.warning("Échec de lecture d'une frame webcam. Nouvelle tentative...")
                    time.sleep(0.05)
                    continue

                # Effet miroir horizontal pour une interaction naturelle
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)

                # Calcul des FPS
                curr_time = time.time()
                dt = curr_time - prev_time
                prev_time = curr_time
                if dt > 0:
                    fps = 0.9 * fps + 0.1 * (1.0 / dt)

                # Détection de la main avec MediaPipe (Jalon 1)
                results = self.detector.process(frame)

                distance = None
                finger_coords = None

                if results.multi_hand_landmarks:
                    # Analyse de la première main détectée
                    hand_landmarks = results.multi_hand_landmarks[0]

                    # Dessin du squelette complet de la main
                    self.detector.draw_skeleton(frame, hand_landmarks)

                    # Isolation des points 4 et 8 et calcul de distance (Jalons 1 & 2)
                    distance, thumb_pt, index_pt, mid_pt = self.detector.extract_thumb_and_index(
                        frame, hand_landmarks
                    )
                    finger_coords = (thumb_pt, index_pt, mid_pt)

                    # Logique métier : LED ON si distance < seuil, OFF sinon (Jalon 2)
                    self.is_led_on = (distance < self.threshold)
                else:
                    # Aucune main détectée dans le champ de vision : LED éteinte par sécurité
                    self.is_led_on = False

                # Publication MQTT de l'état (Jalon 3)
                state_message = "ON" if self.is_led_on else "OFF"
                self.mqtt_handler.publish_state(state_message)

                # Rendu visuel dynamique sur le flux vidéo (Jalon 2)
                VisualFeedbackRenderer.render(
                    frame=frame,
                    distance=distance,
                    is_led_on=self.is_led_on,
                    threshold=self.threshold,
                    is_mqtt_connected=self.mqtt_handler.is_connected,
                    broker=self.broker,
                    topic=self.topic,
                    fps=fps,
                    finger_coords=finger_coords
                )

                # Affichage de la fenêtre
                cv2.imshow("Controle d'Acces par Geste (OpenCV / MediaPipe / MQTT)", frame)

                # Gestion des interactions clavier
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27):  # 'q' ou touche Échap
                    logger.info("Touche d'arrêt pressée. Fermeture de l'application...")
                    break
                elif key in (ord('+'), ord('=')):
                    self.threshold = min(200.0, self.threshold + 2.0)
                    logger.info(f"Seuil augmenté : {self.threshold:.0f} px")
                elif key in (ord('-'), ord('_')):
                    self.threshold = max(10.0, self.threshold - 2.0)
                    logger.info(f"Seuil diminué : {self.threshold:.0f} px")

        except KeyboardInterrupt:
            logger.info("Interruption clavier détectée (Ctrl+C).")
        finally:
            # Libération propre de toutes les ressources
            logger.info("Nettoyage des ressources...")
            cap.release()
            cv2.destroyAllWindows()
            self.detector.close()
            self.mqtt_handler.stop()
            logger.info("Application terminée proprement.")


# =====================================================================
# POINT D'ENTRÉE PRINCIPAL (CLI)
# =====================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Système de Contrôle d'Accès par Geste avec OpenCV, MediaPipe et MQTT."
    )
    parser.add_argument(
        "--broker", type=str, default="test.mosquitto.org",
        help="Adresse du broker MQTT (par défaut: test.mosquitto.org)"
    )
    parser.add_argument(
        "--port", type=int, default=1883,
        help="Port du broker MQTT (par défaut: 1883)"
    )
    parser.add_argument(
        "--topic", type=str, default="idet/led/status",
        help="Topic MQTT de publication (par défaut: idet/led/status)"
    )
    parser.add_argument(
        "--threshold", type=float, default=35.0,
        help="Seuil de distance en pixels entre le pouce et l'index (par défaut: 35)"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="Index de la webcam (par défaut: 0)"
    )
    parser.add_argument(
        "--no-flip", action="store_true",
        help="Désactiver l'effet miroir horizontal de la caméra"
    )

    args = parser.parse_args()

    controller = GestureAccessController(
        camera_id=args.camera,
        threshold=args.threshold,
        broker=args.broker,
        port=args.port,
        topic=args.topic,
        flip_horizontal=not args.no_flip
    )
    controller.run()


if __name__ == "__main__":
    main()
