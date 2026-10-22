/*
  Projet M2 IoT : Contrôle d'Accès par Geste - Actionneur LED ESP32 (Wokwi)
  ========================================================================
  Ce programme s'exécute sur une carte ESP32 simulée dans Wokwi.
  Il se connecte au WiFi simulé (Wokwi-GUEST), s'abonne au topic MQTT
  "idet/led/status" sur le broker public "test.mosquitto.org", et pilote
  l'état d'une LED connectée sur la broche GPIO 23.
  
  Matériel simulé dans Wokwi :
  - ESP32 DevKit v4
  - LED verte (Anode sur GPIO 23, Cathode via résistance 220 ohms au GND)
  - Résistance 220 ohms
*/

#include <WiFi.h>
#include <PubSubClient.h>

// Configuration des broches
const int LED_PIN = 23;        // Broche GPIO connectée à la LED
const int BUILTIN_LED = 2;     // LED intégrée ESP32 (témoin secondaire)

// Configuration WiFi Wokwi
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// Configuration MQTT
const char* MQTT_BROKER = "test.mosquitto.org";
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "idet/led/status";

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Fonction de rappel lors de la réception d'un message MQTT
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  message.trim();

  Serial.println("----------------------------------------------");
  Serial.print("[MQTT REÇU] Topic: ");
  Serial.println(topic);
  Serial.print("[MQTT REÇU] Message: ");
  Serial.println(message);

  // Commande de la LED selon l'ordre reçu
  if (message.equalsIgnoreCase("ON")) {
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUILTIN_LED, HIGH);
    Serial.println(">>> [ACCÈS AUTORISÉ] : LED ALLUMÉE (HIGH) <<<");
  } 
  else if (message.equalsIgnoreCase("OFF")) {
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUILTIN_LED, LOW);
    Serial.println(">>> [ACCÈS VERROUILLÉ] : LED ÉTEINTE (LOW) <<<");
  } 
  else {
    Serial.print("Commande inconnue : ");
    Serial.println(message);
  }
  Serial.println("----------------------------------------------");
}

// Connexion au réseau WiFi Wokwi
void setupWifi() {
  delay(10);
  Serial.println();
  Serial.print("Connexion au WiFi ");
  Serial.print(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connecté avec succès !");
  Serial.print("Adresse IP ESP32 : ");
  Serial.println(WiFi.localIP());
}

// Reconnexion automatique au broker MQTT
void reconnectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connexion au broker MQTT (");
    Serial.print(MQTT_BROKER);
    Serial.print(")... ");

    // Génération d'un identifiant client unique
    String clientId = "ESP32_Wokwi_LED_" + String(random(0xffff), HEX);

    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("CONNECTÉ !");
      // Abonnement au topic
      mqttClient.subscribe(MQTT_TOPIC);
      Serial.print("Abonné avec succès au topic : ");
      Serial.println(MQTT_TOPIC);
      Serial.println("En attente des gestes de la caméra...");
    } else {
      Serial.print("Échec, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" - Nouvelle tentative dans 3 secondes...");
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("==============================================");
  Serial.println("   ESP32 GESTURE ACCESS CONTROL (WOKWI)      ");
  Serial.println("==============================================");

  // Configuration des broches en sortie
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUILTIN_LED, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  digitalWrite(BUILTIN_LED, LOW);

  // Connexion WiFi
  setupWifi();

  // Configuration client MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();
}
