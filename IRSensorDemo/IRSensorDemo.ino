#include<Servo.h>
Servo mockActuator;
Servo servo2;
Servo servo3;


const int sensorPin = 2;     
const int servo1Pin = 3;
const int servo2Pin = 5;
const int servo3Pin = 6;
const int pulsesPerRev = 20;

volatile unsigned long lastMicros = 0;
volatile unsigned long pulseInterval = 0;
long lastRPM = 0;
int directionFlipFlop = -1;  //idk tbh

void pulseISR() {
  unsigned long now = micros();
  pulseInterval = now - lastMicros;
  lastMicros = now;
}

float getRPM() {
  if (pulseInterval == 0) return 0;

  float secPerPulse = pulseInterval / 1e6;
  float revPerSec = (1.0 / secPerPulse) / pulsesPerRev;
  return revPerSec * 60.0;
}

void updateServo(int currentRPM){
  if(currentRPM != lastRPM){
    lastRPM = currentRPM;
    if(directionFlipFlop == -1){
      mockActuator.write(135);
      servo2.write(135);
      servo3.write(135);
    } else {
      mockActuator.write(45);
      servo2.write(45);
      servo3.write(45);
    }
    directionFlipFlop *= -1;
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(sensorPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(sensorPin), pulseISR, RISING);
  mockActuator.attach(servo1Pin);
  servo2.attach(servo2Pin);
  servo3.attach(servo3Pin);
}

void loop() {
  float rpm = getRPM();
  Serial.println(rpm);
  updateServo(rpm);
  delay(100);
}
