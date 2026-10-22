#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client Abonné MQTT (Subscriber) - Témoin LED
============================================
Ce script s'abonne au topic MQTT (par ex: idet/led/status) sur le broker public
et affiche l'état reçu en temps réel ("ON" ou "OFF").
Il permet de valider le bon fonctionnement de la chaîne IoT indépendamment
ou en parallèle de Node-RED.
"""

import sys
import time
import argparse
import logging
import paho.mqtt.client as mqtt

# Configuration de l'affichage
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("MQTTSubscriber")


def print_led_visual(state: str, topic: str):
    """Affiche un indicateur visuel en console selon l'état."""
    timestamp = time.strftime("%H:%M:%S")
    if state == "ON":
        # Vert en console ANSI
        print(f"\033[1;32m[{timestamp}] [MQTT <- {topic}]  ● LED ALLUMÉE (ON)  - [ACCÈS AUTORISÉ]\033[0m")
    elif state == "OFF":
        # Rouge en console ANSI
        print(f"\033[1;31m[{timestamp}] [MQTT <- {topic}]  ○ LED ÉTEINTE (OFF) - [ACCÈS VERROUILLÉ]\033[0m")
    else:
        print(f"[{timestamp}] [MQTT <- {topic}]  Message reçu : {state}")


def main():
    parser = argparse.ArgumentParser(description="Abonné MQTT pour l'état de la LED")
    parser.add_argument("--broker", type=str, default="test.mosquitto.org", help="Broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Port MQTT")
    parser.add_argument("--topic", type=str, default="idet/led/status", help="Topic MQTT")
    args = parser.parse_args()

    client_id = f"LedSubscriber_{int(time.time() * 1000) % 100000}"

    try:
        from paho.mqtt.enums import CallbackAPIVersion
        client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=client_id)
        v2 = True
    except (AttributeError, TypeError, ImportError):
        client = mqtt.Client(client_id=client_id)
        v2 = False

    if v2:
        def on_connect(c, userdata, flags, rc, properties=None):
            if rc == 0:
                logger.info(f"Connecté au broker {args.broker}:{args.port}")
                c.subscribe(args.topic, qos=0)
                logger.info(f"Abonné avec succès au topic : '{args.topic}'")
                logger.info("En attente des messages du système de détection de gestes...")
            else:
                logger.error(f"Échec de connexion (code: {rc})")

        def on_message(c, userdata, msg):
            payload = msg.payload.decode("utf-8", errors="replace").strip()
            print_led_visual(payload, msg.topic)
    else:
        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                logger.info(f"Connecté au broker {args.broker}:{args.port}")
                c.subscribe(args.topic, qos=0)
                logger.info(f"Abonné avec succès au topic : '{args.topic}'")
                logger.info("En attente des messages du système de détection de gestes...")
            else:
                logger.error(f"Échec de connexion (code: {rc})")

        def on_message(c, userdata, msg):
            payload = msg.payload.decode("utf-8", errors="replace").strip()
            print_led_visual(payload, msg.topic)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        logger.info(f"Connexion au broker MQTT [{args.broker}:{args.port}]...")
        client.connect(args.broker, args.port, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Arrêt de l'abonné MQTT (Ctrl+C).")
    finally:
        client.disconnect()
        logger.info("Déconnecté proprement.")


if __name__ == "__main__":
    main()
