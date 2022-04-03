# sim7080
Python Redis -> MQTT example for SIM7080G Cat-M/NB-IoT module

## description
This script listens for new entries in a redis queue and sends them to a mqtt broker using sim7080 integrated mqtt client.

## preparation
1. install redis on your system:   
   ```
   sudo apt install redis
   ```

2. install virtualenv   
   ```
   python -m pip install virtualenv
   ```

3. clone this project to a new folder and change in this folder  
   ```
   git clone https://github.com/meberli/sim7080.git new_folder
   cd new_folder
   ```

4. create and activate virtualenv
   ```
   virtualenv venv
   source venv/bin/activate
   ```

5. install all requirements from requirements.txt
   ```
   python -m pip install -r requirements.txt
   ```
6. run redis2mqtt.py with modem connected
   ```
   python ./redis2mqtt.py --port /dev/ttyAMA0 
   ```

## usage

### upload certificate & key for mqtts
certificate and key needs to be uploaded to sim7080 in advance if you want to use mqtts
* 
*

## links
### manuals
https://www.simcom.com/product/SIM7080G.html


### hardware
* raspberry pi hat:    
   https://www.waveshare.com/wiki/SIM7080G_Cat-M/NB-IoT_HAT   
   https://www.waveshare.com/product/iot-communication/long-range-wireless/nb-iot-lora/sim7080g-cat-m-nb-iot-hat.htm
* m5stack universal:   
   https://www.brack.ch/m5stack-cat-m-nb-iot-modul-sim7080g-1277632

  https://www.brack.ch/m5stack-schnitstelle-atom-dtu-nb-iot-kit-globale-version-1248755
