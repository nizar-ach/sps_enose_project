// src/main.rs - E-NOSE BACKEND v3.1 (FIXED InfluxDB Integration)
// With proper error handling & connection testing

use actix_web::{web, App, HttpResponse, HttpServer, Responder, middleware};
use actix_cors::Cors;
use serde::Serialize;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use std::io::{BufRead, BufReader, Write};
use std::thread;
use std::time::Duration;
use std::net::TcpListener;
use log::{info, warn, error};
use std::sync::mpsc::{channel, Sender};
use serialport::SerialPort;
use influxdb2::Client;

// ===== CONSTANTS - VERIFY THESE! =====
const ARDUINO_WIFI_ADDR: &str = "0.0.0.0:8081";
const GUI_CMD_ADDR: &str = "0.0.0.0:8082";
const GUI_DATA_ADDR: &str = "0.0.0.0:8083";
const HTTP_ADDR: &str = "0.0.0.0:8080";
const SERIAL_PORT: &str = "COM8";
const BAUD_RATE: u32 = 9600;
const HTTP_PORT: u16 = 8080;

// ===== INFLUXDB CONSTANTS - CHECK THESE IN YOUR INFLUXDB UI! =====
const INFLUXDB_URL: &str = "http://localhost:8086";
const INFLUXDB_ORG: &str = "manusa";              // ← VERIFY this exact name
const INFLUXDB_BUCKET: &str = "uhuy";            // ← VERIFY this exact name
const INFLUXDB_TOKEN: &str = "1VaKG4mM_W9v2YGQHSW6_YVyc5iHQ9NvyU06CJtcf0ckJjnPU798syP3jC2qFdN5pGSKplDCWwBguZzgrfMRYA==";
// ← VERIFY token is valid (check if expired)

// ===== STRUKTUR DATA =====
#[derive(Serialize, Clone, Debug)]
struct SensorReading {
    timestamp: u64,
    sample_name: String,
    no2_gm: f64,
    eth_gm: f64,
    voc_gm: f64,
    co_gm: f64,
    co_mics: f64,
    eth_mics: f64,
    voc_mics: f64,
    motor_state: i64,
    level: i64,
}

#[derive(Serialize)]
struct SensorDataResponse {
    readings: Vec<SensorReading>,
    stats: SensorDataStats,
    total_count: usize,
}

#[derive(Serialize)]
struct SensorDataStats {
    no2_avg: f64,
    eth_avg: f64,
    voc_avg: f64,
    co_avg: f64,
    co_mics_avg: f64,
    eth_mics_avg: f64,
    voc_mics_avg: f64,
}

// ===== APP STATE =====
struct AppState {
    sensor_data: Arc<Mutex<Vec<SensorReading>>>,
    is_sampling: Arc<Mutex<bool>>,
    motor_status: Arc<Mutex<String>>,
    last_update: Arc<Mutex<u64>>,
    gui_broadcast: Arc<Mutex<Vec<Sender<String>>>>,
    serial_port: Arc<Mutex<Option<Box<dyn SerialPort>>>>,
    influxdb_client: Arc<Client>,
    influxdb_ready: Arc<Mutex<bool>>,
}

// ===== UTILITY FUNCTIONS =====
fn calculate_average(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

// ===== PARSE SENSOR DATA FROM ARDUINO =====
fn parse_sensor_line(line: &str) -> Option<SensorReading> {
    if !line.starts_with("SENSOR:") {
        return None;
    }
    
    let data_str = &line[7..];
    let parts: Vec<&str> = data_str.split(',').collect();
    
    if parts.len() < 9 {
        warn!("Invalid SENSOR format: expected 9 fields, got {}", parts.len());
        return None;
    }
    
    let parse_f64 = |s: &str| -> f64 { s.trim().parse::<f64>().unwrap_or(0.0) };
    let parse_i64 = |s: &str| -> i64 { s.trim().parse::<i64>().unwrap_or(0) };
    
    let reading = SensorReading {
        timestamp: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64,
        sample_name: String::new(),
        no2_gm: parse_f64(parts[0]),
        eth_gm: parse_f64(parts[1]),
        voc_gm: parse_f64(parts[2]),
        co_gm: parse_f64(parts[3]),
        co_mics: parse_f64(parts[4]),
        eth_mics: parse_f64(parts[5]),
        voc_mics: parse_f64(parts[6]),
        motor_state: parse_i64(parts[7]),
        level: parse_i64(parts[8]),
    };
    
    info!("✓ Sensor: NO2={:.2}ppm | Level={} | State={}", 
        reading.no2_gm, reading.level, reading.motor_state);
    Some(reading)
}

// ===== WRITE TO INFLUXDB (LINE PROTOCOL) - FIXED =====
async fn write_to_influxdb(
    client: &Client,
    reading: &SensorReading,
    influxdb_ready: &Arc<Mutex<bool>>,
) {
    // Check if InfluxDB is ready
    match influxdb_ready.lock() {
        Ok(is_ready) => {
            if !*is_ready {
                warn!("⚠️  InfluxDB not ready, skipping write");
                return;
            }
        }
        Err(_) => {
            warn!("⚠️  Cannot check InfluxDB ready state");
            return;
        }
    }

    let timestamp_ns = reading.timestamp as i64 * 1_000_000;
    
    // CORRECT LINE PROTOCOL FORMAT
    let line_protocol = format!(
        "sensor_data,device=e_nose,level={},state={} no2_gm={},eth_gm={},voc_gm={},co_gm={},co_mics={},eth_mics={},voc_mics={} {}",
        reading.level,
        reading.motor_state,
        reading.no2_gm,
        reading.eth_gm,
        reading.voc_gm,
        reading.co_gm,
        reading.co_mics,
        reading.eth_mics,
        reading.voc_mics,
        timestamp_ns
    );
    
    println!("📝 Line Protocol: {}", line_protocol);
    
    // Write to InfluxDB
    match client.write_line_protocol(INFLUXDB_ORG, INFLUXDB_BUCKET, line_protocol).await {
        Ok(_) => {
            println!("✅ [InfluxDB] Write successful");
            info!("✅ Data written to InfluxDB");
        }
        Err(e) => {
            eprintln!("❌ [InfluxDB] Write FAILED!");
            eprintln!("   Error: {}", e);
            eprintln!("   Check:");
            eprintln!("   1. InfluxDB is running");
            eprintln!("   2. Bucket name is correct: {}", INFLUXDB_BUCKET);
            eprintln!("   3. Org name is correct: {}", INFLUXDB_ORG);
            eprintln!("   4. Token is valid");
            error!("❌ InfluxDB write error: {}", e);
        }
    }
}

// ===== SEND COMMAND TO ARDUINO VIA SERIAL =====
fn send_command_to_arduino(state: &web::Data<AppState>, cmd: &str) -> Result<(), String> {
    println!("🔧 [send_command_to_arduino] Called with: {}", cmd);
    
    let mut serial = state.serial_port.lock().unwrap();
    
    if let Some(port) = serial.as_mut() {
        let cmd_with_newline = format!("{}\n", cmd);
        println!("📝 Writing to serial: {}", cmd_with_newline);
        
        match port.write_all(cmd_with_newline.as_bytes()) {
            Ok(_) => {
                println!("✅ [Serial] Write successful");
                info!("📤 Sent to Arduino via Serial: {}", cmd);
                Ok(())
            }
            Err(e) => {
                println!("❌ [Serial] Write failed: {}", e);
                error!("❌ Failed to write to Arduino serial: {}", e);
                Err(format!("Serial write error: {}", e))
            }
        }
    } else {
        println!("❌ [Serial] Port is None!");
        error!("❌ Serial port not connected!");
        Err("Serial port not connected".to_string())
    }
}

// ===== OPEN SERIAL CONNECTION TO ARDUINO =====
fn open_serial_connection() -> Result<Box<dyn SerialPort>, String> {
    println!("🔌 Attempting to open serial port: {}", SERIAL_PORT);
    
    match serialport::new(SERIAL_PORT, BAUD_RATE)
        .timeout(Duration::from_millis(100))
        .open() {
        Ok(port) => {
            println!("✅ Serial port opened: {}", SERIAL_PORT);
            info!("✅ Serial port {} opened at {} baud", SERIAL_PORT, BAUD_RATE);
            Ok(port)
        }
        Err(e) => {
            println!("❌ Failed to open serial port: {}", e);
            error!("❌ Failed to open serial port {}: {}", SERIAL_PORT, e);
            Err(format!("Cannot open {}: {}", SERIAL_PORT, e))
        }
    }
}

// ===== TCP ARDUINO DATA RECEIVER THREAD =====
fn start_tcp_arduino_receiver(state: web::Data<AppState>) {
    thread::spawn(move || {
        let listener = match TcpListener::bind(ARDUINO_WIFI_ADDR) {
            Ok(l) => l,
            Err(e) => {
                error!("❌ Failed to bind Arduino listener on {}: {}", ARDUINO_WIFI_ADDR, e);
                return;
            }
        };
        
        info!("📡 Arduino Receiver: {} (WiFi data)", ARDUINO_WIFI_ADDR);
        
        for stream_result in listener.incoming() {
            match stream_result {
                Ok(stream) => {
                    let state_clone = state.clone();
                    thread::spawn(move || {
                        let reader = BufReader::new(&stream);
                        for line_result in reader.lines() {
                            match line_result {
                                Ok(line) => {
                                    if let Some(reading) = parse_sensor_line(&line) {
                                        // Lock and update sensor data
                                        match state_clone.sensor_data.lock() {
                                            Ok(mut data) => {
                                                // Update motor status
                                                let state_names = [
                                                    "IDLE", "PRE-COND", "RAMP_UP", 
                                                    "HOLD", "PURGE", "RECOVERY", "DONE"
                                                ];
                                                let state_name = if (reading.motor_state as usize) < state_names.len() {
                                                    state_names[reading.motor_state as usize]
                                                } else {
                                                    "UNKNOWN"
                                                };
                                                
                                                let motor_msg = format!(
                                                    "{} | Level {}",
                                                    state_name, reading.level + 1
                                                );
                                                
                                                if let Ok(mut status) = state_clone.motor_status.lock() {
                                                    *status = motor_msg;
                                                }
                                                
                                                if let Ok(mut last) = state_clone.last_update.lock() {
                                                    *last = reading.timestamp;
                                                }
                                                
                                                // Keep last 1000 readings
                                                data.push(reading.clone());
                                                if data.len() > 1000 {
                                                    data.remove(0);
                                                }
                                                
                                                drop(data);
                                                
                                                // BROADCAST TO ALL GUI CLIENTS
                                                let sensor_line = format!(
                                                    "SENSOR:{:.3},{:.3},{:.3},{:.3},{:.3},{:.3},{:.3},{},{}\n",
                                                    reading.no2_gm, reading.eth_gm, reading.voc_gm, reading.co_gm,
                                                    reading.co_mics, reading.eth_mics, reading.voc_mics,
                                                    reading.motor_state, reading.level
                                                );
                                                
                                                if let Ok(mut clients) = state_clone.gui_broadcast.lock() {
                                                    clients.retain(|tx| tx.send(sensor_line.clone()).is_ok());
                                                }
                                                
                                                // WRITE TO INFLUXDB in separate thread
                                                let client_clone = state_clone.influxdb_client.clone();
                                                let reading_clone = reading.clone();
                                                let ready_clone = state_clone.influxdb_ready.clone();
                                                
                                                thread::spawn(move || {
                                                    match tokio::runtime::Runtime::new() {
                                                        Ok(rt) => {
                                                            rt.block_on(async {
                                                                write_to_influxdb(&client_clone, &reading_clone, &ready_clone).await;
                                                            });
                                                        }
                                                        Err(e) => {
                                                            eprintln!("Failed to create Tokio runtime for InfluxDB: {}", e);
                                                        }
                                                    }
                                                });
                                            }
                                            Err(e) => {
                                                error!("⚠️ Mutex poisoned: {:?}", e);
                                                break;
                                            }
                                        }
                                    }
                                }
                                Err(e) => {
                                    warn!("⚠️ Read error from Arduino: {}", e);
                                    break;
                                }
                            }
                        }
                    });
                }
                Err(e) => {
                    error!("❌ Accept error: {}", e);
                }
            }
        }
    });
}

// ===== TCP GUI DATA BROADCASTER THREAD =====
fn start_tcp_gui_data_broadcaster(state: web::Data<AppState>) {
    thread::spawn(move || {
        let listener = match TcpListener::bind(GUI_DATA_ADDR) {
            Ok(l) => l,
            Err(e) => {
                error!("❌ Failed to bind GUI data broadcaster on {}: {}", GUI_DATA_ADDR, e);
                return;
            }
        };
        
        info!("📡 GUI Data Broadcaster: {} (sensor data OUTPUT)", GUI_DATA_ADDR);
        
        for stream_result in listener.incoming() {
            match stream_result {
                Ok(mut stream) => {
                    let state_clone = state.clone();
                    thread::spawn(move || {
                        let (tx, rx) = channel::<String>();
                        
                        if let Ok(mut clients) = state_clone.gui_broadcast.lock() {
                            clients.push(tx);
                        }
                        
                        info!("✅ GUI Client Connected to Data Broadcaster!");
                        
                        while let Ok(data) = rx.recv() {
                            if stream.write_all(data.as_bytes()).is_err() {
                                warn!("⚠️ GUI client disconnected from data broadcaster");
                                break;
                            }
                        }
                    });
                }
                Err(e) => {
                    error!("❌ Accept error: {}", e);
                }
            }
        }
    });
}

// ===== TCP GUI COMMAND RECEIVER THREAD =====
fn start_tcp_gui_command_receiver(state: web::Data<AppState>) {
    thread::spawn(move || {
        let listener = match TcpListener::bind(GUI_CMD_ADDR) {
            Ok(l) => l,
            Err(e) => {
                println!("❌ Failed to bind GUI command listener on {}: {}", GUI_CMD_ADDR, e);
                error!("❌ Failed to bind GUI command listener on {}: {}", GUI_CMD_ADDR, e);
                return;
            }
        };
        
        println!("🎛️ COMMAND SERVER: Listening on {}", GUI_CMD_ADDR);
        info!("🎛️  GUI Command Receiver: {} (START/STOP)", GUI_CMD_ADDR);
        
        for stream_result in listener.incoming() {
            match stream_result {
                Ok(stream) => {
                    let state_clone = state.clone();
                    thread::spawn(move || {
                        println!("✓ New command connection received");
                        
                        let reader = BufReader::new(&stream);
                        for line_result in reader.lines() {
                            match line_result {
                                Ok(cmd_line) => {
                                    let cmd = cmd_line.trim().to_uppercase();
                                    println!("📥 Raw command from GUI: [{}]", cmd);
                                    
                                    if cmd == "START_SAMPLING" {
                                        println!("✓ Recognized START_SAMPLING");
                                        if let Ok(mut sampling) = state_clone.is_sampling.lock() {
                                            *sampling = true;
                                        }
                                        
                                        println!("🔄 Relaying to Arduino...");
                                        match send_command_to_arduino(&state_clone, "START_SAMPLING") {
                                            Ok(_) => {
                                                println!("✅ START relayed successfully");
                                                info!("✅ START_SAMPLING - Relayed to Arduino");
                                            }
                                            Err(e) => {
                                                println!("❌ Failed to relay START: {}", e);
                                                error!("❌ Failed to relay START: {}", e);
                                            }
                                        }
                                    } 
                                    else if cmd == "STOP_SAMPLING" {
                                        println!("✓ Recognized STOP_SAMPLING");
                                        if let Ok(mut sampling) = state_clone.is_sampling.lock() {
                                            *sampling = false;
                                        }
                                        
                                        println!("🔄 Relaying to Arduino...");
                                        match send_command_to_arduino(&state_clone, "STOP_SAMPLING") {
                                            Ok(_) => {
                                                println!("✅ STOP relayed successfully");
                                                info!("✅ STOP_SAMPLING - Relayed to Arduino");
                                            }
                                            Err(e) => {
                                                println!("❌ Failed to relay STOP: {}", e);
                                                error!("❌ Failed to relay STOP: {}", e);
                                            }
                                        }
                                    }
                                    else {
                                        println!("⚠️ Unknown command: [{}]", cmd);
                                        warn!("⚠️ Unknown command: {}", cmd);
                                    }
                                }
                                Err(e) => {
                                    println!("⚠️ Read error: {}", e);
                                    warn!("⚠️ Read error from GUI: {}", e);
                                    break;
                                }
                            }
                        }
                    });
                }
                Err(e) => {
                    println!("❌ Accept error: {}", e);
                    error!("❌ Accept error: {}", e);
                }
            }
        }
    });
}

// ===== HTTP HANDLERS =====
async fn health_check(data: web::Data<AppState>) -> impl Responder {
    let influxdb_status = match data.influxdb_ready.lock() {
        Ok(ready) => if *ready { "connected" } else { "disconnected" },
        Err(_) => "error"
    };
    
    HttpResponse::Ok().json(serde_json::json!({
        "status": "ok",
        "message": "E-Nose Backend v3.1 (FIXED)",
        "influxdb_status": influxdb_status,
        "arduino_wifi_addr": ARDUINO_WIFI_ADDR,
        "gui_cmd_addr": GUI_CMD_ADDR,
        "gui_data_addr": GUI_DATA_ADDR,
        "http_addr": HTTP_ADDR,
        "serial_port": SERIAL_PORT,
        "influxdb_url": INFLUXDB_URL,
        "influxdb_org": INFLUXDB_ORG,
        "influxdb_bucket": INFLUXDB_BUCKET,
    }))
}

async fn get_sensor_data(data: web::Data<AppState>) -> impl Responder {
    let readings = match data.sensor_data.lock() {
        Ok(d) => d.clone(),
        Err(_) => return HttpResponse::InternalServerError().json(serde_json::json!({"error": "Mutex poisoned"}))
    };

    if readings.is_empty() {
        return HttpResponse::Ok().json(SensorDataResponse {
            readings: vec![],
            stats: SensorDataStats {
                no2_avg: 0.0,
                eth_avg: 0.0,
                voc_avg: 0.0,
                co_avg: 0.0,
                co_mics_avg: 0.0,
                eth_mics_avg: 0.0,
                voc_mics_avg: 0.0,
            },
            total_count: 0,
        });
    }

    let total_count = readings.len();
    let stats = SensorDataStats {
        no2_avg: calculate_average(&readings.iter().map(|r| r.no2_gm).collect::<Vec<_>>()),
        eth_avg: calculate_average(&readings.iter().map(|r| r.eth_gm).collect::<Vec<_>>()),
        voc_avg: calculate_average(&readings.iter().map(|r| r.voc_gm).collect::<Vec<_>>()),
        co_avg: calculate_average(&readings.iter().map(|r| r.co_gm).collect::<Vec<_>>()),
        co_mics_avg: calculate_average(&readings.iter().map(|r| r.co_mics).collect::<Vec<_>>()),
        eth_mics_avg: calculate_average(&readings.iter().map(|r| r.eth_mics).collect::<Vec<_>>()),
        voc_mics_avg: calculate_average(&readings.iter().map(|r| r.voc_mics).collect::<Vec<_>>()),
    };

    HttpResponse::Ok().json(SensorDataResponse {
        readings,
        stats,
        total_count,
    })
}

async fn clear_sensor_data(data: web::Data<AppState>) -> impl Responder {
    match data.sensor_data.lock() {
        Ok(mut sensor_data) => {
            sensor_data.clear();
            info!("🗑️ Data cleared");
            HttpResponse::Ok().json(serde_json::json!({
                "status": "success",
                "message": "Data cleared"
            }))
        }
        Err(_) => {
            HttpResponse::InternalServerError().json(serde_json::json!({"error": "Mutex poisoned"}))
        }
    }
}

async fn get_motor_status(data: web::Data<AppState>) -> impl Responder {
    let status = match data.motor_status.lock() {
        Ok(s) => s.clone(),
        Err(_) => "Unknown".to_string()
    };
    
    let last_update = match data.last_update.lock() {
        Ok(l) => *l,
        Err(_) => 0
    };
    
    HttpResponse::Ok().json(serde_json::json!({
        "motor_status": status,
        "last_update_ms": last_update
    }))
}

// ===== MAIN =====
#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::Builder::from_default_env()
        .filter_level(log::LevelFilter::Info)
        .init();

    println!("\n╔════════════════════════════════════════════════════════════╗");
    println!("║ 🚀 ELECTRONIC NOSE BACKEND v3.1 (FIXED)                  ║");
    println!("║    WiFi Arduino + Serial Relay + GUI + InfluxDB           ║");
    println!("╠════════════════════════════════════════════════════════════╣");
    println!("║ 📡 Arduino WiFi Input:   {}                ║", ARDUINO_WIFI_ADDR);
    println!("║ 📤 GUI Data Output:      {}                ║", GUI_DATA_ADDR);
    println!("║ 🎛️  GUI Commands:        {}                ║", GUI_CMD_ADDR);
    println!("║ 🌐 HTTP API:            {}                 ║", HTTP_ADDR);
    println!("║ 🔌 Serial Relay:        {} @ {}baud       ║", SERIAL_PORT, BAUD_RATE);
    println!("║ 📊 InfluxDB:            {}", INFLUXDB_URL);
    println!("║    Organization: {}", INFLUXDB_ORG);
    println!("║    Bucket: {}", INFLUXDB_BUCKET);
    println!("╚════════════════════════════════════════════════════════════╝\n");

    // Initialize InfluxDB client
    println!("🔌 Initializing InfluxDB client...");
    let influxdb_client = Client::new(INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_TOKEN);
    
    // TEST InfluxDB CONNECTION - THIS IS THE FIX!
    println!("🧪 Testing InfluxDB connection...");
    let mut influxdb_ready = false;
    match influxdb_client.ready().await {
        Ok(_) => {
            println!("✅ InfluxDB is REACHABLE and READY!");
            println!("   URL: {}", INFLUXDB_URL);
            println!("   Org: {}", INFLUXDB_ORG);
            println!("   Bucket: {}", INFLUXDB_BUCKET);
            influxdb_ready = true;
        }
        Err(e) => {
            eprintln!("\n❌ InfluxDB connection FAILED!");
            eprintln!("   Error: {}\n", e);
            eprintln!("   Please verify:");
            eprintln!("   1. InfluxDB is running:");
            eprintln!("      docker ps | grep influxdb");
            eprintln!("   2. InfluxDB URL is correct:");
            eprintln!("      {}", INFLUXDB_URL);
            eprintln!("   3. Organization name is correct:");
            eprintln!("      Current: {}", INFLUXDB_ORG);
            eprintln!("      Check in InfluxDB UI → Settings → Organizations");
            eprintln!("   4. Bucket name is correct:");
            eprintln!("      Current: {}", INFLUXDB_BUCKET);
            eprintln!("      Check in InfluxDB UI → Data → Buckets");
            eprintln!("   5. Token is valid (not expired):");
            eprintln!("      Current: {}...", &INFLUXDB_TOKEN[..20]);
            eprintln!("      Check in InfluxDB UI → Data → Tokens");
            eprintln!("\n⚠️  Continuing WITHOUT InfluxDB write functionality...\n");
        }
    }

    // Try to open serial connection
    let serial_port = match open_serial_connection() {
        Ok(port) => {
            println!("✅ Serial connection established!");
            Some(port)
        }
        Err(e) => {
            println!("⚠️  Serial connection failed: {}", e);
            println!("   Continuing without serial - commands won't relay to Arduino");
            None
        }
    };

    let app_state = web::Data::new(AppState {
        sensor_data: Arc::new(Mutex::new(Vec::new())),
        is_sampling: Arc::new(Mutex::new(false)),
        motor_status: Arc::new(Mutex::new(String::from("Idle"))),
        last_update: Arc::new(Mutex::new(0)),
        gui_broadcast: Arc::new(Mutex::new(Vec::new())),
        serial_port: Arc::new(Mutex::new(serial_port)),
        influxdb_client: Arc::new(influxdb_client),
        influxdb_ready: Arc::new(Mutex::new(influxdb_ready)),
    });

    // Start all TCP receivers and broadcasters
    start_tcp_arduino_receiver(app_state.clone());
    start_tcp_gui_command_receiver(app_state.clone());
    start_tcp_gui_data_broadcaster(app_state.clone());
    thread::sleep(Duration::from_millis(500));

    println!("📍 HTTP Endpoints:");
    println!("   GET  /              - Health check (shows InfluxDB status)");
    println!("   GET  /sensor_data   - Get sensor readings");
    println!("   GET  /motor_status  - Get motor state");
    println!("   POST /clear_data    - Clear all data\n");

    println!("🔄 Data Flow:");
    println!("   Arduino (WiFi:8081) → Rust → GUI (8083) & Serial relay");
    println!("   GUI (cmd:8082) → Rust → Arduino (Serial COM8)");
    if influxdb_ready {
        println!("   Rust → InfluxDB ({}) for storage ✅\n", INFLUXDB_BUCKET);
    } else {
        println!("   Rust → InfluxDB ({}) for storage ❌ (NOT CONNECTED)\n", INFLUXDB_BUCKET);
    }

    HttpServer::new(move || {
        let cors = Cors::permissive();

        App::new()
            .wrap(middleware::Logger::default())
            .wrap(cors)
            .app_data(app_state.clone())
            .route("/", web::get().to(health_check))
            .route("/sensor_data", web::get().to(get_sensor_data))
            .route("/clear_data", web::post().to(clear_sensor_data))
            .route("/motor_status", web::get().to(get_motor_status))
    })
    .bind(("0.0.0.0", HTTP_PORT))?
    .run()
    .await
}