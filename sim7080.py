#!/usr/bin/python

import serial
import time
import logging
from urllib.parse import urlparse
from datetime import datetime
from datetime import timedelta
from enum import Enum, IntEnum

POWER_KEY = 4
DEFAULT_TIMEOUT = 1


class MODEM_STATUS(IntEnum):
    PWR_OFF = 1
    PWR_ON = 2
    NETWORK_CONNECTED = 3
    MQTT_CONNECTED = 4


class Response():
    def __init__(self):
        self._message = []
        self._raw_message = []
        self._error_code = None

    def __str__(self):
        return (
            f'message: {str(self._message)} - '
            f'errorcode: {self._error_code}'
        )

    def is_error(self):
        return not self.is_success()

    def is_success(self):
        return True if self._error_code == 'OK' else False

    @property
    def error_code(self):
        return self._error_code

    @error_code.setter
    def error_code(self, value):
        self._error_code = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value


class Sim7080:

    modem_status = None

    def __init__(self, port, baud, default_timeout=DEFAULT_TIMEOUT):
        self.ser = serial.Serial(port, baud, timeout=default_timeout)
        self.ser.flushInput()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.modem_status = MODEM_STATUS.PWR_OFF
        r = self._send_execute_command('ATE0')
        if r.is_success():
            self._sync_modem_status()

    def is_powered_on(self):
        if self._send_execute_command('ATE0').is_success():
            return True
        else:
            return False

    def is_mqtt_connected(self):
        res = self._send_read_command('AT+SMSTATE')
        if not res.is_error() and (res.message[0] == '1'):
            return True
        else:
            return False

    def is_network_connected(self):
        res = self._send_read_command('AT+CNACT')
        if not res.is_error():
            ip = res.message[0].split(',')[2].strip('"')
            if (ip is not None and
                    ip != '0.0.0.0'):
                return True
        else:
            return False

    def _sync_modem_status(self):
        if self.is_powered_on():
            if self.is_network_connected():
                if self.is_mqtt_connected():
                    self.modem_status = MODEM_STATUS.MQTT_CONNECTED
                else:
                    self.modem_status = MODEM_STATUS.NETWORK_CONNECTED
            else:
                self.modem_status = MODEM_STATUS.PWR_ON
        else:
            self.modem_status = MODEM_STATUS.PWR_OFF

    def ensure_network(self):
        self._sync_modem_status()
        while 1:
            if self.modem_status >= MODEM_STATUS.NETWORK_CONNECTED:
                self.logger.info('sim7080 is connected to network.')
                return True
            else:
                self.logger.info('sim7080 has no network connection.')
                self.ensure_power()
                self.logger.info('try connect to network')
                self.connect_network()
                if self.modem_status >= MODEM_STATUS.NETWORK_CONNECTED:
                    self.logger.info('sim7080 is connected to network.')
                    return True
                else:
                    self.logger.info('trying again...')
                    time.sleep(10)
            

    def ensure_power(self):
        if self.modem_status is MODEM_STATUS.PWR_OFF:
            self.logger.info('sim7080 is powered off.')
            while self.modem_status is MODEM_STATUS.PWR_OFF:
                self.logger.info('try to power on..')
                self.power_on()
            self.logger.info('sim7080 is ready.')

    def get_location(self):
        #does not work... always errorcode 1
        cid = 0
        self.logger.info('*'*8 + ' get location' + '*'*8)
        self.ensure_network()
        self.logger.debug('Base station Location configure')
        self._send_write_command('AT+CLBSCFG', f'0,3')
        self.logger.debug('Base station Location')
        self._send_write_command('AT+CLBS', f'1,{cid}')
        resp = self._wait_for_message('', timeout=10)
        if resp.is_success() and resp.message[0].startswith('0,'):
            response_fields = [
                "Error Code",
                "Longitude",
                "Latitude",
                "Precision",
            ]
            pos_dict = dict(
                zip(
                    response_fields,
                    resp.message[0].split(',')
                )
            )
            self.logger.info(
                f"position: Longitude: {pos_dict.get('Longitude')}, "
                f"Latitude: {pos_dict.get('Latitude')}, "
                f"Precision: {pos_dict.get('Precision')}, "
            )
            return pos_dict
        else:
            self.logger.error(f'failed to sync time. error msg: {resp.message[0]}')
            return None
        
    def get_network_info(self):
        self.logger.info('*'*8 + ' get network info' + '*'*8)
        self.ensure_network()
        self.logger.debug('Inquiring UE system information')
        res = self._send_read_command('AT+CPSI')
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
        if res.is_error():
            return False
        res_dict = dict(
            zip(
                response_fields.split(','),
                res.message[0][7:].split(',')
            )
        )
        res = self._send_read_command('AT+CNACT')
        if not res.is_error():
            ip = res.message[0].split(',')[2]
            res_dict['ip'] = ip[1:-1]
            return res_dict
        return False

    def connect_network(self, apn_name=''):
        self.ensure_power()
        self.logger.info('*'*8 + ' connecting to network' + '*'*8)
        self.logger.debug('Preferred Selection between CAT-M and NB-IoT')
        self._send_write_command('AT+CMNB', '1')
        if apn_name == '':
            self.logger.debug('Get Network APN in CAT-M or NB-IOT')
            resp = self._send_execute_command('AT+CGNAPN')
            # expectet result: '1,"[APN_NAME]"
            if resp.is_success() and resp.message[0].startswith('1,'):
                apn_name = resp.message[0][2:].strip('"')
        self.logger.debug('PDP Configure')
        self._send_write_command('AT+CNCFG', f'0,1,"{apn_name}"')
        self.logger.debug('APP Network Active')
        self._send_write_command('AT+CNACT', '0,1')
        resp = self._wait_for_message('+APP PDP', timeout=10)
        if resp.is_success() and resp.message[0] == '0,ACTIVE':
            self.modem_status = MODEM_STATUS.NETWORK_CONNECTED
            self.logger.info(f'connection to network established.')
            return True
        else:
            self.logger.warn(f'connection to network failed.')
            return False

    def connect_mqtt(
        self,
        host,
        port,
        clientid,
        ca_crt_filename,
        client_crt_filename,
        client_key_filename,
        qos
    ):
        self.logger.info('*'*8 + ' connecting mqtt' + '*'*8)
        self.logger.info(f'host: {host}, port: {port}, client-id: {clientid}')
        self.ensure_network()
        if (self.is_mqtt_connected()):
            self.modem_status = MODEM_STATUS.MQTT_CONNECTED
            self.logger.info('already connected to mqtt. skipping connect..')
            return True
        self._send_write_command('AT+CMEE', '2')
        self._send_write_command('AT+SMCONF', f'"URL","{host}",{port}')
        self._send_write_command('AT+SMCONF', '"KEEPTIME",60')
        self._send_write_command('AT+SMCONF', '"CLEANSS",1')
        self._send_write_command('AT+SMCONF', f'"QOS",{qos}')
        self._send_write_command('AT+SMCONF', f'"CLIENTID","{clientid}"')
        resp = self._send_write_command(
            'AT+CSSLCFG', f'"convert",2,"{ca_crt_filename}"')
        if resp.is_error():
            self.write_file(ca_crt_filename)
            self._send_write_command(
                'AT+CSSLCFG', f'"convert",2,"{ca_crt_filename}"')
        resp = self._send_write_command(
            'AT+CSSLCFG',
            f'"convert",1,"{client_crt_filename}","{client_key_filename}"'
        )
        if resp.is_error():
            self.write_file(client_crt_filename)
            self.write_file(client_key_filename)
            self._send_write_command(
                'AT+CSSLCFG',
                f'"convert",1,"{client_crt_filename}","{client_key_filename}"'
            )
        self._send_write_command('AT+CSSLCFG', '"sslversion",0,3')
        self._send_read_command('AT+CSSLCFG')
        self._send_write_command(
            'AT+SMSSL', f'1,"{ca_crt_filename}","{client_crt_filename}"')
        self._send_read_command('AT+SMSSL')
        for i in range(3):
            self.logger.info(f'try to connect to mqtt ({i+1}/3)...')
            resp = self._send_execute_command('AT+SMCONN', timeout=10)
            if resp.is_success():
                self.logger.info(f'successfully connected to mqtt.')
                self.modem_status = MODEM_STATUS.MQTT_CONNECTED
                return True
        self.logger.warn('connection to mqtt failed!')
        self.modem_status = MODEM_STATUS.NETWORK_CONNECTED
        return False
    
    def _connect_http(
        self,
        url
    ):
        self.logger.info('*'*8 + ' connect_http ' + '*'*8)
        self.logger.info(f'url: {url}')
        self.ensure_network()
        self._send_write_command('AT+SHCONF', f'"URL","{url}"')
        self._send_write_command('AT+SHCONF', '"BODYLEN",1024')
        self._send_write_command('AT+SHCONF', '"HEADERLEN",350')
        for i in range(3):
            self.logger.info(f'try to connect to http server ({i+1}/3)...')
            resp = self._send_execute_command('AT+SHCONN', timeout=10)
            if resp.is_success():
                resp = self._send_read_command('AT+SHSTATE')
                if resp.is_success() and resp.message[0] == '1':
                    self.logger.info(f'successfully connected to http server.')
                    return True
        self.logger.warn('connection to http server failed!')
        return False

    def download_file(
        self,
        url : str
    ):
        file_chunk_size = 1024
        self.logger.info('*'*8 + ' download_file ' + '*'*8)
        self.logger.info(f'url: {url}')
        self.ensure_network()
        parsed_uri = urlparse(url)
        self._connect_http('{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri))
        self._send_execute_command('AT+SHCHEAD')
        self._send_write_command('AT+SHAHEAD', '"User-Agent","IOE Client"')
        self._send_write_command('AT+SHAHEAD', '"Connection","keep-alive"')
        self._send_write_command('AT+SHAHEAD', '"Cache-control","no-cache"')
        self._send_write_command('AT+SHREQ', f'"{url}",1')
        resp = self._wait_for_message('+SHREQ', timeout=10)
        if resp.is_success():
            error_code = int(resp.message[0].split(',')[1])
            self.logger.debug(f'error code is {error_code}')
            if (error_code == 200):
                data_length = int(resp.message[0].split(',')[2])
                self.logger.debug(f'data length is {data_length}')
                with open("foo.bin", "wb") as newFile:
                    start_idx = 0
                    while start_idx < data_length:
                        if data_length - start_idx < file_chunk_size:
                            file_chunk_size = data_length - start_idx
                        resp = self._send_write_command('AT+SHREAD', f'{start_idx},{file_chunk_size}')
                        if resp.is_success():
                            data_head = self._wait_for_message('+SHREAD')
                            data_content =  self.ser.read(file_chunk_size)
                            self.logger.debug(f'data_part is {data_content}')
                            newFile.write(bytearray(data_content))
                            start_idx += file_chunk_size 
            return True
            
        self.logger.warn('download file failed!')
        return False

    def check_if_file_exists(self, filename):
        self.logger.info('*'*8 + ' check if file exists' + '*'*8)
        self.logger.info(f'file: {filename}')
        self.ensure_power()
        res = self._send_write_command('AT+CFSGFIS', f'3,"{filename}"')
        if not res.is_error():
            filesize = int(res.message[0])
            self.logger.debug(f'file size is {filesize}')
            if filesize > 0:
                self.logger.info(f'file: {filename} exists.')
                return True
        else:
            self.logger.info(f'file: {filename} does not exist.')
            return False

    def write_file(self, filename):
        self.logger.info('*'*8 + ' write file' + '*'*8)
        self.logger.info(f'file: {filename}')
        self.ensure_power()
        with open(filename) as f:
            content = f.read()
        self.logger.debug(f'file content: {content}')
        self._send_execute_command('AT+CFSINIT')
        self._send_test_command(f'AT+CFSWFILE')
        self._send_write_command(
            'AT+CFSWFILE', f'3,"{filename}",0,{len(content)},9999')
        self._send_execute_command(content)
        self._send_execute_command('AT+CFSTERM')
        return True

    def delete_file(self, filename):
        self.logger.info('*'*8 + ' delete file' + '*'*8)
        self.logger.info(f'file: {filename}')
        self.ensure_power()
        self._send_write_command('AT+CFSDFILE', f'3,"{filename}"')
        return True

    def get_ntp_time(self, ntp_server):
        self.logger.info('*'*8 + ' sync_time ' + '*'*8)
        self.ensure_network()
        self._send_write_command('AT+CNTP', f'"{ntp_server}",0,0,2')
        self._send_execute_command('AT+CNTP')
        resp = self._wait_for_message('+CNTP', timeout=10)
        if resp.is_success() and resp.message[0].startswith('1,'):
            self.logger.debug('Get Module Time')
            time_resp = self._send_read_command('AT+CCLK')
            module_date = time_resp.message[0][1:9]
            module_time = time_resp.message[0][10:18]
            date_time_obj = datetime.strptime(
                f'{module_date} {module_time}', '%y/%m/%d %H:%M:%S')
            self.logger.info(f'time synced: current time is: {str(date_time_obj)}')
            return date_time_obj
        else:
            self.logger.error(f'failed to sync time. error msg: {resp.message[0]}')
            return None

    def mqtt_publish(self, topic, elem):
        self.logger.info('*'*8 + ' mqtt_publish ' + '*'*8)
        self.ensure_network()
        self.logger.debug(f'mqtt message: \'{elem}\'')
        self._send_write_command('AT+SMPUB', f'"{topic}",{len(elem)},1,0')
        res = self._send_execute_command(elem, timeout=10)
        return res.is_success()

    def ping(self, hostname):
        """Pings the host with the SIM7080 module."""
        self.logger.info(f'{"*"*8} ping {"*"*8}')
        self.ensure_network()
        self.logger.debug(f'hostname: {hostname}')
        self._send_write_command('AT+CNACT', '0,1')
        self._send_write_command('AT+SNPDPID', '0')
        res = self._send_write_command('AT+SNPING4', f'"{hostname}",3,16,1000')
        return res.message 

    def log_info(self):
        self.self.ensure_network()
        self.logger.info('*'*8 + ' info ' + '*'*8)
        self.logger.info('Display Product Identification Information')
        self._send_at_cmd('ATI')
        self.logger.info('Get Local Timestamp enabled/disabled')
        self._send_at_cmd('AT+CLTS?')
        self.logger.info('module time')
        self._send_at_cmd('AT+CCLK?')
        # enable debug messages
        self.logger.info('Report mobile equipment error')
        self._send_at_cmd('AT+CMEE=2')
        self.logger.info('Signal quality report')
        self._send_at_cmd('AT+CSQ')
        self.logger.info('Inquiring UE system information')
        self._send_at_cmd('AT+CPSI?')
        self.logger.info('Network Registration Status')
        self._send_at_cmd('AT+CGREG?')
        self.logger.info('SIM Lock')
        self._send_at_cmd('AT+CSIMLOCK?')
        self.logger.info('Enter PIN')
        self._send_at_cmd('AT+CPIN?')
        self._send_at_cmd('AT+CNACT?')
        self.logger.info('Inquiring UE system information')
        self._send_at_cmd('AT+CPSI?')

    def __send_at_cmd(self, at_cmd, end_str='OK', timeout=DEFAULT_TIMEOUT) -> Response:
        self.logger.debug(f'request  : {str(at_cmd)}')
        if timeout != DEFAULT_TIMEOUT:
            self.ser.timeout = timeout
        # check if unsolicited message is waiting
        while self.ser.inWaiting():
            msg = str(self.ser.read_until(b'\r\n'))
            self.logger.debug('unsolicited message from device :' + msg)
        self.ser.write((at_cmd + '\r\n').encode())
        response = Response()
        while 1:
            line = self.ser.read_until(b'\r\n')
            if line == b'':
                self.logger.debug('TIMEOUT!')
                response.error_code = 'TIMEOUT'
                break
            line = line.decode().strip('\r\n')
            if line == '':
                continue
            response._raw_message.append(line)
            if line.startswith('+CME ERROR: '):
                response.error_code = 'ERROR'
                break
            if line.startswith(end_str):
                response.error_code = 'OK'
                break
            if line.startswith('ERROR'):
                response.error_code = 'ERROR'
                break
        self.logger.debug('raw response :' + str(response._raw_message))
        self.ser.timeout = DEFAULT_TIMEOUT
        return response

    def __wait_for_msg(self, msg, timeout=DEFAULT_TIMEOUT) -> Response:
        self.logger.debug(f'wait for message  : {str(msg)}')
        if timeout != DEFAULT_TIMEOUT:
            self.ser.timeout = timeout
        response = Response()
        while 1:
            line = self.ser.read_until(b'\r\n')
            if line == b'':
                self.logger.debug('TIMEOUT!')
                response.error_code = 'TIMEOUT'
                break
            line = line.decode().strip('\r\n')
            if line == '':
                continue
            response._raw_message.append(line)
            if line.startswith('+CME ERROR: '):
                response.error_code = 'ERROR'
                break
            if line.startswith(msg):
                response.error_code = 'OK'
                break
            if line.startswith('ERROR'):
                response.error_code = 'ERROR'
                break
        self.logger.debug('raw response :' + str(response._raw_message))
        self.ser.timeout = DEFAULT_TIMEOUT
        return response

    def _send_test_command(self, command, timeout=DEFAULT_TIMEOUT) -> Response:
        resp = self.__send_at_cmd(command + '=?', timeout=timeout)
        resp.message = resp._raw_message
        return resp

    def _send_read_command(self, command, timeout=DEFAULT_TIMEOUT) -> Response:
        resp = self.__send_at_cmd(command + '?', timeout=timeout)

        for line in resp._raw_message:
            if line.startswith(command[2:] + ':'):
                resp.message.append(line[len(command):])
                self.logger.debug('expected line in result: ' + str(line))
            else:
                resp.message.append(line)
                self.logger.debug('unexpected line in result: ' + str(line))
        return resp

    def _send_write_command(
        self,
        command,
        parameters,
        timeout=DEFAULT_TIMEOUT
    ) -> Response:
        resp = self.__send_at_cmd(command + '=' + parameters, timeout=timeout)
        for line in resp._raw_message:
            if line.startswith(command[2:] + ':'):
                resp.message.append(line[len(command):])
            else:
                resp.message.append(line)
        return resp

    def _send_execute_command(
        self,
        command,
        timeout=DEFAULT_TIMEOUT
    ) -> Response:
        resp = self.__send_at_cmd(command, timeout=timeout)
        for line in resp._raw_message:
            if line.startswith(command[2:] + ':'):
                resp.message.append(line[len(command):])
            else:
                resp.message.append(line)
        return resp
    
    def _wait_for_message(
        self,
        msg,
        timeout=DEFAULT_TIMEOUT
    ) -> Response:
        resp = self.__wait_for_msg(msg, timeout=timeout)
        for line in resp._raw_message:
            if line.startswith(msg):
                resp.message.append(line[len(msg)+1:].strip())
            else:
                resp.message.append(line)
        return resp
