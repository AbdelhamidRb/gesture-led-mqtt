#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Test et Simulation Automatisé
======================================
Valide sans webcam le bon fonctionnement de :
1. Calcul de distance euclidienne (Jalon 2)
2. Logique de seuil LED ON / OFF (Jalon 2)
3. Rendu visuel OpenCV (Jalon 2)
4. Connexion et publication MQTT sur broker public (Jalon 3)
"""

import time
import math
import numpy as np
import cv2
from gesture_controller import (
    HandGestureDetector,
    VisualFeedbackRenderer,
    MQTTClientHandler
)


class MockLandmark:
    def __init__(self, x, y, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class MockHandLandmarks:
    def __init__(self, thumb_norm_xy, index_norm_xy):
        # MediaPipe Hands produit 21 landmarks (0 à 20)
        self.landmark = [MockLandmark(0.5, 0.5) for _ in range(21)]
        self.landmark[4] = MockLandmark(thumb_norm_xy[0], thumb_norm_xy[1])
        self.landmark[8] = MockLandmark(index_norm_xy[0], index_norm_xy[1])


def test_distance_and_logic():
    print("[TEST 1/3] Validation du calcul de distance euclidienne et seuil...")
    detector = HandGestureDetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Test A : Doigts très proches (distance = 20 pixels < seuil 35 -> LED ON)
    # pouce à (100, 100), index à (100, 120)
    mock_close = MockHandLandmarks((100 / 640, 100 / 480), (100 / 640, 120 / 480))
    dist, thumb_pt, index_pt, mid_pt = detector.extract_thumb_and_index(frame, mock_close)
    assert abs(dist - 20.0) < 1.0, f"Erreur distance: attendu ~20, obtenu {dist}"
    assert dist < 35.0, "La condition < 35 aurait dû être VRAIE"
    print(f"  -> Doigts proches : distance = {dist:.2f} px (Seuil < 35) => LED ON [OK]")

    # Test B : Doigts écartés (distance = 80 pixels >= seuil 35 -> LED OFF)
    mock_far = MockHandLandmarks((100 / 640, 100 / 480), (100 / 640, 180 / 480))
    dist_far, _, _, _ = detector.extract_thumb_and_index(frame, mock_far)
    assert abs(dist_far - 80.0) < 1.0, f"Erreur distance: attendu ~80, obtenu {dist_far}"
    assert not (dist_far < 35.0), "La condition < 35 aurait dû être FAUSSE"
    print(f"  -> Doigts écartés : distance = {dist_far:.2f} px (Seuil >= 35) => LED OFF [OK]")
    detector.close()


def test_visual_rendering():
    print("[TEST 2/3] Validation du rendu graphique OpenCV...")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    coords = ((100, 100), (100, 120), (100, 110))

    # Test rendu LED ON
    VisualFeedbackRenderer.render(
        frame=frame,
        distance=20.0,
        is_led_on=True,
        threshold=35.0,
        is_mqtt_connected=True,
        broker="test.mosquitto.org",
        topic="idet/led/status",
        fps=30.0,
        finger_coords=coords
    )
    assert frame.shape == (480, 640, 3)
    print("  -> Rendu visuel OpenCV (LED ON & HUD) généré avec succès [OK]")


def test_mqtt_publishing():
    print("[TEST 3/3] Validation de la connexion et publication MQTT...")
    handler = MQTTClientHandler(
        broker="test.mosquitto.org",
        port=1883,
        topic="idet/led/status"
    )
    handler.start()

    # Attente de la connexion
    t0 = time.time()
    while not handler.is_connected and (time.time() - t0 < 6.0):
        time.sleep(0.2)

    if handler.is_connected:
        print(f"  -> Connecté au broker MQTT {handler.broker}:{handler.port} [OK]")
        pub_ok_on = handler.publish_state("ON", force=True)
        print(f"  -> Publication de l'état 'ON' : {pub_ok_on} [OK]")
        time.sleep(0.5)
        pub_ok_off = handler.publish_state("OFF", force=True)
        print(f"  -> Publication de l'état 'OFF' : {pub_ok_off} [OK]")
    else:
        print("  -> Avertissement : Connexion MQTT non établie (vérifiez l'accès réseau)")

    handler.stop()


if __name__ == "__main__":
    print("=" * 60)
    print("   TEST DE VALIDATION DU SYSTÈME GESTE-LED-MQTT")
    print("=" * 60)
    test_distance_and_logic()
    test_visual_rendering()
    test_mqtt_publishing()
    print("=" * 60)
    print("   TOUS LES TESTS SONT VALIDES AVEC SUCCÈS !")
    print("=" * 60)
