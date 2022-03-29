#!/usr/bin/python

import serial
import time
import redis
import subprocess
import logging
import argparse
import os
from logging.config import fileConfig
from getmac import get_mac_address

CONFIG_BASE_PATH = 'conf/'
LOGGING_CONFIG = 'logging.conf'



powerKey = 4
rec_buff = ''
Message = 'gateway.uno'
 

def power_on():
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(powerKey, GPIO.OUT)
        time.sleep(0.1)
        GPIO.output(powerKey, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(powerKey, GPIO.LOW)
        time.sleep(5)
    finally:
        logger.error('GPIO not available')
        ser.flushInput()
        return


def power_down(powerKey):
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(powerKey, GPIO.OUT)
        GPIO.output(powerKey, GPIO.HIGH)
        time.sleep(2)
        GPIO.output(powerKey, GPIO.LOW)
        time.sleep(5)
    finally:
        logger.exception('GPIO not available')
        return

def is_running():
    # simcom module uart may be fool,so it is better to send much times when it starts.
    for seq in range(3):
        ser.write('AT\r\n'.encode())
        time.sleep(1)
        if ser.inWaiting():
            time.sleep(0.01)
            recBuff = ser.read(ser.inWaiting())
            # logger.debug(f'rec_buff: {recBuff.decode()}')
            if 'OK' in recBuff.decode():
                recBuff = ''
                return True
        
    return False

def send_at(command, back, timeout):
    rec_buff = ''
    ser.write((command+'\r\n').encode())
    time.sleep(timeout)
    if ser.inWaiting():
        time.sleep(0.1)
        rec_buff = ser.read(ser.inWaiting())
    if rec_buff != '':
        if back not in rec_buff.decode():
            logger.warning(f'command \'{command}\' failed: expected result is \'{back}\' but got \'{rec_buff.decode()}\'')
            return False
        else:
            logger.debug(f'command \'{command}\' succeeded. returned: \'{rec_buff.decode()}\'')
            return rec_buff.decode()
    else:
        logger.warning(f'command \'{command}\' failed: no response')
        return False

def connect_mqtt():
    logger.info('*'*8 +' connecting mqtt' + '*'*8)
    try:
        logger.info('mqtt conf')
        # send_at('AT+SMCONF=?', 'OK', 1) # get mqtt configuration
        send_at('AT+SMCONF="CLIENTID","user1"', 'OK', 1)
        send_at('AT+SMCONF="URL","mqtttest.gateway.uno",1884', 'OK', 1)
        # send_at('AT+SMCONF="URL","137.135.83.217",1883', 'OK', 1)
        send_at('AT+SMCONF="USERNAME","user1"', 'OK', 1)
        send_at('AT+SMCONF="PASSWORD","asdf"', 'OK', 1)
        send_at('AT+SMCONF="KEEPTIME",60', 'OK', 1)
        send_at('AT+SMCONF="CLEANSS",1', 'OK', 1)
        send_at('AT+SMCONF="QOS",1', 'OK', 1)
        # send_at('AT+SMCONF="TOPIC","waveshare_pub"', 'OK', 1)
        # send_at('AT+SMCONF="MESSAGE","SALI"', 'OK', 1)
        # send_at('AT+SMCONF="RETAIN",1', 'OK', 1)
        send_at('AT+SMCONN', 'OK', 5)
        while True:
            while r.llen('timetrack_events') > 0:
                logger.info(f'# of timetrack events: {r.llen("timetrack_events")}')
                elem = r.rpop('timetrack_events')
                logger.info(f'sending event: \'{elem}\'')
                send_at(f'AT+SMPUB=\"waveshare_sub\",{len(elem)},1,0', 'OK', 1)
                send_at(elem,'OK', 4)
            time.sleep(10)
        
    except:
        logger.exception('Exception while trying to connect')
        if ser != None:
            send_at('AT+SMDISC', 'OK', 1)
            send_at('AT+CNACT=0,0', 'OK', 1)
            ser.close()
        power_down(powerKey)


def write_file(filename):
    logger.info('*'*8 +' writing file' + '*'*8)
    logger.info(f'writing file {filename}')
    with open(filename) as f:
        content = f.read()
    logger.debug(f'file content: {content}')
    send_at('AT+CFSINIT', 'OK', 3)
    send_at(f'AT+CFSWFILE=?', 'OK', 3)
    send_at(f'AT+CFSWFILE=3,"{filename}",0,{len(content)},9999', 'OK', 3)
    send_at(content,'OK', 4)
    send_at('AT+CFSTERM', 'OK', 1)
    res= send_at(f'AT+CFSGFIS=3,"{filename}"', 'OK', 1)
    logger.info(f'file size is {res}')


def connect_network():
    logger.info('*'*8 +' connecting to network' + '*'*8)
    logger.info('Preferred Selection between CAT-M and NB-IoT')
    send_at('AT+CMNB=1', 'OK', 0.5)
    logger.info('PDP Configure')
    send_at('AT+CNCFG=0,1,\"iot.1nce.net\"', 'OK', 1)
    logger.info('Get Network APN in CAT-M or NB-IOT')
    send_at('AT+CGNAPN', 'OK', 1)
    logger.info('APP Network Active')
    send_at('AT+CNCFG?', 'OK', 1)
    send_at('AT+CNACT=0,1', 'OK', 1)
  
    
def is_network_connected():
    res_dict = {}
    command = "AT+CPSI"
    response_fields = ("System Mode,"
                       "Operation Mode,"
                       "MCC-MNC,"
                       "TAC,"
                       "SCellID,"
                       "PCellID,"
                       "Frequency Band,"
                       "earfcn,"
                       "dlbw,"
                       "ulbw,"
                       "RSRQ,"
                       "RSRP,"
                       "RSSI,"
                       "RSSNR")
    
    logger.info('*'*8 + ' network check' + '*'*8)
    logger.info('Inquiring UE system information')
    res = send_at(command + "?", 'OK', 1).splitlines()
    for line in res:
        if line.startswith(command[2:] + ': '):
            res_dict = dict(zip(response_fields.split(','), line.split(',')))
            logger.debug(f'res_dict: {res_dict}')

    res = send_at('AT+CNACT?', 'OK', 1).splitlines()
    for line in res:
        if line.startswith('+CNACT:'):
            ip = line[13:-1]
            if not ip.startswith("0.0.0.0"):
                res_dict['ip'] = ip
                return res_dict
    return False
        
    
def info():
    logger.info('*'*8 + ' info ' + '*'*8)
    # logger.info('Report mobile equipment error') # enable debug messages
    send_at('AT+CMEE=2', 'OK', 1)
    logger.info('Signal quality report')
    send_at('AT+CSQ', 'OK', 1)
    logger.info('Inquiring UE system information')
    send_at('AT+CPSI?', 'OK', 1)
    logger.info('Network Registration Status')
    send_at('AT+CGREG?', '+CGREG: 0,1', 0.5)
    logger.info('SIM Lock')
    send_at('AT+CSIMLOCK?', 'OK', 0.5)
    logger.info('Enter PIN')
    send_at('AT+CPIN?', 'OK', 0.5)
    
    send_at('AT+CNACT?', 'OK', 1)
    logger.info('Inquiring UE system information')
    send_at('AT+CPSI?', 'OK', 1)


if __name__ == '__main__':
    #parse arguments
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='commands', dest='command')
    
    # create the parser for the "write_file" command
    parser_test= subparsers.add_parser('write_file', help="write file to sim7080 module")
    parser_test.add_argument("filename", help="name of the file to send to sim7080", type=str)

    parser_test= subparsers.add_parser('connect', help="send downlink to device")
    
    parser.add_argument("--port", help="serial port for modem", type=str,required=True)
    parser.add_argument("--config_dir", default = CONFIG_BASE_PATH, help="relative path to configuration files.", type=str)
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")
    parser.add_argument("-t", "--test", help="don't send anything to mqtt",
                    action="store_true")    
      
    args = parser.parse_args()    
    path_log_config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), args.config_dir, LOGGING_CONFIG)

    print('log config file: ',path_log_config_file)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)
        logger.info("verbosity turned on")
    else:
        fileConfig(path_log_config_file)
        logger = logging.getLogger(__name__)
        logger.info("using logging conf from {}".format(path_log_config_file))
    if args.test:
            logger.info("Test mode - not sending anything...")
    
    # initialize redis
    r = redis.StrictRedis('localhost', 6379, charset="utf-8", decode_responses=True)
    
    # initialize serial
    ser = serial.Serial(args.port, 9600)
    ser.flushInput()

    # initialize gpio
    try :
        import RPi.GPIO as GPIO
    except:     
        logger.warning('Unable to import Rpi.GPIO')
    
    mac_addr = get_mac_address()
    logger.info(f'mac addr is :\'{mac_addr}\'')

    if is_running():
        logger.info('sim7080 is running..')
    else:
        logger.info('sim7080 is powered off. power on..')
        power_on()
    
    ip = is_network_connected()
    if ip:
        logger.info(f'already connected to network. ip is {ip}')
    else:
        connect_network()

    if args.command == 'write_file':
        write_file(args.filename)

    elif args.command == 'connect':
        logger.info('Starting mqtt client')
        connect_mqtt() 
        
        
        
