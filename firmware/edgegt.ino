#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ===============================
// WIFI
// ===============================

const char *WIFI_SSID = "";
const char *WIFI_PASS = "";

// ===============================
// MQTT
// ===============================

const char *MQTT_HOST = "";
const int MQTT_PORT = 8883;
const char *MQTT_USER = "";
const char *MQTT_PASS = "";

const char *TOPIC_EDGE = "kazthor/edge/truck01";
const char *TOPIC_GAME = "kazthor/truck01/game";

// ===============================
// OLED
// ===============================

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ===============================
// JOYSTICK 1  (steering)
// ===============================

#define JOY1_X 34
#define JOY1_Y 35 
#define JOY1_SW 14

// ===============================
// JOYSTICK 2  
// ===============================

#define JOY2_X 36 
#define JOY2_Y 39 
#define JOY2_SW 13

// ===============================
// BOTONES
// ===============================

#define BTN_ENGINE 18
#define BTN_LIGHTS 19

// ===============================
// SENSORES
// ===============================

#define TEMP_PIN 32
#define WATER_PIN 33

// ===============================
// SALIDAS
// ===============================

#define BUZZER_PIN 25
#define LED_GREEN 26
#define LED_RED 27

// ===============================
// OBJETOS
// ===============================

OneWire oneWire(TEMP_PIN);
DallasTemperature tempSensor(&oneWire);

WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);

// ===============================
// DATOS ETS2 (via MQTT)
// ===============================

bool gameConnected = false;
float etsSpeed = 0;
int etsRpm = 0;
int etsGear = 0;
float etsFuel = 0;
float etsWaterTemp = 0;
float etsDamage = 0;
bool etsEngineOn = false;
unsigned long lastGameMsg = 0;

// ===============================
// DEBOUNCE BOTONES
// ===============================

bool enginePressedEvent = false;
bool lightsPressedEvent = false;
bool lastEngineReading = HIGH;
bool lastLightsReading = HIGH;
unsigned long lastEngineDebounce = 0;
unsigned long lastLightsDebounce = 0;
const unsigned long debounceDelay = 60;

bool engineStableState = HIGH;
bool lightsStableState = HIGH;

// ===============================
// WIFI
// ===============================

void connectWiFi()
{
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WIFI OK");
}

// ===============================
// MQTT CALLBACK
// ===============================

void mqttCallback(char *topic, byte *payload, unsigned int length)
{
  String msg = "";

  for (unsigned int i = 0; i < length; i++)
  {
    msg += (char)payload[i];
  }

  if (String(topic) == TOPIC_GAME)
  {
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, msg);

    if (!error)
    {
      gameConnected = doc["connected"] | false;
      etsSpeed = doc["speed"] | 0;
      etsRpm = doc["rpm"] | 0;
      etsGear = doc["gear"] | 0;
      etsFuel = doc["fuel"] | 0;
      etsWaterTemp = doc["waterTemp"] | 0;
      etsDamage = doc["damage"] | 0;
      etsEngineOn = doc["engineOn"] | false;
      lastGameMsg = millis();
    }
  }
}

// ===============================
// MQTT CONNECT
// ===============================

void connectMQTT()
{
  while (!mqtt.connected())
  {
    Serial.println("MQTT connecting...");

    String clientId = "kazthor-edge-" + String(random(0xffff), HEX);

    if (mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS))
    {
      Serial.println("MQTT OK");
      mqtt.subscribe(TOPIC_GAME);
    }
    else
    {
      Serial.print("MQTT retry, rc=");
      Serial.println(mqtt.state());
      delay(2000);
    }
  }
}

// ===============================
// LEER BOTONES CON DEBOUNCE
// ===============================

void readButtons()
{
  enginePressedEvent = false;
  lightsPressedEvent = false;

  bool engineReading = digitalRead(BTN_ENGINE);
  bool lightsReading = digitalRead(BTN_LIGHTS);

  if (engineReading != lastEngineReading)
    lastEngineDebounce = millis();

  if (lightsReading != lastLightsReading)
    lastLightsDebounce = millis();

  if ((millis() - lastEngineDebounce) > debounceDelay)
  {
    if (engineStableState == HIGH && engineReading == LOW)
      enginePressedEvent = true;
    engineStableState = engineReading;
  }

  if ((millis() - lastLightsDebounce) > debounceDelay)
  {
    if (lastLightsReading == HIGH && lightsReading == LOW)
      lightsPressedEvent = true;
    lightsStableState = lightsReading;
  }

  lastEngineReading = engineReading;
  lastLightsReading = lightsReading;
}

// ===============================
// SETUP
// ===============================

void setup()
{
  Serial.begin(115200);

  Wire.begin(21, 22);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
  {
    Serial.println("OLED FAIL");
    while (true)
      ;
  }

  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(2);
  display.setCursor(0, 20);
  display.println("KAZTHOR");
  display.display();
  delay(1500);

  tempSensor.begin();

  pinMode(JOY1_SW, INPUT_PULLUP);
  pinMode(JOY2_SW, INPUT_PULLUP);
  pinMode(BTN_ENGINE, INPUT_PULLUP);
  pinMode(BTN_LIGHTS, INPUT_PULLUP);

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);

  ledcAttach(BUZZER_PIN, 1000, 8);

  connectWiFi();

  wifiClient.setInsecure();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setKeepAlive(60);
  mqtt.setBufferSize(768);

  connectMQTT();
}

// ===============================
// LOOP
// ===============================

void loop()
{
  // ── MQTT ──────────────────────────────────────
  if (!mqtt.connected())
    connectMQTT();

  mqtt.loop();

  // ── LEER JOYSTICKS ────────────────────────────
  int joy1X = analogRead(JOY1_X); // steering
  int joy2Y = analogRead(JOY2_Y); // throttle
  int joy2X = analogRead(JOY2_X); // brake
  bool joy1Pressed = (digitalRead(JOY1_SW) == LOW);
  bool joy2Pressed = (digitalRead(JOY2_SW) == LOW);

  // ── BOTONES ───────────────────────────────────
  readButtons();

  // ── SENSORES ──────────────────────────────────
  tempSensor.requestTemperatures();
  float tempC = tempSensor.getTempCByIndex(0);

  int waterRaw = analogRead(WATER_PIN);
  int waterPercent = constrain(map(waterRaw, 0, 4095, 0, 100), 0, 100);

  // ── TIMEOUT ETS2 ──────────────────────────────
  if (millis() - lastGameMsg > 3000)
    gameConnected = false;

  // ── ALERTAS ───────────────────────────────────
  bool edgeCritical = (tempC > 95) || (waterPercent < 20);
  bool gameCritical = gameConnected && ((etsWaterTemp > 100) || (etsDamage > 5));
  bool warning = (tempC > 80) || (gameConnected && ((etsWaterTemp > 90) || (etsFuel < 20)));

  String state = "NORMAL";

  if (edgeCritical || gameCritical)
  {
    state = "CRITICAL";
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_RED, HIGH);
    ledcWriteTone(BUZZER_PIN, 1000);
  }
  else if (warning)
  {
    state = "WARNING";
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_RED, HIGH);
    ledcWriteTone(BUZZER_PIN, 0);
  }
  else
  {
    state = "NORMAL";
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_RED, LOW);
    ledcWriteTone(BUZZER_PIN, 0);
  }

  // ── OLED ──────────────────────────────────────
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(1);

  if (gameConnected)
  {
    display.setCursor(0, 0);
    display.println("ETS2 LIVE");

    display.setCursor(0, 14);
    display.print("SPD:");
    display.print(abs(etsSpeed), 1);

    display.setCursor(70, 14);
    display.print("G:");
    display.print(etsGear);

    display.setCursor(0, 28);
    display.print("RPM:");
    display.print(etsRpm);

    display.setCursor(70, 28);
    display.print("F:");
    display.print(etsFuel, 0);
    display.print("%");

    display.setCursor(0, 42);
    display.print("WT:");
    display.print(etsWaterTemp, 1);
    display.print("C");

    display.setCursor(70, 42);
    display.print("D:");
    display.print(etsDamage, 1);

    display.setCursor(0, 54);
    display.print(state);
  }
  else
  {
    display.setCursor(0, 0);
    display.println("KAZTHOR EDGE");

    display.setCursor(0, 14);
    display.print("T:");
    display.print(tempC, 1);
    display.print("C");

    display.setCursor(70, 14);
    display.print("W:");
    display.print(waterPercent);
    display.print("%");

    display.setCursor(0, 28);
    display.print(state);

    display.setCursor(0, 42);
    display.print("S:");
    display.print(joy1X);

    display.setCursor(66, 42);
    display.print("T:");
    display.print(joy2Y);

    display.setCursor(0, 54);
    display.print("B:");
    display.print(joy2X);
  }

  display.display();

  // ── MQTT PUBLISH (telemetria edge) ────────────
  StaticJsonDocument<512> doc;

  doc["temp"] = tempC;
  doc["water"] = waterPercent;
  doc["joyX"] = joy1X;
  doc["joy2Y"] = joy2Y;
  doc["joy2X"] = joy2X;
  doc["joySW"] = joy1Pressed ? 1 : 0;
  doc["joy2SW"] = joy2Pressed ? 1 : 0;
  doc["engineBtn"] = enginePressedEvent ? 1 : 0;
  doc["lightsBtn"] = lightsPressedEvent ? 1 : 0;
  doc["state"] = state;

  char mqttPayload[512];
  serializeJson(doc, mqttPayload);
  mqtt.publish(TOPIC_EDGE, mqttPayload);

  // ── SERIAL USB → Python vJoy ──────────────────

  int stateCode = 0;
  if (state == "CRITICAL")
    stateCode = 2;
  else if (state == "WARNING")
    stateCode = 1;

  Serial.print(joy1X);
  Serial.print(",");
  Serial.print(joy2Y);
  Serial.print(",");
  Serial.print(joy2X);
  Serial.print(",");
  Serial.print(enginePressedEvent ? 1 : 0);
  Serial.print(",");
  Serial.print(lightsPressedEvent ? 1 : 0);
  Serial.print(",");
  Serial.print(joy1Pressed ? 1 : 0);
  Serial.print(",");
  Serial.print(joy2Pressed ? 1 : 0);
  Serial.print(",");
  Serial.println(stateCode);

  delay(20);
}
