#include <Servo.h>


const int loadPin = A1;        // Analog input for load detection
const int loadThreshold = 11.90;       // Load in volts -----MIGHT NEED TO CHANGE------
const int estopPin = 4;          // E-stop button (to GND)
const int encoderPin = 2;       // Encoder Pin for RPMs
const int actuatorPin = 5;      // Actuator PWM pin

int rpmEstopEna = 800;
int EPin = digitalRead(estopPin);
bool estopEngaged = false;

// --- Actuator setup ---
Servo actuator;
int actuatorPosition = 56;   // Initial actuator position
const int stepSize = 1;      // Step size per adjustment
const int actuatorMin = 47;
const int actuatorMax = 71;

// --- RPM Measurement variables ---
volatile unsigned long lastPulseTime = 0;
volatile unsigned long pulseInterval = 0;
volatile bool pulseReceived = false;
float rpm = 0.0;

// --- RPM Smoothing variables ---
const int numSamples = 10;
float rpmSamples[numSamples] = {0};
int sampleIndex = 0;

// --- Optimization variables ---
float lastRPM = 0.0;
unsigned long lastUpdateTime = 0;
const unsigned long updateInterval = 100; // ms between actuator moves
bool movingUp = true; // Start direction

// --- RPM Limits ---
const float maxShaftRPM = 1750.0; // Max safe shaft RPM
const float minValidRPM = 0.0;   // Reject too small RPMs
const float maxValidRPM = 5000.0; // Reject too large RPMs

// --- Braking control ---
bool braking = false;
const float minSafeRPM = 5.0;  // Stop adjusting once below this


void pulseISR();

void setup() {
  braking = false;
  estopEngaged = false;
  pinMode(estopPin, INPUT_PULLUP); 
  pinMode(encoderPin, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(encoderPin), pulseISR, RISING);


  actuator.attach(actuatorPin);
  actuator.write(actuatorPosition); // Set initial position



  Serial.begin(9600);
}

void handleRPMUpdates(){
  if (pulseReceived) {
    noInterrupts();
    unsigned long interval = pulseInterval;
    pulseReceived = false;
    interrupts();

    if (interval > 0) {
      float newRPM = 60000000.0 / interval;

      // Sanity check on RPM
      if (newRPM > minValidRPM && newRPM < maxValidRPM) {
        rpmSamples[sampleIndex] = newRPM;
        sampleIndex = (sampleIndex + 1) % numSamples;

        // Calculate moving average
        float sum = 0;
        for (int i = 0; i < numSamples; i++) {
          sum += rpmSamples[i];
        }
        rpm = sum / numSamples;

        Serial.print("Smoothed Shaft RPM: ");
        Serial.println(rpm);
      } else {
        Serial.println("Ignored bad RPM reading");
      }
    }
  }
}

void loop() 
{

 unsigned long currentTime = millis();
 //Serial.println(currentTime);
 int EPin = digitalRead(estopPin);
 Serial.println(EPin);



  float reading = analogRead(loadPin);
  Serial.println(reading);
  float Vmeasured = reading / 1024.0 * 5;  // voltage at analog pin
  float Vload = Vmeasured / 0.3125; // Voltage divider: R1 = 22k, R2 = 10k => Vin = Vmeasured * R2/(R1+R2) = 10k / 32k

  bool loadConnected = Vload < loadThreshold;
    Serial.println(Vload);
    Serial.print("Input Voltage: ");
    Serial.println(Vmeasured);


// && (rpm > rpmEstopEna)
/*
if ((!loadConnected || digitalRead(estopPin) == HIGH)) { //PUT ON HIGH
  if (!estopEngaged) {
    estopEngaged = true;
    braking = true;
    Serial.println("Emergency Stop OR Load Disconnect Triggered");
  }
} else {
  if (!estopEngaged) {
    Serial.println("Load Connected");
  }
}
*/

  
  // --- Handle RPM updates ---
  

   // --- Braking State (active deceleration) ---
  if (braking) {
    Serial.println("Braking");
    actuatorPosition = 70;
   actuator.write(actuatorPosition);
   Serial.println(actuatorPosition);
   braking = false;
   estopEngaged = false;

  }


  // --- Actuator Optimization ---
  if (!braking && !estopEngaged && (currentTime - lastUpdateTime > updateInterval)) {
    lastUpdateTime = currentTime;

    if (rpm > maxShaftRPM) {
      // RPM too high — feather blades more to slow down
      
      actuatorPosition +=stepSize ;
      Serial.println("RPM too high, feathering blades.");
    }
    else if (rpm > lastRPM) {
      // RPM improved, continue moving same direction
      Serial.println("RPM GREATER THAN LAST RPM");
      if (movingUp){
        actuatorPosition += stepSize;
        Serial.println("ACTUATOR Up");
        }
        else  {
        actuatorPosition -= stepSize;
        Serial.println("RPM improving, continuing same direction.");
        Serial.println("ACTUATOR DOWN");
        }
      }
    
    else {
      // RPM got worse, reverse direction
      Serial.println("RPM GOT WORSE");
      movingUp = !movingUp;
      if (movingUp) {
      actuatorPosition += stepSize;
      Serial.println("actuator UP");
      }
      else {
      actuatorPosition -= stepSize;
      Serial.println("RPM dropped, reversing direction.");
      Serial.println("actuator DOWN");
      }
    }

    // Bound actuator position
    if (actuatorPosition > actuatorMax) actuatorPosition = actuatorMax;
    if (actuatorPosition < actuatorMin) actuatorPosition = actuatorMin;

    actuator.write(actuatorPosition);

    Serial.println("New Actuator Position: ");
    Serial.println(actuatorPosition);

    lastRPM = rpm; // Save current RPM for next decision
  }




  delay(500);
}




void pulseISR() {
  unsigned long currentTime = micros();
  pulseInterval = currentTime - lastPulseTime;
  lastPulseTime = currentTime;
  pulseReceived = true;
}


