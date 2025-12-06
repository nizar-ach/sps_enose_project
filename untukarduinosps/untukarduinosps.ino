// ARDUINO E-NOSE — FINAL + KIRIM currentLevel (UNO R4 WiFi)
// Library: "Multichannel Gas Sensor" by Seeed Studio

#include <WiFiS3.h>
#include <Wire.h>
#include "Multichannel_Gas_GMXXX.h"

// ==================== WIFI ====================
const char* ssid = "Redmi Note 12 Pro";
const char* pass = "galendio";
const char* RUST_IP = "10.43.4.238";   // GANTI DENGAN IP PC KAMU!
const int   RUST_PORT = 8081;
WiFiClient client;

// ==================== SENSOR ====================
GAS_GMXXX<TwoWire> gas;
#define MICS_PIN A1
float R0_mics = 100000.0;

// ==================== MOTOR PINS ====================
const int PWM_A  = 10,  DIR_A1 = 12,  DIR_A2 = 13;
const int PWM_B  = 11,  DIR_B1 = 8,  DIR_B2 = 9;

// ==================== FSM ====================
enum State { IDLE, PRE_COND, RAMP_UP, HOLD, PURGE, RECOVERY, DONE };
State currentState = IDLE;
unsigned long stateTime = 0;
int currentLevel = 0;  // 0 sampai 4
const int speeds[5] = {51, 102, 153, 204, 255};
bool samplingActive = false;

// ==================== TIMING (ms) ====================
const unsigned long T_PRECOND  = 10000;
const unsigned long T_RAMP     = 2000;
const unsigned long T_HOLD     = 120000;
const unsigned long T_PURGE    = 240000;
const unsigned long T_RECOVERY = 10000;
unsigned long lastSend = 0;

// ==================== MOTOR ====================
void motorA(int speed, bool reverse = false) {
  digitalWrite(DIR_A1, reverse ? LOW : HIGH);
  digitalWrite(DIR_A2, reverse ? HIGH : LOW);
  analogWrite(PWM_A, speed);
}
void motorB(int speed, bool reverse = false) {
  digitalWrite(DIR_B1, reverse ? LOW : HIGH);
  digitalWrite(DIR_B2, reverse ? HIGH : LOW);
  analogWrite(PWM_B, speed);
}
void stopMotors() { analogWrite(PWM_A, 0); analogWrite(PWM_B, 0); }
void rampTo(int target) {
  static int cur = 0;
  if (cur < target) cur += 10;
  else if (cur > target) cur = target;
  motorA(cur);
}

// ==================== SETUP ====================
void setup() {
  Serial.begin(9600);
  pinMode(DIR_A1, OUTPUT); pinMode(DIR_A2, OUTPUT); pinMode(PWM_A, OUTPUT);
  pinMode(DIR_B1, OUTPUT); pinMode(DIR_B2, OUTPUT); pinMode(PWM_B, OUTPUT);
  stopMotors();

  Wire.begin();
  gas.begin(Wire, 0x08);

  while (WiFi.begin(ssid, pass) != WL_CONNECTED) { Serial.print("."); delay(500); }
  Serial.println("\nWiFi Connected! IP: " + WiFi.localIP().toString());
  Serial.println("E-NOSE READY – Tunggu START_SAMPLING");
}

// ==================== LOOP ====================
void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n'); cmd.trim();
    if (cmd == "START_SAMPLING") startSampling();
    else if (cmd == "STOP_SAMPLING") stopSampling();
  }

  if (millis() - lastSend >= 250) { lastSend = millis(); sendSensorData(); }
  if (samplingActive) runFSM();
}

// ==================== FSM ====================
void startSampling() { if (!samplingActive) { samplingActive = true; currentLevel = 0; changeState(PRE_COND); } }
void stopSampling() { samplingActive = false; changeState(IDLE); stopMotors(); }

void changeState(State s) {
  currentState = s; stateTime = millis();
  String n[] = {"IDLE","PRE-COND","RAMP_UP","HOLD","PURGE","RECOVERY","DONE"};
  Serial.println("FSM → " + n[s] + " | Level " + String(currentLevel+1));
}

void runFSM() {
  unsigned long e = millis() - stateTime;
  switch (currentState) {
    case PRE_COND:  motorA(100); motorB(0); if (e >= T_PRECOND) changeState(RAMP_UP); break;
    case RAMP_UP:   rampTo(speeds[currentLevel]); if (e >= T_RAMP) changeState(HOLD); break;
    case HOLD:      motorA(speeds[currentLevel]); motorB(0); if (e >= T_HOLD) changeState(PURGE); break;
    case PURGE:     motorA(255, true); motorB(255); if (e >= T_PURGE) changeState(RECOVERY); break;
    case RECOVERY:  stopMotors();
      if (e >= T_RECOVERY) {
        currentLevel++;
        if (currentLevel >= 5) { changeState(DONE); samplingActive = false; Serial.println("5 LEVEL SELESAI!"); }
        else changeState(RAMP_UP);
      }
      break;
    case IDLE: case DONE: stopMotors(); break;
  }
}

// ==================== KIRIM DATA (TAMBAHAN currentLevel!) ====================
void sendSensorData() {
  uint32_t rno2 = gas.measure_NO2();
  uint32_t reth = gas.measure_C2H5OH();
  uint32_t rvoc = gas.measure_VOC();
  uint32_t rco  = gas.measure_CO();

  float no2 = (rno2 < 30000) ? rno2/1000.0 : -1.0;
  float eth = (reth < 30000) ? reth/1000.0 : -1.0;
  float voc = (rvoc < 30000) ? rvoc/1000.0 : -1.0;
  float co  = (rco  < 30000) ? rco /1000.0 : -1.0;

  float raw = analogRead(MICS_PIN) * (5.0/1023.0);
  float Rs = (raw > 0.1) ? 820.0*(5.0-raw)/raw : 100000;
  float ratio = Rs / R0_mics;
  float co_mics  = pow(10.0, (log10(ratio)-0.35)/-0.85);
  float eth_mics = pow(10.0, (log10(ratio)-0.15)/-0.65);
  float voc_mics = pow(10.0, (log10(ratio)+0.10)/-0.75);

  String data = "SENSOR:";
  data += String(no2,3) + "," + String(eth,3) + "," + String(voc,3) + "," + String(co,3) + ",";
  data += String(co_mics,3) + "," + String(eth_mics,3) + "," + String(voc_mics,3) + ",";
  data += String(currentState) + "," + String(currentLevel);  // <--- INI YANG BARU!

  if (client.connect(RUST_IP, RUST_PORT)) {
    client.print(data + "\n");
    client.stop();
  }
}