# Electronic Nose System

Arduino UNO R4 WiFi + Rust Backend + Python Frontend

This project implements a complete E-Nose data pipeline consisting of an Arduino firmware (sensor acquisition + FSM), a Rust backend (data relay + command gateway), and a Python frontend (real-time GUI + CSV export + Edge Impulse upload).

---

# 1. Arduino System (Arduino IDE)

**File:** `arduino_code/untu kard uinosps.ino`
**Responsibilities:**

### 1. WiFi Communication

```cpp
const char* ssid = "...";
const char* pass = "...";
const char* RUST_IP = "...";  // Backend IP
const int   RUST_PORT = 8081;
```

### 2. Sensor Acquisition

* GMXXX Multichannel Gas Sensor
* MICS analog gas sensor (`A1`)

Reads: NO₂, C₂H₅OH, VOC, CO (GMXXX)
Reads: MICS analog channels processed into relative values

### 3. Motor Control + FSM

FSM states:

```
IDLE → PRE_COND → RAMP_UP → HOLD → PURGE → RECOVERY → DONE
```

Each cycle runs across 5 motor speed levels:

```cpp
const int speeds[5] = {51,102,153,204,255};
```

Commands via Serial:

```
START_SAMPLING
STOP_SAMPLING
```

### 4. Data Transmission (every 250 ms)

Arduino sends:

```
SENSOR:no2,eth,voc,co,co_mics,eth_mics,voc_mics,state,level
```

Via TCP to Rust backend.

---

# 2. Rust Backend System

**File:** `backend/src/main.rs`
Acts as the central gateway between Arduino and the Python GUI.

### 1. TCP Receiver (from Arduino)

Listens on `0.0.0.0:8081`.

For each line:

1. Parse sensor values
2. Store into memory buffer
3. Broadcast to GUI (TCP 8083)

### 2. TCP Broadcaster (to GUI)

GUI connects to `0.0.0.0:8083`
Receives continuous sensor stream in `SENSOR:...` format.

### 3. Command Receiver (from GUI)

GUI sends:

```
START_SAMPLING
STOP_SAMPLING
```

Backend listens on `0.0.0.0:8082`
Then forwards command to Arduino via Serial port (e.g., `COM8`).

### 4. Optional InfluxDB Logging

Backend can write each frame using InfluxDB line protocol.

### 5. Minimal HTTP API

* `/` health check
* `/sensor_data` full buffer dump
* `/motor_status` FSM state info

---

# 3. Python Frontend System (PyQt GUI)

**File:** `frontend/main.py`

### 1. TCP Connections

* Data stream from backend:
  `host=127.0.0.1`, `port=8083`
* Command channel to backend:
  `host=127.0.0.1`, `port=8082`

### 2. Real-Time Dashboard

Using PyQt6 + pyqtgraph:

* Seven sensor plots (GMXXX + MICS)
* Combined sensor plot
* Display FSM state and motor level
* Connection and sample status

### 3. Data Storage

On user request:

```
data/<sample_name>_<timestamp>.csv
data/<sample_name>_<timestamp>.json
```

### 4. Edge Impulse Upload

Uploads CSV to EI ingestion API:

```
POST https://ingestion.edgeimpulse.com/api/training/files
Headers:
  x-api-key: <key>
  x-label: <label>
Body: multipart/form-data containing CSV file
```

Success response confirms that data is stored in EI's Data Acquisition tab.

### 5. Sampling Control

GUI buttons:

```
Start Sampling → send START_SAMPLING
Stop Sampling  → send STOP_SAMPLING
Save & Upload  → store locally and upload to EI
```

---

# Summary (Most Compact)

| Layer                 | Role                                           | Protocol             |
| --------------------- | ---------------------------------------------- | -------------------- |
| **Arduino**           | Sensors, Motor FSM, TCP data sender            | WiFi TCP → Backend   |
| **Backend (Rust)**    | Relay data, forward commands, broadcast to GUI | TCP 8081, 8082, 8083 |
| **Frontend (Python)** | Plot, save CSV/JSON, upload to Edge Impulse    | TCP, HTTP            |

