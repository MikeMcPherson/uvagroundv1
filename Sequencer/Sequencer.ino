/*
  Copyright Mike McPherson, 2019.
  Sequencer for UVa Libertas ground station.

  REST functions:
  
  powerOn?param=TXAMP|VLNA|ULNA|ROT2PROG|UPOL|ALL
  powerOff?param=TXAMP|VLNA|ULNA|ROT2PROG|UPOL|ALL
  txPortSelect?param=portNumber
  txPortSense?param=unused
  uhfTxModeEnable?param=unused
  uhfTxModeDisable?param=unused
  ulnaEnable?param=0|1
  txampEnable?param=0|1
  txDelaySet?param=txDelay
  readDcPower?param=unused
  txWait?param=txTimeout
  readRfPower?param=unused
  
*/

#define AREST_NUMBER_VARIABLES 30
#define AREST_NUMBER_FUNCTIONS 30

#define TRUE 1   // Built-in is "true"
#define FALSE 0  // Built-in is "false"

#include <SPI.h>
#include <Ethernet.h>
#include <PubSubClient.h>
#include <aREST.h>
#include <avr/wdt.h>
#include <Adafruit_INA260.h>
#include <Adafruit_INA219.h>

#define antSelectPin1 22
#define antSelectPin2 23
#define antSelectPin3 24
#define radioSelectPin1 25
#define radioSelectPin2 26
#define radioSelectPin3 27
#define portSelectDelay 100
#define portSenseDelay 30

#define vlnaTxPin 28
#define ulnaTxPin 29
#define vhfTxampTxPin 30
#define uhfTxampTxPin 31

#define txAmpPowerPin 32
#define vlnaPowerPin 33
#define ulnaPowerPin 34
#define rot2progPowerPin 35
#define unusedRelayPin5 36
#define upolPowerPin 37
#define unusedRelayPin7 38
#define unusedRelayPin8 39

#define txAmpPowerI2cAddress 0x40
#define rot2progPowerI2cAddress 0x41
#define ulnaPowerI2cAddress 0x44
#define upolPowerI2cAddress 0x45

#define antSensePin1 40
#define antSensePin2 41
#define antSensePin3 42
#define radioSensePin1 43
#define radioSensePin2 44
#define radioSensePin3 45

#define txampRfPowerMonitorPin 0

char IdString[] = "seq020";
char NameString[] = "Sequencer";
char powerOnString[] = "powerOn";
char powerOffString[] = "powerOff";
char txPortSelectString[] = "txPortSelect";
char txPortSenseString[] = "txPortSense";
char uhfTxModeEnableString[] = "uhfTxModeEnable";
char uhfTxModeDisableString[] = "uhfTxModeDisable";
char readDcPowerString[] = "readDcPower";
char ulnaEnableString[] = "ulnaEnable";
char txampEnableString[] = "txampEnable";
char txWaitString[] = "txWait";
char txDelaySetString[] = "txDelaySet";
char readRfPowerString[] = "readRfPower";

byte mac[] = { 0x2C, 0xF7, 0xF1, 0x08, 0x04, 0x02 };
IPAddress ip(192,168,10,80);
EthernetServer server(80);
unsigned long int txStartTime = 0;
bool txMode = false;

Adafruit_INA260 txAmpPowerMonitor = Adafruit_INA260();
Adafruit_INA260 rot2progPowerMonitor = Adafruit_INA260();
Adafruit_INA219 ulnaPowerMonitor(ulnaPowerI2cAddress);
Adafruit_INA219 upolPowerMonitor(upolPowerI2cAddress);

aREST rest = aREST();

// Variables to be exposed
int seqError = 0;
int antSense1 = 0;
int antSense2 = 0;
int antSense3 = 0;
int antPortSensed = 0;
int radioSense1 = 0;
int radioSense2 = 0;
int radioSense3 = 0;
int radioPortSensed = 0;
int txDelay = 300;
float txAmpVoltage = 0;
float txAmpCurrent = 0;
float rot2progVoltage = 0;
float rot2progCurrent = 0;
float ulnaVoltage = 0;
float ulnaCurrent = 0;
float upolVoltage = 0;
float upolCurrent = 0;
unsigned long int timeStamp = 0;
int ulnaEnabled = FALSE;  // false = 0, true != 0; bool not supported by arest.io
int txampEnabled = FALSE;
int txTimeout = 1500;  // Timeout in milliseconds
int txampRfPower = 0;
int txampRfPowerMax = 0;

void setup(void)
{
  timeStamp = millis();
  Serial.begin(115200);

  // Init pins
  pinMode(antSelectPin1, OUTPUT);
  digitalWrite(antSelectPin1, LOW);
  pinMode(antSelectPin2, OUTPUT);
  digitalWrite(antSelectPin2, LOW);
  pinMode(antSelectPin3, OUTPUT);
  digitalWrite(antSelectPin3, LOW);
  pinMode(radioSelectPin1, OUTPUT);
  digitalWrite(radioSelectPin1, LOW);
  pinMode(radioSelectPin2, OUTPUT);
  digitalWrite(radioSelectPin2, LOW);
  pinMode(radioSelectPin3, OUTPUT);
  digitalWrite(radioSelectPin3, LOW);

  pinMode(antSensePin1,INPUT);
  pinMode(antSensePin2,INPUT);
  pinMode(antSensePin3,INPUT);
  pinMode(radioSensePin1,INPUT);
  pinMode(radioSensePin2,INPUT);
  pinMode(radioSensePin3,INPUT);
  txPortSelect("3");

  pinMode(vlnaTxPin, OUTPUT);
  digitalWrite(vlnaTxPin, LOW);
  pinMode(ulnaTxPin, OUTPUT);
  digitalWrite(ulnaTxPin, LOW);
  pinMode(vhfTxampTxPin, OUTPUT);
  digitalWrite(vhfTxampTxPin, LOW);
  pinMode(uhfTxampTxPin, OUTPUT);
  digitalWrite(uhfTxampTxPin, LOW);

  ulnaEnabled = FALSE;
  txampEnabled = FALSE;
  pinMode(txAmpPowerPin, OUTPUT);
  digitalWrite(txAmpPowerPin, HIGH);
  pinMode(vlnaPowerPin, OUTPUT);
  digitalWrite(vlnaPowerPin, HIGH);
  pinMode(ulnaPowerPin, OUTPUT);
  digitalWrite(ulnaPowerPin, HIGH);
  pinMode(rot2progPowerPin, OUTPUT);
  digitalWrite(rot2progPowerPin, LOW);
  pinMode(unusedRelayPin5, OUTPUT);
  digitalWrite(unusedRelayPin5, HIGH);
  pinMode(upolPowerPin, OUTPUT);
  digitalWrite(upolPowerPin, HIGH);
  pinMode(unusedRelayPin7, OUTPUT);
  digitalWrite(unusedRelayPin7, HIGH);
  pinMode(unusedRelayPin8, OUTPUT);
  digitalWrite(unusedRelayPin8, HIGH);

  txAmpPowerMonitor.begin(txAmpPowerI2cAddress);
  rot2progPowerMonitor.begin(rot2progPowerI2cAddress);
  ulnaPowerMonitor.begin();
  upolPowerMonitor.begin();
  
  // Init and expose variables and functions
  seqError = 0;
  rest.variable("seqError",&seqError);
  rest.variable("antSense1",&antSense1);
  rest.variable("antSense2",&antSense2);
  rest.variable("antSense3",&antSense3);
  rest.variable("radioSense1",&radioSense1);
  rest.variable("radioSense2",&radioSense2);
  rest.variable("radioSense3",&radioSense3);
  rest.variable("antPortSensed",&antPortSensed);
  rest.variable("radioPortSensed",&radioPortSensed);
  rest.variable("txDelay",&txDelay);
  rest.variable("txAmpVoltage",&txAmpVoltage);
  rest.variable("txAmpCurrent",&txAmpCurrent);
  rest.variable("rot2progVoltage",&rot2progVoltage);
  rest.variable("rot2progCurrent",&rot2progCurrent);
  rest.variable("ulnaVoltage",&ulnaVoltage);
  rest.variable("ulnaCurrent",&ulnaCurrent);
  rest.variable("upolVoltage",&upolVoltage);
  rest.variable("upolCurrent",&upolCurrent);
  rest.variable("timeStamp",&timeStamp);
  rest.variable("ulnaEnabled",&ulnaEnabled);
  rest.variable("txampEnabled",&txampEnabled);
  rest.variable("txTimeout",&txTimeout);
  rest.variable("txampRfPower",&txampRfPower);
  rest.variable("txampRfPowerMax",&txampRfPowerMax);

  rest.function(powerOnString,powerOn);
  rest.function(powerOffString,powerOff);
  rest.function(txPortSelectString,txPortSelect);
  rest.function(txPortSenseString,txPortSense);
  rest.function(uhfTxModeEnableString,uhfTxModeEnable);
  rest.function(uhfTxModeDisableString,uhfTxModeDisable);
  rest.function(readDcPowerString,readDcPower);
  rest.function(ulnaEnableString,ulnaEnable);
  rest.function(txampEnableString,txampEnable);
  rest.function(txWaitString,txWait);
  rest.function(txDelaySetString,txDelaySet);
  rest.function(readRfPowerString,readRfPower);

  // ***ID needs to be 6 characters***
  rest.set_id(IdString);
  rest.set_name(NameString);

  Ethernet.begin(mac, ip);
  server.begin();
  timeStamp = millis();
  Serial.print("Server ready at ");
  Serial.print(Ethernet.localIP());
  Serial.print(" ");
  Serial.println(timeStamp);

  // Start watchdog
//  wdt_enable(WDTO_4S);
}

void loop() {
  unsigned long int txCurrentTime;
  unsigned long int txElapsedTime;
  EthernetClient client = server.available();
  rest.handle(client);
  if (txMode) {
    txCurrentTime = millis();
    if (txCurrentTime >= txStartTime) {
      txElapsedTime = txCurrentTime - txStartTime;
    } else{
      txElapsedTime = (4294967295 - txStartTime) + txCurrentTime;
    }
    if (txElapsedTime >= txTimeout) {
      uhfTxModeDisable("");
      Serial.println("txTimeout expired, returning to RX mode");
    }
  }
//  wdt_reset();
}

void pinSet(int pinNumber, int state) {
  digitalWrite(pinNumber,state);
}

int powerOn(String command) {
  if (command.equalsIgnoreCase("TXAMP")) {
    pinSet(txAmpPowerPin,LOW);
    txampEnabled = TRUE;
  } else if(command.equalsIgnoreCase("VLNA")) {
    pinSet(vlnaPowerPin,LOW);
  } else if(command.equalsIgnoreCase("ULNA")) {
    pinSet(ulnaPowerPin,LOW);
    ulnaEnabled = TRUE;
  } else if(command.equalsIgnoreCase("ROT2PROG")) {
    pinSet(rot2progPowerPin,LOW);
  } else if(command.equalsIgnoreCase("UPOL")) {
    pinSet(upolPowerPin,LOW);
  } else if(command.equalsIgnoreCase("ALL")) {
    pinSet(txAmpPowerPin,LOW);
    txampEnabled = TRUE;
    pinSet(vlnaPowerPin,LOW);
    pinSet(ulnaPowerPin,LOW);
    ulnaEnabled = TRUE;
    pinSet(rot2progPowerPin,LOW);    
    pinSet(upolPowerPin,LOW);
  }
  seqError = 0;
  timeStamp = millis();
  Serial.print("powerOn ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int powerOff(String command) {
  if (command.equalsIgnoreCase("TXAMP")) {
    pinSet(txAmpPowerPin,HIGH);
    txampEnabled = FALSE;
  } else if(command.equalsIgnoreCase("VLNA")) {
    pinSet(vlnaPowerPin,HIGH);
  } else if(command.equalsIgnoreCase("ULNA")) {
    pinSet(ulnaPowerPin,HIGH);
    ulnaEnabled = FALSE;
  } else if(command.equalsIgnoreCase("ROT2PROG")) {
    pinSet(rot2progPowerPin,HIGH);
  } else if(command.equalsIgnoreCase("UPOL")) {
    pinSet(upolPowerPin,HIGH);
  } else if(command.equalsIgnoreCase("ALL")) {
    pinSet(txAmpPowerPin,HIGH);
    txampEnabled = FALSE;
    pinSet(vlnaPowerPin,HIGH);
    pinSet(ulnaPowerPin,HIGH);
    ulnaEnabled = FALSE;
    pinSet(rot2progPowerPin,HIGH);
    pinSet(upolPowerPin,HIGH);
  }
  seqError = 0;
  timeStamp = millis();
  Serial.print("powerOff ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int txPortSelect(String command) {
  int port = command.toInt();
  pinSet(antSelectPin1,LOW);
  pinSet(radioSelectPin1,LOW);
  pinSet(antSelectPin2,LOW);
  pinSet(radioSelectPin2,LOW);
  pinSet(antSelectPin3,LOW);
  pinSet(radioSelectPin3,LOW);
  switch (port) {
    case 1:
      pinSet(antSelectPin1,HIGH);
      pinSet(radioSelectPin1,HIGH);
      break;
    case 2:
      pinSet(antSelectPin2,HIGH);
      pinSet(radioSelectPin2,HIGH);
      break;
    case 3:
      pinSet(antSelectPin3,HIGH);
      pinSet(radioSelectPin3,HIGH);
      break;
  }
  delay(portSelectDelay);
  pinSet(antSelectPin1,LOW);
  pinSet(radioSelectPin1,LOW);
  pinSet(antSelectPin2,LOW);
  pinSet(radioSelectPin2,LOW);
  pinSet(antSelectPin3,LOW);
  pinSet(radioSelectPin3,LOW);

  delay(portSenseDelay);
  txPortSense(command);
  timeStamp = millis();
  Serial.print("txPortSelect ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int txPortSense(String command) {
  int port = command.toInt();
  antSense1 = digitalRead(antSensePin1);
  antSense2 = digitalRead(antSensePin2);
  antSense3 = digitalRead(antSensePin3);
  antPortSensed = (antSense1 * 1) + (antSense2 * 2) + (antSense3 * 3);
  radioSense1 = digitalRead(radioSensePin1);
  radioSense2 = digitalRead(radioSensePin2);
  radioSense3 = digitalRead(radioSensePin3);
  radioPortSensed = (radioSense1 * 1) + (radioSense2 * 2) + (radioSense3 * 3);
  if ((antPortSensed != port) or (radioPortSensed != port)) {
    seqError = -1;
  } else {
    seqError = 0;
  }
  timeStamp = millis();
  Serial.print("txPortSense ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int ulnaTxMode(String command) {
  pinSet(ulnaTxPin,HIGH);
  seqError = 0;
  timeStamp = millis();
  Serial.print("ulnaTxMode ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int ulnaRxMode(String command) {
  pinSet(ulnaTxPin,LOW);
  seqError = 0;
  timeStamp = millis();
  Serial.print("ulnaRxMode ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int ulnaEnable(String command) {
  ulnaEnabled = command.toInt();
  if(ulnaEnabled == TRUE) {
    pinSet(ulnaPowerPin, LOW);
  } else {
    pinSet(ulnaPowerPin, HIGH);
  }
  seqError = 0;
  timeStamp = millis();
  Serial.print("ulnaEnable ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int uhfTxampTx(String command) {
  pinSet(uhfTxampTxPin,HIGH);
  seqError = 0;
  timeStamp = millis();
  Serial.print("uhfTxampTx ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int uhfTxampRx(String command) {
  pinSet(uhfTxampTxPin,LOW);
  seqError = 0;
  timeStamp = millis();
  Serial.print("uhfTxampRx ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int txampEnable(String command) {
  txampEnabled = command.toInt();
  if(txampEnabled == TRUE) {
    pinSet(txAmpPowerPin, LOW);
  } else {
    pinSet(txAmpPowerPin, HIGH);
  }
  seqError = 0;
  timeStamp = millis();
  Serial.print("txampEnable ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int uhfTxModeEnable(String command) {
  ulnaTxMode("");
  txPortSelect("2");
  uhfTxampTx("");
  delay(txDelay);
  seqError = 0;
  timeStamp = millis();
  txStartTime = timeStamp;
  txMode = true;
  Serial.print("uhfTxModeEnable ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int uhfTxModeDisable(String command) {
  uhfTxampRx("");
  txPortSelect("1");
  ulnaRxMode("");
  seqError = 0;
  timeStamp = millis();
  txMode = false;
  Serial.print("uhfTxModeDisable ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int txDelaySet(String command) {
  int temp = command.toInt();
  if(temp >= 0) {
    txDelay = temp;
    seqError = 0;
  } else {
    seqError = -1;
  }
  timeStamp = millis();
  Serial.print("txDelaySet ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int readDcPower(String command) {
  txAmpVoltage = txAmpPowerMonitor.readBusVoltage()/1000.0;
  txAmpCurrent = txAmpPowerMonitor.readCurrent();
  rot2progVoltage = rot2progPowerMonitor.readBusVoltage()/1000.0;
  rot2progCurrent = rot2progPowerMonitor.readCurrent();
  ulnaVoltage = ulnaPowerMonitor.getBusVoltage_V();
  ulnaCurrent = ulnaPowerMonitor.getCurrent_mA();
  upolVoltage = upolPowerMonitor.getBusVoltage_V();
  upolCurrent = upolPowerMonitor.getCurrent_mA();
  seqError = 0;
  timeStamp = millis();
  Serial.print("readDcPower ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int txWait(String command) {
  txampRfPowerMax = analogRead(txampRfPowerMonitorPin);
  txampRfPower = txampRfPowerMax;
  seqError = 0;
  timeStamp = millis();
  Serial.print("txWait ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}

int readRfPower(String command) {
  txampRfPower = analogRead(txampRfPowerMonitorPin);
  txampRfPowerMax = txampRfPower;
  seqError = 0;
  timeStamp = millis();
  Serial.print("readRfPower ");
  Serial.print(command);
  Serial.print(" ");
  Serial.print(seqError);
  Serial.print(" ");
  Serial.println(timeStamp);
  return seqError;
}
