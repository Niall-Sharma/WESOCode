#!/usr/bin/env python3
"""
orchestrator.py

Co-simulation orchestrator for QBlade + Arduino.
Modes:
  - FAKE: internal simple turbine model (use this to validate serial comms & PID logic)
  - CLI:  run QBlade in batch mode (user must configure command-line call)
  - SIL:  placeholder for QBlade SIL API (requires QBlade's SDK / exported library)

Protocol with Arduino (text):
  - Orchestrator sends: "RPM:123.456\n"
  - Arduino replies:    "PITCH:12.345\n"

How to use:
  1) Edit configuration variables below (COM port, mode, paths).
  2) For FAKE mode: run the script and it will simulate a plant.
  3) For CLI mode: set QBlade_exe_path and CLI flags and adapt run_qblade_cli_once().
"""

import time
import math
import argparse
from pathlib import Path

# Optional: install pyserial and pandas if you use serial or CLI mode:
# pip install pyserial pandas

# ------------------ USER CONFIG ------------------
MODE = "FAKE"             # "FAKE", "CLI", or "SIL"
ARDUINO_SERIAL = None     # e.g. "COM3" on Windows or "/dev/ttyUSB0" on Linux. If None, uses no hardware.
ARDUINO_BAUD = 115200
STEP_SIZE = 0.1           # seconds per sim step
T_END = 60.0              # total simulated seconds
QBlade_exe_path = r"C:\Program Files\QBlade\qblade.exe"   # used if MODE=="CLI"
QPRJ_PATH = r"C:\path\to\my_turbine.qprj"                # your QBlade project
SIM_NAME = "MyTimeDomainSim"                             # simulation name inside project (if needed)
OUTPUT_DIR = Path("./qblade_outputs")
OUTPUT_CSV_PATH = OUTPUT_DIR / "last_sim_output.csv"
# -------------------------------------------------

# ------------------ Imports (runtime) ------------------
try:
    import serial
except Exception:
    serial = None

try:
    import pandas as pd
except Exception:
    pd = None

# ------------------ Utilities ------------------
def log(*a):
    print("[orch]", *a)

# ------------------ Arduino comms ------------------
def start_arduino_serial(port, baud=115200, timeout=1.0):
    if serial is None:
        raise RuntimeError("pyserial not installed. Run: pip install pyserial")
    ser = serial.Serial(port, baud, timeout=timeout)
    time.sleep(2.0)  # allow Arduino auto-reset
    log("Connected to Arduino on", port)
    return ser

def send_rpm_and_get_pitch(ser, rpm, timeout=1.0):
    """
    Send RPM as ASCII and await "PITCH:xx" response.
    Returns float pitch in degrees, or None on timeout/parse error.
    """
    line = f"RPM:{rpm:.3f}\n"
    ser.write(line.encode('ascii'))
    t0 = time.time()
    while time.time() - t0 < timeout:
        raw = ser.readline().decode('ascii', errors='ignore').strip()
        if not raw:
            continue
        # Expected format: PITCH:12.345
        if raw.upper().startswith("PITCH:"):
            try:
                return float(raw.split(":",1)[1])
            except:
                return None
        # allow Arduino to send other debug lines (we'll log them)
        log("Arduino:", raw)
    log("Arduino response timeout")
    return None

# ------------------ FAKE plant ------------------
class FakeTurbine:
    """
    Very simple 1-DOF rotor model mapping pitch -> rotor speed.
    This is intentionally simplistic: RPM_dot = f(wind, pitch, damping)
    Useful for testing control logic without QBlade.
    """
    def __init__(self, wind_speed=8.0):
        self.wind = wind_speed
        self.rpm = 0.0
        self.inertia = 1.0
        self.damping = 0.02

    def step(self, pitch_deg, dt):
        # Map pitch (deg) to aerodynamic torque roughly: less pitch -> more torque
        # torque ~ c1 * (wind^3) * cos(pitch) - c2 * rpm
        c1 = 0.0008
        c2 = 0.002
        torque = c1 * (self.wind**3) * max(0.0, math.cos(math.radians(pitch_deg))) - c2*self.rpm
        # simple integrator for rpm (not physically accurate)
        rpm_dot = torque / (0.1 + self.inertia)
        self.rpm += rpm_dot * dt
        if self.rpm < 0: self.rpm = 0.0
        return self.rpm

# ------------------ QBlade CLI fallback (placeholder) ------------------
def run_qblade_cli_once(qblade_exe_path, qprj_path, sim_name, output_csv_path, prescribed_pitch_deg, step_size, sim_duration):
    """
    Placeholder for running QBlade via CLI for a short time window.
    QBlade CLI flags differ between versions; please replace the 'cmd' below with the
    correct invocation for your QBlade installation. The function should write any
    prescribed-pitch input files required by your project before invoking QBlade, and
    should ensure the output CSV is written to 'output_csv_path'.
    """
    # Example: create directory, write a simple 'prescribed_pitch.csv'
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    sim_input = output_csv_path.parent / "prescribed_pitch.csv"
    with open(sim_input, "w") as f:
        f.write("time[s],pitch[deg]\n")
        f.write(f"0.0,{prescribed_pitch_deg}\n")
        f.write(f"{sim_duration},{prescribed_pitch_deg}\n")
    # Build the command (THIS IS A PLACEHOLDER - edit for your QBlade)
    cmd = [
        str(qblade_exe_path),
        "--project", str(qprj_path),
        "--run-sim", sim_name,
        "--prescribed-input", str(sim_input),
        "--output", str(output_csv_path),
        "--t_end", str(sim_duration),
        "--t_step", str(step_size)
    ]
    log("Would run QBlade CLI (placeholder):", " ".join(cmd))
    # If you have a working command, run it:
    # import subprocess
    # subprocess.run(cmd, check=True)
    # For now, we can't run QBlade here — calling code should ensure QBlade runs and creates output_csv_path
    # We'll raise NotImplementedError to indicate user must supply correct invocation.
    raise NotImplementedError("Replace run_qblade_cli_once() with the correct QBlade CLI invocation for your installation.")

def read_latest_rpm_from_csv(output_csv_path):
    if pd is None:
        raise RuntimeError("pandas required to parse QBlade CSV. Install: pip install pandas")
    df = pd.read_csv(output_csv_path)
    # attempt to find an RPM-like column:
    candidates = [c for c in df.columns if "rpm" in c.lower() or ("rotor" in c.lower() and "speed" in c.lower())]
    if candidates:
        col = candidates[0]
    else:
        # fallback numeric
        numeric = df.select_dtypes("number").columns.tolist()
        if not numeric:
            raise ValueError("No numeric columns found in QBlade CSV output.")
        col = numeric[0]
    return float(df[col].iloc[-1])

# ------------------ Main loop ------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=MODE, help="FAKE, CLI, or SIL")
    parser.add_argument("--port", default=ARDUINO_SERIAL, help="Arduino serial port (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--stepsize", type=float, default=STEP_SIZE)
    parser.add_argument("--tend", type=float, default=T_END)
    args = parser.parse_args()

    mode = args.mode.upper()
    step_size = args.stepsize
    t_end = args.tend
    ser = None
    if args.port:
        log("Attempting to open serial:", args.port)
        ser = start_arduino_serial(args.port, ARDUINO_BAUD)

    sim_time = 0.0
    pitch_cmd = 0.0   # degrees

    # Choose plant
    if mode == "FAKE":
        plant = FakeTurbine(wind_speed=8.0)
        log("Running FAKE turbine. This simulates rotor behaviour.")
        while sim_time < t_end:
            rpm = plant.step(pitch_cmd, step_size)
            log(f"time={sim_time:.2f}s rpm={rpm:.3f} pitch_cmd={pitch_cmd:.3f}")
            # exchange with Arduino if present
            if ser:
                new_pitch = send_rpm_and_get_pitch(ser, rpm)
                if new_pitch is not None:
                    pitch_cmd = new_pitch
            else:
                # If no Arduino connected, simulate a simple feedback: try to hold rpm 150 by varying pitch (for demo)
                # (this is just local, not sent to hardware)
                # We don't change pitch here to allow Arduino to be the controller.
                pass
            sim_time += step_size
            time.sleep(0.01)  # small sleep so this script doesn't max CPU
        log("FAKE sim finished.")

    elif mode == "CLI":
        output_dir = OUTPUT_DIR
        output_csv = OUTPUT_CSV_PATH
        log("Running CLI mode. You must implement run_qblade_cli_once() for your QBlade.")
        while sim_time < t_end:
            try:
                run_qblade_cli_once(QBlade_exe_path, QPRJ_PATH, SIM_NAME, output_csv, pitch_cmd, step_size, step_size)
            except NotImplementedError:
                log("CLI invocation not implemented. Exiting.")
                break
            # read rpm from CSV (user must ensure QBlade wrote it)
            rpm = read_latest_rpm_from_csv(output_csv)
            log(f"time={sim_time:.2f}s rpm={rpm:.3f} pitch_cmd={pitch_cmd:.3f}")
            if ser:
                new_pitch = send_rpm_and_get_pitch(ser, rpm)
                if new_pitch is not None:
                    pitch_cmd = new_pitch
            sim_time += step_size

    elif mode == "SIL":
        log("SIL mode selected. You must implement QBlade SIL calls for your QBlade version.")
        # Placeholder: load user DLL/SO and step sim via exported functions.
        # See QBlade docs for function signatures and examples.
        log("Exiting (SIL not implemented here).")
    else:
        log("Unknown mode:", mode)

if __name__ == "__main__":
    main()
