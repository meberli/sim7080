"""This module listens for new entries in a redis queue
and sends them to a mqtt broker using sim7080 integrated mqtt client."""

import time
import logging
import argparse
import os
from logging.config import fileConfig
from getmac import get_mac_address
import redis
from sim7080 import Sim7080
from config import Config


CONFIG_BASE_PATH = 'conf/'
APP_CONFIG_FILE = 'settings.json'
LOGGING_CONFIG_FILE = 'logging.conf'
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





if __name__ == '__main__':
    #parse arguments
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='commands', dest='command')
    parser_test= subparsers.add_parser('write_file', help="write file(s) to sim7080 module")
    parser_test.add_argument("filenames", nargs='*', help="name of the file(s) to send to sim7080", type=str)
    parser_test= subparsers.add_parser('delete_file', help="delete file(s) from sim7080 module")
    parser_test.add_argument("filenames", nargs='*', help="name of the file(s) to delete from sim7080", type=str)
    parser_test= subparsers.add_parser('download_file', help="download file using http from specified url")
    parser_test.add_argument("urls", nargs='*', help="url's to download", type=str)
    parser_test= subparsers.add_parser('send_msg', help="send message to mqtt")
    parser_test.add_argument("--message", help="message to send", type=str)
    parser_test= subparsers.add_parser('send_status', help="send status message to mqtt")
    parser_test.add_argument("--message", help="optional message to sent with status message", type=str)
    parser_test= subparsers.add_parser('sync_time', help="sync local time with ntp")
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-t", "--test", help="don't send anything to mqtt", action="store_true")
    parser.add_argument("-o", "--keep_on", help="don't shut down modem after execution", action="store_true")

    args = parser.parse_args()

    path_log_config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), CONFIG_BASE_PATH, LOGGING_CONFIG_FILE)
    print('log config file: ', path_log_config_file)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)
        logger.info("verbosity turned on")
    else:
        fileConfig(path_log_config_file)
        logger = logging.getLogger(__name__)
        logger.info("using logging conf from {}".format(path_log_config_file))

    # load settings
    path_app_config = os.path.join(os.path.dirname(os.path.realpath(__file__)), CONFIG_BASE_PATH, APP_CONFIG_FILE)
    _config = Config().load_config(path_app_config)

    # initialize
    if args.test:
            logger.info("Test mode - not sending anything to gdc...")

    r = redis.StrictRedis('localhost', 6379, charset="utf-8", decode_responses=True)
    modem =  Sim7080(
        _config['serial_port'], _config['serial_baud'], default_timeout=_config['serial_default_timeout'])

    try:
        if args.command == 'write_file':
            logger.info('write_file')
            for filename in args.filenames:
                modem.write_file(filename)

        elif args.command == 'delete_file':
            logger.info('delete_file')
            for filename in args.filenames:
                modem.delete_file(filename)

        elif args.command == 'download_file':
            for file_url in args.urls:
                modem.download_file(file_url)

        elif args.command == 'sync_time':
            logger.info('sync_time')
            curr_time = modem.get_ntp_time(_config['ntp_server_host'])
            if curr_time:
                set_time(curr_time)
                logger.info('sync_time succeeded.')
            else:
                logger.info('sync_time failed')

        elif args.command == 'send_status':
            logger.info('send_status')
            if modem.modem_status < MODEM_STATUS.NETWORK_CONNECTED:
                modem.connect_network(apn_name=_config['mobile_apn'])
            while modem.modem_status !=  MODEM_STATUS.MQTT_CONNECTED:
                modem.connect_mqtt(
                    _config['mqtt_host'],
                    _config['mqtt_port'],
                    _config['mqtt_clientid'],
                    _config['mqtt_ca_crt_filename'],
                    _config['mqtt_client_cert_filename'],
                    _config['mqtt_client_key_filename'],
                    _config['mqtt_qos']
                )
            if not args.test:
                msg = prepare_status_msg()
                if args.message:
                    msg['fields']['message'] = args.message
                modem.mqtt_publish(_config['mqtt_publish_topic'], json.dumps([msg]))

        elif args.command == 'send_data':
            logger.info('send_data')
            # get data from sqlite
            new_timestamp_entries = load_data_from_sqlite()
            logger.info(f'found {len(new_timestamp_entries)} new entries...')
            if new_timestamp_entries:
                if modem.modem_status < MODEM_STATUS.NETWORK_CONNECTED:
                    modem.connect_network(apn_name=NETWORK_APN)
                if modem.modem_status !=  MODEM_STATUS.MQTT_CONNECTED:
                    while modem.modem_status !=  MODEM_STATUS.MQTT_CONNECTED:
                        modem.connect_mqtt(
                            MQTT_HOST,
                            MQTT_PORT,
                            device_name,
                            CA_CRT_FILENAME,
                            CLIENT_CRT_FILENAME,
                            CLIENT_KEY_FILENAME,
                            MQTT_QOS
                        )
                while new_timestamp_entries:
                    ids = []
                    msg = []
                    for entry in new_timestamp_entries:
                        ids.append(entry[0])
                        msg.append(prepare_timestamp_msg(entry[1], entry[2], entry[3]))
                    if not args.test:
                        logger.info(f'start publishing {len(msg)} new entries...')
                        if modem.mqtt_publish(MQTT_PUBLISH_TOPIC, json.dumps(msg)):
                            delete_data_from_sqlite(ids)
                    new_timestamp_entries = load_data_from_sqlite()
        if not args.keep_on:
            modem.power_down()
    except:
        logger.exception('Exception occured:')
        if modem != None:
            modem.power_down()