"""This module listens for new entries in a redis queue
and sends them to a mqtt broker using sim7080 integrated mqtt client."""

import time
import logging
import argparse
import os
from logging.config import fileConfig
from getmac import get_mac_address
import redis
import serial
from config import Config

CONFIG_BASE_PATH = 'conf/'
LOGGING_CONFIG = 'logging.conf'
POWER_PIN = 4

def power_on():
    """Powers on the SIM7080 module."""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(POWER_PIN, GPIO.OUT)
        time.sleep(0.1)
        GPIO.output(POWER_PIN, GPIO.HIGH)
        time.sleep(1)
        GPIO.output(POWER_PIN, GPIO.LOW)
        time.sleep(5)
    except NameError:
        logger.error('GPIO not available')
        ser.flushInput()

def power_down():
    """Powers down the SIM7080 module."""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(POWER_PIN, GPIO.OUT)
        GPIO.output(POWER_PIN, GPIO.HIGH)
        time.sleep(2)
        GPIO.output(POWER_PIN, GPIO.LOW)
        time.sleep(5)
    except NameError:
        logger.exception('GPIO not available')

def is_running():
    """Check if SIM7080 module is running."""
    # simcom module uart may be fool,so it is better to send much times when it starts.
    for _ in range(3):
        ser.write('AT\r\n'.encode())
        time.sleep(1)
        if ser.inWaiting():
            time.sleep(0.01)
            rec_buff = ser.read(ser.inWaiting())
            # logger.debug(f'rec_buff: {rec_buff.decode()}')
            if 'OK' in rec_buff.decode():
                rec_buff = ''
                return True

    return False

def send_at(command, back, timeout):
    """Sends AT Command to SIM7080 module."""
    rec_buff = ''
    ser.write((command+'\r\n').encode())
    time.sleep(timeout)
    if ser.inWaiting():
        time.sleep(0.1)
        rec_buff = ser.read(ser.inWaiting())
    if rec_buff != '':
        if back not in rec_buff.decode():
            logger.warning(
                f'command \'{command}\' failed.' +
                f'expected result is \'{back}\' but got \'{rec_buff.decode()}\'')
            return False
        else:
            logger.debug(f'command \'{command}\' succeeded. returned: \'{rec_buff.decode()}\'')
            return rec_buff.decode()
    else:
        logger.warning(f'command \'{command}\' failed: no response')
        return False

def connect_mqtt():
    """Connects to MQTT Server with the SIM7080 module."""

    logger.info('*'*8 +' connecting mqtt' + '*'*8)
    try:
        logger.info('mqtt conf')
        # send_at('AT+SMCONF=?', 'OK', 1) # get mqtt configuration
        send_at(f'AT+SMCONF="CLIENTID","{_config["mqtt_clientid"]}"', 'OK', 1)
        send_at(f'AT+SMCONF="URL","{_config["mqtt_server_host"]}",{_config["mqtt_server_port"]}', 'OK', 1)
        # send_at('AT+SMCONF="URL","137.135.83.217",1883', 'OK', 1)
        send_at(f'AT+SMCONF="USERNAME","{_config["mqtt_user"]}"', 'OK', 1)
        send_at(f'AT+SMCONF="PASSWORD","{_config["mqtt_password"]}"', 'OK', 1)
        send_at(f'AT+SMCONF="KEEPTIME",{_config["mqtt_keeptime"]}', 'OK', 1)
        send_at(f'AT+SMCONF="CLEANSS",{_config["mqtt_cleanss"]}', 'OK', 1)
        send_at(f'AT+SMCONF="QOS",{_config["mqtt_qos"]}', 'OK', 1)
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
        power_down()


def ping(hostname):
    """Pings the host with the SIM7080 module."""

    logger.info(f'{"*"*8} ping {hostname} {"*"*8}')
    try:
        send_at(f'AT+CNACT=0,1', 'OK', 1)
        send_at(f'AT+SNPDPID=0', 'OK', 1)
        send_at(f'AT+SNPING4="{hostname}",3,16,1000', 'OK', 1)
        
    except:
        logger.exception('Exception while trying ping host')

def write_file(filename):
    """Writes a file to SIM7080 module."""
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
    global _config
    """Connects SIM7080 module to Network."""
    logger.info('*'*8 +' connecting to network' + '*'*8)
    logger.info('Preferred Selection between CAT-M and NB-IoT')
    send_at(f'AT+CMNB={_config["mobile_catm_nbiot"]}', 'OK', 0.5)
    logger.info('PDP Configure')
    send_at(f'AT+CNCFG=0,1,"{_config["mobile_apn"]}"', 'OK', 1)
    logger.info('Get Network APN in CAT-M or NB-IOT')
    send_at('AT+CGNAPN', 'OK', 1)
    logger.info('APP Network Active')
    send_at('AT+CNCFG?', 'OK', 1)
    send_at('AT+CNACT=0,1', 'OK', 1)


def is_network_connected():
    """Check if SIM7080 module is connected to network."""
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
            ip_1 = line[13:-1]
            if not ip_1.startswith("0.0.0.0"):
                res_dict['ip'] = ip_1
                return res_dict
    return False


def info():
    """Prints info from SIM7080 module."""
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
    logger.info('PIN Status')
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
    parser.add_argument(
        "--config_dir",
        default = CONFIG_BASE_PATH,
        help="relative path to configuration files.",
        type=str
    )
    parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")
    parser.add_argument("-t", "--test", help="don't send anything to mqtt",
                    action="store_true")

    args = parser.parse_args()
    path_log_config_file = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        args.config_dir,
        LOGGING_CONFIG)

    print('log config file: ',path_log_config_file)

     # load the config
    filename = 'conf/settings.json'
    _config = Config(filename).load_config()
    print(_config['mqtt_server_host'])
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
        info()
        ping("www.google.com")

    if args.command == 'write_file':
        write_file(args.filename)

    elif args.command == 'connect':
        logger.info('Starting mqtt client')
        connect_mqtt()
