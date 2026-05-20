import serial
import time
import pyvjoy
import keyboard

# ===============================
# CONFIG
# ===============================

SERIAL_PORT = "COM11"
BAUDRATE = 115200

j = pyvjoy.VJoyDevice(1)

VJOY_CENTER = 16384
VJOY_MIN = 1
VJOY_MAX = 32768

# ===============================
# TUNING
# ===============================

STEER_DEADZONE_LOW = 1750
STEER_DEADZONE_HIGH = 2150

CAM_DEADZONE_LOW = 1750
CAM_DEADZONE_HIGH = 2150

STEER_SMOOTH = 1.00
CAM_SMOOTH = 0.65

STEER_CURVE = 0.65

EMERGENCY_HOLD_FRAMES = 30

# ===============================
# ESTADO
# ===============================

smooth_steer = VJOY_CENTER
smooth_cam_x = VJOY_CENTER
smooth_cam_y = VJOY_CENTER

last_state_code = 0
emergency_hold = 0

# ===============================
# SERIAL
# ===============================

ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
time.sleep(2)

print("=" * 50)
print("  KAZTHOR — ETS2 Controller Bridge v4")
print("=" * 50)
print("  Joy1 X:   Volante vJoy X")
print("  Joy2 X:   Cámara vJoy RX")
print("  Joy2 Y:   Cámara vJoy RY")
print("  BTN 1:    Acelerar W")
print("  BTN 2:    Frenar/Reversa S")
print("  Joy1 SW:  vJoy Button 1")
print("  Joy2 SW:  vJoy Button 2")
print("=" * 50)

# ===============================
# HELPERS
# ===============================

def clamp(v, mn, mx):
    return max(mn, min(mx, v))


def map_axis(value):
    value = clamp(value, 0, 4095)
    return int((value / 4095.0) * 32767) + 1


def apply_curve(raw_adc, power=STEER_CURVE):
    normalized = (raw_adc - 2048) / 2048.0
    normalized = clamp(normalized, -1.0, 1.0)

    sign = 1 if normalized >= 0 else -1
    curved = sign * (abs(normalized) ** power)

    return int(((curved + 1.0) / 2.0) * 32767) + 1


def apply_deadzone_axis(value, low, high):
    if low <= value <= high:
        return VJOY_CENTER
    return map_axis(value)


def apply_deadzone_steer(value, low, high):
    if low <= value <= high:
        return VJOY_CENTER
    return apply_curve(value)


def smooth(current, target, factor):
    return int(current * (1.0 - factor) + target * factor)


# ===============================
# MAIN LOOP
# ===============================

while True:
    try:
        line = ser.readline().decode("utf-8", errors="ignore").strip()

        if not line or line.startswith("{"):
            continue

        parts = line.split(",")

        if len(parts) != 8:
            continue

        joy1X = int(parts[0])
        joy2Y = int(parts[1])
        joy2X = int(parts[2])
        engineBtn = int(parts[3])
        lightsBtn = int(parts[4])
        joy1Btn = int(parts[5])
        joy2Btn = int(parts[6])
        state_code = int(parts[7])

        # ===============================
        # PARADA DE EMERGENCIA
        # ===============================

        if state_code == 2:
            if last_state_code != 2:
                print("🚨 CRITICAL — PARADA DE EMERGENCIA")

            keyboard.release("w")
            keyboard.press("s")

            j.set_axis(pyvjoy.HID_USAGE_X, smooth_steer)
            j.set_axis(pyvjoy.HID_USAGE_RX, VJOY_CENTER)
            j.set_axis(pyvjoy.HID_USAGE_RY, VJOY_CENTER)

            j.set_button(1, 0)
            j.set_button(2, 0)

            emergency_hold = EMERGENCY_HOLD_FRAMES
            last_state_code = state_code

            print(f"🛑 EMERGENCY BRAKE state:{state_code}")
            continue

        # ===============================
        # SALIDA DE ESTADO CRÍTICO
        # ===============================

        if emergency_hold > 0:
            emergency_hold -= 1

            if emergency_hold > 0:
                keyboard.release("w")
                keyboard.press("s")
                continue
            else:
                keyboard.release("s")
                print("✅ Retomando control normal")

        # ===============================
        # VOLANTE — JOYSTICK 1 X
        # ===============================

        steer_target = apply_deadzone_steer(
            joy1X,
            STEER_DEADZONE_LOW,
            STEER_DEADZONE_HIGH
        )

        smooth_steer = smooth(smooth_steer, steer_target, STEER_SMOOTH)
        j.set_axis(pyvjoy.HID_USAGE_X, smooth_steer)

        # ===============================
        # CÁMARA — JOYSTICK 2 
        # ===============================

        cam_x_target = apply_deadzone_axis(
            joy2X,
            CAM_DEADZONE_LOW,
            CAM_DEADZONE_HIGH
        )

        cam_y_target = apply_deadzone_axis(
            joy2Y,
            CAM_DEADZONE_LOW,
            CAM_DEADZONE_HIGH
        )

        smooth_cam_x = smooth(smooth_cam_x, cam_x_target, CAM_SMOOTH)
        smooth_cam_y = smooth(smooth_cam_y, cam_y_target, CAM_SMOOTH)

        j.set_axis(pyvjoy.HID_USAGE_RX, smooth_cam_x)
        j.set_axis(pyvjoy.HID_USAGE_RY, smooth_cam_y)

        # ===============================
        # ACELERAR / FRENAR
        # ===============================

        if engineBtn == 1 and lightsBtn == 0:
            keyboard.press("w")
            keyboard.release("s")

        elif lightsBtn == 1 and engineBtn == 0:
            keyboard.press("s")
            keyboard.release("w")

        else:
            keyboard.release("w")
            keyboard.release("s")

        # ===============================
        # PULSADORES JOYSTICK → VJOY BUTTONS
        # ===============================

        j.set_button(1, 1 if joy1Btn == 1 else 0)
        j.set_button(2, 1 if joy2Btn == 1 else 0)

        last_state_code = state_code

        estado_txt = ["NORMAL", "⚠ WARN", "🚨 CRIT"][state_code]

        print(
            f"STR:{joy1X:4d}->{smooth_steer:5d} | "
            f"CAM_X:{joy2X:4d}->{smooth_cam_x:5d} "
            f"CAM_Y:{joy2Y:4d}->{smooth_cam_y:5d} | "
            f"ACC:{engineBtn} BRK:{lightsBtn} | "
            f"B1:{joy1Btn} B2:{joy2Btn} | "
            f"{estado_txt}"
        )

    except ValueError:
        pass

    except KeyboardInterrupt:
        keyboard.release("w")
        keyboard.release("s")
        j.set_button(1, 0)
        j.set_button(2, 0)
        print("\nPrograma detenido.")
        break

    except Exception as e:
        keyboard.release("w")
        keyboard.release("s")
        j.set_button(1, 0)
        j.set_button(2, 0)
        print(f"ERROR: {e}")