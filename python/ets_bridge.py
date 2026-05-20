
import json
import ssl
import time
import requests
import paho.mqtt.client as mqtt


# ====================================================
#  MQTT
# ====================================================
MQTT_HOST = ""
MQTT_PORT = 8883
MQTT_USER = ""
MQTT_PASS = ""
TOPIC     = "kazthor/truck01/game"


# ====================================================
# ====================================================
ETS2_URL_A = "http://127.0.0.1:25555/api/ets2/telemetry"

# Opción B: scs-telemetry-server (npm)
ETS2_URL_B = "http://127.0.0.1:25555/api"

# Opción C: ets2-dashboard-skin
ETS2_URL_C = "http://127.0.0.1:3000/api/telemetry"

ETS2_URL = ETS2_URL_A

INTERVALO    = 0.25   
TIMEOUT_HTTP = 2      


# ====================================================
#  ESTADO
# ====================================================
mqtt_conectado   = False
ets2_conectado   = False
errores_seguidos = 0
MAX_ERRORES      = 10 


# ====================================================
#  MQTT
# ====================================================
def on_connect(client, userdata, flags, rc):
    global mqtt_conectado
    if rc == 0:
        mqtt_conectado = True
        print("✅ MQTT conectado")
    else:
        print(f"❌ MQTT error código: {rc}")

def on_disconnect(client, userdata, rc):
    global mqtt_conectado
    mqtt_conectado = False
    print("⚠ MQTT desconectado — reintentando...")


# ====================================================
#  PARSEAR RESPUESTA DE ETS2
# ====================================================
def parsear_telemetria(data):
    try:
        # ── Formato Funbit  ───────────────
        if "truck" in data:
            truck = data["truck"]
            game  = data.get("game", {})
            nav   = data.get("navigation", {})

            fuel_cap = truck.get("fuelCapacity", 1)
            fuel_act = truck.get("fuel", 0)
            fuel_pct = round((fuel_act / max(fuel_cap, 1)) * 100, 1)

            # Daño total 
            wear_vals = [
                truck.get("wearEngine", 0),
                truck.get("wearTransmission", 0),
                truck.get("wearCabin", 0),
                truck.get("wearChassis", 0),
            ]
            damage_pct = round(sum(wear_vals) / len(wear_vals) * 100, 2)

            return {
                "connected":   game.get("connected", True),
                "paused":      game.get("paused", False),
                "speed":       round(abs(truck.get("speed", 0)), 1),
                "rpm":         round(truck.get("engineRpm", 0)),
                "gear":        truck.get("displayedGear", 0),
                "fuel":        fuel_pct,
                "waterTemp":   round(truck.get("waterTemperature", 0), 1),
                "oilTemp":     round(truck.get("oilTemperature", 0), 1),
                "airPressure": round(truck.get("airPressure", 0), 1),
                "engineOn":    truck.get("engineOn", False),
                "parkBrake":   truck.get("parkBrakeOn", False),
                "beacon":      truck.get("lightsBeaconOn", False),
                "damage":      damage_pct,
                "speedLimit":  nav.get("speedLimit", 0),
                "cruiseControl": truck.get("cruiseControlOn", False),
                "odometer":    round(truck.get("odometer", 0)),
            }

        elif "speed" in data:
            fuel_pct = 0
            if data.get("maxFuel", 0) > 0:
                fuel_pct = round((data.get("fuel", 0) / data["maxFuel"]) * 100, 1)

            return {
                "connected":   True,
                "paused":      data.get("paused", False),
                "speed":       round(abs(data.get("speed", 0)) * 3.6, 1),  # m/s → km/h
                "rpm":         round(data.get("engineRpm", 0)),
                "gear":        data.get("gear", 0),
                "fuel":        fuel_pct,
                "waterTemp":   round(data.get("waterTemperature", 0), 1),
                "oilTemp":     round(data.get("oilTemperature", 0), 1),
                "airPressure": round(data.get("airPressure", 0), 1),
                "engineOn":    data.get("engineEnabled", False),
                "parkBrake":   data.get("parkBrake", False),
                "beacon":      data.get("lightsBeacon", False),
                "damage":      round(data.get("wearEngine", 0) * 100, 2),
                "speedLimit":  data.get("navigationSpeedLimit", 0),
                "cruiseControl": data.get("cruiseControl", False),
                "odometer":    round(data.get("odometer", 0)),
            }

        else:
            print("⚠ Formato desconocido:", list(data.keys())[:5])
            return None

    except Exception as e:
        print(f"❌ Error parseando telemetría: {e}")
        return None


# ====================================================
#  MAIN
# ====================================================
print("=" * 50)
print("  KAZTHOR — ETS2 Telemetry Bridge v2.0")
print("=" * 50)
print(f"  API URL: {ETS2_URL}")
print(f"  MQTT:    {MQTT_HOST}:{MQTT_PORT}")
print(f"  Topic:   {TOPIC}")
print("=" * 50)

# Conectar MQTT
client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)
client.on_connect    = on_connect
client.on_disconnect = on_disconnect

print("Conectando MQTT...")
client.connect(MQTT_HOST, MQTT_PORT)
client.loop_start()
time.sleep(1)

print("Iniciando lectura de ETS2...")
print("(Abre ETS2 si no está abierto)\n")

ciclo = 0

try:
    while True:
        ciclo += 1
        try:
            resp = requests.get(ETS2_URL, timeout=TIMEOUT_HTTP)
            resp.raise_for_status()
            raw = resp.json()

            payload = parsear_telemetria(raw)

            if payload:
                msg = json.dumps(payload)
                result = client.publish(TOPIC, msg, qos=0)

                errores_seguidos = 0

                if ciclo % 4 == 0:
                    estado_ets = "▶ JUGANDO" if not payload["paused"] else "⏸ PAUSADO"
                    motor      = "ON" if payload["engineOn"] else "OFF"
                    print(
                        f"{estado_ets} | "
                        f"v:{payload['speed']:5.1f}km/h | "
                        f"rpm:{payload['rpm']:4d} | "
                        f"gear:{payload['gear']:2d} | "
                        f"fuel:{payload['fuel']:4.1f}% | "
                        f"wT:{payload['waterTemp']:5.1f}°C | "
                        f"dmg:{payload['damage']:4.2f}% | "
                        f"motor:{motor}"
                    )

                if not ets2_conectado:
                    ets2_conectado = True
                    print("✅ ETS2 conectado — leyendo telemetría")

        except requests.exceptions.ConnectionError:
            errores_seguidos += 1
            if errores_seguidos == 1 or errores_seguidos % 20 == 0:
                print(
                    f"⚠ ETS2 no responde ({errores_seguidos} intentos) — "
                    f"¿está abierto el juego y el plugin?"
                )
            ets2_conectado = False

        except requests.exceptions.Timeout:
            print("⚠ Timeout leyendo ETS2")

        except json.JSONDecodeError as e:
            print(f"❌ Respuesta inválida de ETS2: {e}")

        except Exception as e:
            print(f"❌ Error inesperado: {e}")

        time.sleep(INTERVALO)

except KeyboardInterrupt:
    print("\nDeteniendo bridge...")
    client.loop_stop()
    print("Listo.")