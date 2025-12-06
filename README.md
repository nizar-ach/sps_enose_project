Here is the **simple, clean, natural English version**, written as **one unified README** without emojis:

---

```markdown
# SPS e-Nose Project

This project provides a complete data acquisition pipeline for an electronic nose (e-nose) system. It consists of an Arduino-based sensor module, a Rust backend that exposes a REST API, and a Python frontend for visualization, data logging, and uploading CSV datasets to Edge Impulse for model training.

## System Architecture

Gas Sensors → Arduino → Rust Backend (REST API) → Python Frontend → Edge Impulse

- The Arduino reads sensor values from the e-nose array and sends them over a serial connection.
- The Rust backend receives this data and provides an HTTP API for retrieving sensor readings and sending control commands.
- The Python frontend displays the incoming data, allows saving datasets to CSV, and supports uploading these CSV files to Edge Impulse.

## Features

- Real-time sensor data acquisition from Arduino.
- REST API for data retrieval and system control.
- Python-based dashboard for monitoring and visualization.
- CSV data logging for dataset generation.
- CSV upload directly to Edge Impulse for training machine learning models.

## Project Structure

```

backend/    - Rust-based API server (serial communication + REST endpoints)
firmware/   - Arduino code for reading sensors
frontend/   - Python application for visualization and CSV management

```

## How to Run the System

### 1. Arduino Firmware
1. Open the `firmware` directory.
2. Upload the `.ino` file to the Arduino using the Arduino IDE.
3. Ensure the serial port and baud rate match the backend configuration.

### 2. Rust Backend

```

cd backend
cargo run

```

The backend will:
- Read incoming data from the Arduino via serial.
- Provide HTTP endpoints such as:
  - `GET /sensors` for retrieving current sensor readings
  - `POST /control` for sending control commands

### 3. Python Frontend

```

cd frontend
pip install -r requirements.txt
python app.py

```

The frontend will:
- Connect to the backend API
- Display real-time data
- Save datasets to CSV
- Upload CSV files to Edge Impulse

## Uploading CSV to Edge Impulse

The frontend provides an interface for selecting a CSV file.  
The file is then sent to Edge Impulse using the project's API key and the official ingestion endpoint.  
Uploaded data will appear in the Edge Impulse “Data Acquisition” page.

## System Workflow Summary

1. The Arduino collects gas sensor data.
2. The Rust backend receives the data and exposes it through an HTTP API.
3. The Python frontend requests data from the backend and visualizes it.
4. The user records and exports data as CSV.
5. CSV files are uploaded to Edge Impulse for model training.

---

If you want, I can further shorten this, make it more formal, or adjust it to match your actual folder names and API routes.
```
