# -*- coding: utf-8 -*-

##################################################################################################

import logging

import xbmc
import xbmcaddon
import xbmcvfs

import clientinfo
import read_embyserver as embyserver
import connect.connectionmanager as connectionmanager
from dialogs import ServerConnect, UsersConnect, LoginConnect, LoginManual, ServerManual

##################################################################################################

log = logging.getLogger("EMBY."+__name__)
addon = xbmcaddon.Addon(id='plugin.video.emby')

XML_PATH = (addon.getAddonInfo('path'), "default", "1080i")

##################################################################################################

class ConnectManager(object):

    _shared_state = {} # Borg
    state = {}


    def __init__(self):

        self.__dict__ = self._shared_state

        if not self.state:
            client_info = clientinfo.ClientInfo()
            self.emby = embyserver.Read_EmbyServer()

            version = client_info.get_version()
            device_name = client_info.get_device_name()
            device_id = client_info.get_device_id()

            self._connect = connectionmanager.ConnectionManager(appName="Kodi",
                                                                appVersion=version,
                                                                deviceName=device_name,
                                                                deviceId=device_id)
            path = xbmc.translatePath(
                   "special://profile/addon_data/plugin.video.emby/").decode('utf-8')

            if not xbmcvfs.exists(path):
                xbmcvfs.mkdirs(path)

            self._connect.setFilePath(path)
            self.state = self._connect.connect()
            log.info("Started with: %s", self.state)


    def update_state(self):

        self.state = self._connect.connect({'updateDateLastAccessed': False})
        return self.state

    def get_state(self):
        return self.state

    def get_server(self, server):
        self.state = self._connect.connectToAddress(server)
        return self.get_state()

    @classmethod
    def get_address(cls, server):
        return connectionmanager.getServerAddress(server, server['LastConnectionMode'])

    def clear_data(self):
        self._connect.clearData()

    def select_servers(self):
        # Will return selected server or raise error
        state = self._connect.connect({'enableAutoLogin': False})
        user = state.get('ConnectUser') or {}

        dialog = ServerConnect("script-emby-connect-server.xml", *XML_PATH)
        kwargs = {
            'connect_manager': self._connect,
            'username': user.get('DisplayName', ""),
            'user_image': user.get('ImageUrl'),
            'servers': state['Servers'],
            'emby_connect': False if user else True
        }
        dialog.set_args(**kwargs)
        dialog.doModal()

        if dialog.is_server_selected():
            log.debug("Server selected")
            return dialog.get_server()

        elif dialog.is_connect_login():
            log.debug("Login with Emby Connect")
            try: # Login to emby connect
                self.login_connect()
            except RuntimeError:
                pass
            return self.select_servers()

        elif dialog.is_manual_server():
            log.debug("Add manual server")
            try: # Add manual server address
                return self.manual_server()
            except RuntimeError:
                return self.select_servers()
        else:
            raise RuntimeError("No server selected")

    def manual_server(self):
        # Return server or raise error
        dialog = ServerManual("script-emby-connect-server-manual.xml", *XML_PATH)
        dialog.set_connect_manager(self._connect)
        dialog.doModal()

        if dialog.is_connected():
            return dialog.get_server()
        else:
            raise RuntimeError("Server is not connected")

    def login_connect(self):
        # Return connect user or raise error
        dialog = LoginConnect("script-emby-connect-login.xml", *XML_PATH)
        dialog.set_connect_manager(self._connect)
        dialog.doModal()

        self.update_state()

        if dialog.is_logged_in():
            return dialog.get_user()
        else:
            raise RuntimeError("Connect user is not logged in")

    def login(self, server=None):
        # Return user or raise error
        server = server or self.state['Servers'][0]
        server_address = connectionmanager.getServerAddress(server, server['LastConnectionMode'])
        users = self.emby.getUsers(server_address)

        if not users:
            try:
                return self.login_manual(server_address)
            except RuntimeError:
                raise RuntimeError("No user selected")

        dialog = UsersConnect("script-emby-connect-users.xml", *XML_PATH)
        dialog.set_server(server_address)
        dialog.set_users(users)
        dialog.doModal()

        if dialog.is_user_selected():
            user = dialog.get_user()
            if user['HasPassword']:
                log.debug("User has password, present manual login")
                try:
                    return self.login_manual(server_address, user)
                except RuntimeError:
                    return self.login(server)
            else:
                user = self.emby.loginUser(server_address, user['Name'])
                self._connect.onAuthenticated(user)
                return user

        elif dialog.is_manual_login():
            try:
                return self.login_manual(server_address)
            except RuntimeError:
                return self.login(server)
        else:
            raise RuntimeError("No user selected")

    def login_manual(self, server, user=None):
        # Return manual login user authenticated or raise error
        dialog = LoginManual("script-emby-connect-login-manual.xml", *XML_PATH)
        dialog.set_server(server)
        dialog.set_user(user)
        dialog.doModal()

        if dialog.is_logged_in():
            user = dialog.get_user()
            self._connect.onAuthenticated(user)
            return user
        else:
            raise RuntimeError("User is not authenticated")

    def update_token(self, servers, server):
        self._connect.credentialProvider.addOrUpdateServer(servers, server)
        self.update_state()
