import os
import json

class Config():

    _keys = ['mqtt_server_host',
            'mqtt_server_port',
            'mqtt_clientid',
            'mqtt_user',
            'mqtt_password',
            'mqtt_keeptime',
            'mqtt_cleanss',
            'mqtt_qos',
            'mqtt_auth_type',
            'mqtt_client_id',
            'mobile_catm_nbiot',
            'mobile_apn']

    def __init__(self, filename):
        self.filename = filename

    def load_config(self):
        """
        Load config from file and environment
        :return:
        """
        self._load_from_file(self.filename)
        self._update_config_from_environment()
        return self.store

    def _load_from_file(self, filename):
        print('Loading settings from %s' % filename)
        self.store = json.loads(open(filename).read())

    def _update_config_from_environment(self):
        from_env = {}
        for key in self._keys:
            env = os.environ.get(key.upper(), None)
            if env:
                from_env[key] = env
        self.store.update(from_env)