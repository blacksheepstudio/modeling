import socket, select, pickle
import atexit
# from gameobjects.gameobject import get_object_by_id
# from gameobjects.gameobject import load_user

import json
import sys
import pytmx

from game_locals import *

# constants
USER_LIST = 'mp/users/users.json'
TILE_SIZE = 8
BUFFER_SIZE = 1024
VERBOSE = False
OBJECT_LAYER = 2

START_ROOM = 'template_room'
START_COORDS = [160, 160]


# ERRORS
# 1001  :: Gameobject not exist

# TODO: Need to display enemy damage to players, both in white for other players to see, and in red for the player
# TODO: being hit.  Also need to display '<enemy> has been slain!' message as well.
class BroadcastQue(object):
    """ Queues messages to be sent to individual clients """
    def __init__(self, server):
        self.server = server
        self.que = []

    def add(self, message, target, color=NORMAL_COLOR):
        """
        :param message: Message to be broadcasted
        :param target: 'ALL', 'room:uniquename', 'charactername'
        :param color: (255, 255, 255)
        """
        if target == 'ALL':
            for charactername in self.characternames:
                self.que.append({'message': message, 'charactername': charactername, 'color': color})
        elif target.startswith('room:'):
            room = target.replace('room:', '')
            names = [player.name for id, player in self.server.goc.players.items() if player.current_room == room]
            for charactername in names:
                self.que.append({'message': message, 'charactername': charactername, 'color': color})
        else:
            self.que.append({'message': message, 'charactername': target, 'color': color})

    def dump(self, charactername):
        """ Return list of all messages intended for the given charactername, and pop them from the broadcast que """
        output_que = []
        for i, message in enumerate(self.que):
            if message['charactername'] == charactername:
                output_que.append(self.que.pop(i))
        return output_que

    @property
    def characternames(self):
        """ List of all characternames currently connected """
        return self.server.goc.playernames


# TODO: Finish this, starting with visual equipment for remoteclients updating
class PayloadQue(object):
    """ Queues payloads to be sent to individual clients"""
    def __init__(self, server):
        self.server = server
        self.que = []

    def add(self, tag, data, target):
        """
        :param tag: string, metadata so that client knows what to do with payload
        :param data: payload to be delivered to client(s)
        :param target: 'ALL', 'room:uniquename', 'charactername'
        """
        if target == 'ALL':
            for charactername in self.characternames:
                self.que.append({'tag': tag, 'data': data, 'charactername': charactername})
        elif target.startswith('room:'):
            room = target.replace('room:', '')
            names = [player.name for id, player in self.server.goc.players.items() if player.current_room == room]
            for charactername in names:
                self.que.append({'tag': tag, 'data': data, 'charactername': charactername})
        else:
            self.que.append({'tag': tag, 'data': data, 'charactername': target})

    def dump(self, charactername):
        """ Return list of all messages intended for the given charactername, and pop them from the broadcast que """
        output_que = []
        for i, message in enumerate(self.que):
            if message['charactername'] == charactername:
                output_que.append(self.que.pop(i))
        return output_que

    @property
    def characternames(self):
        """ List of all characternames currently connected """
        return self.server.goc.playernames


class RequestProcessor(object):
    def __init__(self, goc=None, server=None):
        self.goc = goc
        self.server = server
        self.broadcastque = BroadcastQue(self.server)
        self.payloadque = PayloadQue(self.server)

    def get_payload(self, request):
        """
        Takes request from client and processes payload using GOC
        Request in format:
        {'username': <user>, 'charactername': <name>, 'password': <pass>,
        'id': <playerid>, 'request': <req>, 'args': <args>}

        :param request: dictionary sent from client
        :return: {'status': 0, 'response': { <response object> } }
        """
        return getattr(self, request['request'])(request)

    def inventory_update(self, request):
        """ Send list of dictionaries of item data to client to update client-side RemoteInventory
        Request like: {... 'request': 'inventory_update', 'args': None} """
        # TODO: This will need to be changed if items besides Helm, Chest, Boots, and Weapon are equipped and have
        # graphics.
        playerid = request['id']
        inventory = self.goc.gameobjects[playerid].inventory
        slots = self.goc.gameobjects[playerid].inventory.slots
        payload = [{'name': item.fullname, 'graphic': item.sprite,
                    'equipped': inventory.is_equipped(item.uniquename)} for item in slots]
        images = inventory.visual_equipment
        self.payloadque.add('visualequipment', {'visualequipment': images, 'playerid': playerid},
                            'room:{0}'.format(self.goc.gameobjects[playerid].current_room))
        return {'status': 0, 'response': payload}

    def inventory_equip(self, request):
        """ Equips item on client's gameobject based on index """
        index = int(request['args'])
        playerid = request['id']
        try:
            self.goc.gameobjects[playerid].inventory.equip_item(index)
            item = self.goc.gameobjects[playerid].inventory.slots[index]
            fullname = item.fullname
        except RuntimeError:
            return {'status': -1, 'response': {'message': 'Could not equip item'}}
        return {'status': 0, 'response': {'message': 'Equipped {0}'.format(fullname)}}

    def inventory_unequip(self, request):
        """ Unequips item on client's gameobject based on index """
        index = int(request['args'])
        playerid = request['id']
        try:
            self.goc.gameobjects[playerid].inventory.unequip_item(index)
            item = self.goc.gameobjects[playerid].inventory.slots[index]
            fullname = item.fullname
        except RuntimeError:
            return {'status': -1, 'response': {'message': 'Could not unequip item'}}
        return {'status': 0, 'response': {'message': 'Unequipped {0}'.format(fullname)}}

    def ooc(self, request):
        """ Send out-of-character message to all players in all zones
        Request like: {... 'request': 'ooc', {'message': message} } """
        message = request['args']['message']
        self.broadcastque.add(message=message, target='ALL', color=OOC_COLOR)
        return {'status': 0, 'response': 'ooc message delivered to server'}

    def tell(self, request):
        """ Send private message to another player,
        Request like: {... 'request': 'tell', {'message': message, 'target': target_player}} """
        message = request['args']['message']
        target_player = request['args']['target']
        # Check if player is in remote clients, and correct for case sensitivity
        if target_player.capitalize() not in self.goc.playernames:
            return {'status': -1, 'response': {'message': 'Player not logged in'}}
        self.broadcastque.add(message=message, target=target_player.capitalize(), color=TELL_COLOR)
        return {'status': 0, 'response': 'tell message delivered to server'}

    def say(self, request):
        """ Broadcast message locally to other players, if NPC is targetted, will trigger dialogue with NPC """
        # TODO Finish npc aspect
        npc_id = request['args']['id']

        player = self.goc.gameobjects[request['id']]
        message = request['args']['message']
        room = 'room:{0}'.format(player.current_room)
        self.broadcastque.add(message=message, target=room)
        return {'status': 0, 'response': 'echo'}

    def attack(self, request):
        """ Request like: {... 'request': 'attack', 'args': <enemy id>}
        Return data like: {'status': 0, 'response': 'damage': <damage dealt> """
        try:
            # Calculate attack damage and execute on target
            enemyid = request['args']
            enemy = self.goc.gameobjects[enemyid]
            playerid = request['id']
            player = self.goc.gameobjects[playerid]
            damage = player.attack(enemyid)

            # Create broadcast message (TODO use weapon verb)
            room = 'room:{0}'.format(player.current_room)
            message = '{0} attacks {1} for {2} damage.'.format(player.name, enemy.name, damage)
            self.broadcastque.add(message=message, target=room)
            return {'status': 0, 'response': {'damage': damage}}
        except KeyError:
            return {'status': -1, 'response': {'message': 'Something went wrong, does current target still exist?'}}

    def get_target(self, request):
        """ Return target data like: {'name': <name>, 'stats': <stats dictionary>} """
        id = request['args'][0]
        try:
            gameobject = self.goc.gameobjects[id]
            name, stats = gameobject.name, gameobject.stats
            return {'status': 0, 'response': {'stats': stats, 'name': name}}
        except KeyError:
            return {'status': 1001, 'response': {'message': 'ID Does not exist in Gameobject controller'}}

    def get_roomdata(self, request):
        """ Return Co-ords to client of all gameobjects in room, also return all broadcast messages to client """
        # Get coordinates of only objects in the client's current room:
        current_room = self.goc.gameobjects[request['id']].current_room
        room_coords = self.goc.coords_sprite_map_for_room(current_room)
        charactername = request['charactername']
        return {'status': 0, 'response': {'coords': room_coords, 'messages': self.broadcastque.dump(charactername),
                                          'payloads': self.payloadque.dump(charactername)}}

    def update_coords(self, request):
        """ Update player's coords in the GOC, also return some basic player stats to client like:
         move_time, attack_speed """
        lf = self.goc.lifeforms[request['id']]
        lf.coords = request['args']
        return {'status': 0, 'response': {'move_time': lf.move_time, 'attack_time': lf.attack_time}}

    def login(self, request):
        """ Login client and create Gameobject for the client-user's character """
        if self.server.authenticate_credentials(request):
            if request['charactername'] not in self.goc.playernames:
                print('Player logging in, adding player Lifeform to GOC')
                print('Loading mp/users/{0}/sav'.format(request['charactername']))
                gameobject, id = self.goc.load_gameobject('mp/users/{0}.sav'.format(request['charactername']))
                print('Loaded, creating gameobject')
                print('Created gameobject with id: {0}'.format(id))
                # If the player has no coords, he's a fresh player, and should go to the starting room
                if not gameobject.current_room:
                    gameobject.current_room = START_ROOM
                    gameobject.coords = START_COORDS
                print('RETURNING!!!!!!!')
                return {'status': 0, 'response': {'id': id, 'coords': gameobject.coords, 'sprite': gameobject.graphic,
                        'current_room': gameobject.current_room}}
            else:
                return {'status': -1, 'response': {'message': 'Character already logged in'}}
        else:
            return {'status': -1, 'response': {'message': 'Credentials invalid'}}

    def logout(self, request):
        """ Logout client and remove their gameobject from the world """
        if self.server.authenticate_credentials(request):
            if request['charactername'] in self.goc.playernames:
                print('Removing gameobject with id: {0}'.format(request['id']))
                self.goc.remove_gameobject(request['id'])
                return {'status': 0, 'response': {'message': 'Logout successful'}}
            else:
                return {'status': -1, 'response': {'message': 'Character is not logged in'}}
        else:
            print('User had invalid credentials, halting action')
            return {'status': -1, 'response': {'message': 'Credentials invalid'}}

    def test(self, request):
        """ Simple socket test.  Send a message back and forth from client to server """
        playername = request['username']
        return {'status': 0, 'response': {'message': 'Hello {0}!'.format(playername)}}

    def evaluate(self, request):
        """ Allows client to get variable values from GOC, debugging only """
        result = eval('self.goc.{0}'.format(request['args']))
        return {'status': 0, 'response': {'message': result}}


class GameServer(object):
    def __init__(self, goc=None):
        # GOC is a GameObjectController, this will grant GameServer access to game data to send to clients
        self.goc = goc
        # RequestProcessor will respond to client request and deliver payload from the goc
        self.processor = RequestProcessor(self.goc, self)
        self.server = None

        with open(USER_LIST, 'r') as f:
            self.user_data = json.load(f)

        # que of messages to be broadcasted to other players, list of tuples containing message,
        # target playerid, and original playerid
        self.broadcast_que = []

    def server_start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('', 4000))
        # Kill any zombie connection:
        # ps - fA | grep python
        server.listen(5)
        self.server = server
        atexit.register(self.server_stop)

    def server_stop(self):
        if self.server:
            self.server.close()
            self.server = None

    def get_clients(self):
        if not self.server:
            self.server_start()

        clients = []
        Connections, wlist, xlist = select.select([self.server], [], [], 0.05)

        for Connection in Connections:
            client, Informations = Connection.accept()
            clients.append(client)

        return clients

    def logout_client(self, request):
        """
        Delete player instance from room and delete remote client instance from remote_clients dict
        :param request: dictionary containing 'username', 'password' and 'charactername'
        :return:
        """
        charactername = request['charactername']
        username = request['username']
        password = request['password']

        with open('mp/users/{0}'.format(USER_LIST), 'r') as f:
            userdata = json.load(f)
            f.close()
        current_user = userdata[username]
        if current_user['password'] != password:
            return {'status': -1, 'response': 'Password was invalid, or character/user does not exist'}

        # check that user is logged in
        if charactername not in self.goc.playernames:
            print('Cannot logout, user is not logged in')
            return {'status': -1, 'response': 'User is not logged in'}
        # save character
        # todo All this stuff
        # logout character

    def listen(self, clients):
        try:
            clients_list, wlist, xlist = select.select(clients, [], [], 0.05)
        except select.error:
            pass
        else:
            for client in clients_list:
                print('--Client conneted, listening...')
                request = self.receive_packet(client, BUFFER_SIZE)
                if request:
                    if request == -1:
                        print('--Client returned error, disconnecting')
                        client.close()
                    else:
                        try:
                            payload = self.process_request(request)
                        except RuntimeError:
                            payload = {'status': -1, 'response': 'Unable to process request, was it malformed?'}
                        payload_string = str(payload)
                        payload = pickle.dumps(payload)
                        buffer_size = sys.getsizeof(payload)
                        response = pickle.dumps(buffer_size)

                        if VERBOSE: print('--Sending buffer size: {0}'.format(buffer_size))
                        client.send(response)

                        # Wait for confirmation from client for buffer size
                        if VERBOSE: print('--awaiting client response to send payload')
                        client_response = self.receive_packet(client, 128)

                        if client_response:
                            if VERBOSE: print('--client response to send payload received:{0}'.format(client_response))
                            if client_response == buffer_size:
                                if VERBOSE: print('--Sending payload (size): {0}'.format(buffer_size))
                                if VERBOSE: print('--Sending payload data: {0}'.format(payload_string))
                                client.send(payload)
                            elif client_response == -1:
                                print('--Received error message from client')

                        # Client needs to confirm that it received payload

                print('Socket closed with client')
                client.close()

    @staticmethod
    def receive_packet(client, buffer_size):
        packet = client.recv(buffer_size)
        if packet:
            data = pickle.loads(packet)
            if data == -1:
                return -1
            else:
                print('received data:\n{0}'.format(data))
                return data
        else:
            return None

    def process_request(self, request):
        """ Receive client request, process and form the Payload to be returned """
        # If request is in valid format
        if {'username', 'charactername', 'password', 'request', 'id', 'args'} == set(request.keys()):
            if self.authenticate_credentials(request):

                return self.processor.get_payload(request)

        else:
            raise RuntimeError('Request is not in valid format\n'
                               'should be dictionary with keys:\n '
                               '"username", "charactername", "password", "request", "args"')

    def authenticate_credentials(self, request):
        username = request['username']
        password = request['password']
        charactername = request['charactername']
        if username in self.user_data:
            if password == self.user_data[username]['password']:
                if charactername in self.user_data[username]['characters']:
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False
