""" Quest - An epic journey.

Simple demo that demonstrates PyTMX and pyscroll.

requires pygame and pytmx.

https://github.com/bitcraft/pytmx

pip install pytmx
"""
from __future__ import division

import pygame
from pygame.locals import *
from pytmx.util_pygame import load_pygame

import pyscroll
import pyscroll.data
from pyscroll.group import PyscrollGroup

import graphics.eztext as eztext
from graphics.graphictext import draw_lines, draw_text, InputLog, InventoryBox

from functions.math import negpos
from mp.client import PacketSizeMismatch
from mp.client import GameClient


# Player starting room
STARTING_ROOM = 'gameobjects/room/test8.tmx'
# Player starting position
STARTING_POSITION = [160, 160]
# Default run speed
MOVE_TIME = 8

# Default Resolution
DEFAULT_RESOLUTION = [900, 506]
# Map camera zoom
MAP_ZOOM = 4.5
# Default Font
FONT = None

# size of walkable tile
TILE_SIZE = 8
# define rate that the server is polled, lower number means more polling
POLL_RATE = 10
# debug messages displayed on screen
DEBUG_MODE = True
# Pyscroll default layer
DEFAULT_LAYER = 2


def init_screen(width, height):
    """Simple wrapper to keep the screen resizeable"""
    # screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    screen = pygame.display.set_mode((width, height))
    return screen


def load_sprite(filename):
    return pygame.image.load(filename)


class Camera(object):
    """Invisible object that slowly follows player, screen locks onto this object"""
    def __init__(self, hero):
        self.hero = hero
        x, y = self.hero.position[0], self.hero.position[1]
        self.rect = pygame.Rect(x, y, 8, 8)
        self._position = self.hero.position
        self.spd = 100.

    def update(self, dt):
        self.x += (self.hero.x - self.x) * (dt / self.spd)
        self.y += (self.hero.y - self.y) * (dt / self.spd)
        self.rect.topleft = self._position

    @property
    def x(self):
        return self._position[0]

    @x.setter
    def x(self, value):
        self._position[0] = value

    @property
    def y(self):
        return self._position[1]

    @y.setter
    def y(self, value):
        self._position[1] = value

    @property
    def position(self):
        return list(self._position)

    @position.setter
    def position(self, value):
        self._position = list(value)


class RemoteSprite(pygame.sprite.Sprite):
    """
    This object is the counterpart of a gameobject on the server side.  It holds a limited amount
    of information about its sister game object.  This allows the server to expose a limited amount
    of information to the client, and the client to render a representation of all the gameobjects
    in the game world.
    """
    def __init__(self, id, sprite, coords):
        """
        :param id: id of sister gameobject on server side
        :param sprite: image
        :param coords: coordinates to render on screen (from remote gameobject)
        :param stats: stats of Gameobject counterpart
        """
        pygame.sprite.Sprite.__init__(self)
        self.rect = self.image.get_rect()

        self.id = id
        self.image = load_sprite(sprite).convert_alpha()
        self._position = coords

    def update(self, dt):
        self.rect.topleft = self._position

    @property
    def x(self):
        return self._position[0]

    @x.setter
    def x(self, value):
        self._position[0] = value

    @property
    def y(self):
        return self._position[1]

    @y.setter
    def y(self, value):
        self._position[1] = value

    @property
    def position(self):
        return list(self._position)

    @position.setter
    def position(self, value):
        self._position = list(value)


class Hero(object):
    """ Our Hero """

    def __init__(self, id, sprite, coords):
        """
        :param lifeform: .sav file of lifeform class
        """
        # RemoteSprite object
        self.remotesprite = RemoteSprite(id=id, sprite=sprite, coords=coords)

        self.position = self.lifeform.coords
        self._position = self.position
        self.x = self.position[0]
        self.y = self.position[1]

        self.camera = Camera(self)

        # 'move_time' is determined by speed stat, the lower this is, the faster you can move from tile to tile
        self.move_time = MOVE_TIME
        self.move_timer = self.move_time
        self.moving = False
        self.target_coords = None

    @property
    def id(self):
        return self.remotesprite.id

    @property
    def rect(self):
        return self.remotesprite.rect

    @property
    def x(self):
        return self.remotesprite.x

    @x.setter
    def x(self, value):
        self.remotesprite.x = value

    @property
    def y(self):
        return self.remotesprite.y

    @y.setter
    def y(self, value):
        self.remotesprite.y = value

    @property
    def position(self):
        return self.remotesprite.position

    @position.setter
    def position(self, value):
        self.remotesprite.position = list(value)

    def update(self, dt):
        self.rect.topleft = self._position


class Game(object):
    """This class is essentially the Wizard of Oz"""
    def __init__(self, charactername='Mike', username='leif', password='mypw', ip='127.0.0.1',
                 current_room=None):
        self.client = GameClient(charactername=charactername, username=username, password=password, ip=ip)

        # List of other lifeform Other objects [{id: RemoteSprite}, ...]
        self.others = {}

        # Rate that chat polls are sent to server
        self.poll_frequency = POLL_RATE
        self.poll_timer = self.poll_frequency
        self.out_going_message = None

        # true while running
        self.running = False

        # load data from pytmx
        if not current_room:
            current_room = STARTING_ROOM
        tmx_data = load_pygame(current_room)
        self.map_data = tmx_data

        # create new data source for pyscroll
        map_data = pyscroll.data.TiledMapData(tmx_data)

        # create new renderer (camera)
        self.map_layer = pyscroll.BufferedRenderer(map_data, screen.get_size())
        self.map_layer.zoom = MAP_ZOOM

        # pyscroll supports layered rendering.
        self.group = PyscrollGroup(map_layer=self.map_layer, default_layer=DEFAULT_LAYER)

        # Login to server:
        # Get room instance and player object id
        response = self.client.login()
        playerid = response['response']['playerid']
        sprite = response['response']['sprite']
        coords = response['coords']['coords']
        self.hero = Hero(id=playerid, sprite=sprite, coords=coords)

        # This is late -- ???
        self.current_room = response['response']['current_room']
        # put the hero in the center of the map
        # TODO: Put here in coords on hero object
        self.hero.position = STARTING_POSITION
        self.hero.lifeform.coords = self.hero.position

        # add our hero to the group
        self.group.add(self.hero)

        # Create text box
        text_box_x, text_box_y = self.screen_coords((3, 95))
        self.text_box = eztext.Input(maxlength=90, color=(255, 255, 255), x=text_box_x, y=text_box_y,
                                     font=pygame.font.Font(FONT, 26), prompt=': ')
        # Create InputLog
        self.inputlog = InputLog(coords=self.screen_coords((3, 92)), max_length=10, size=22, spacing=18, font=FONT)
        # Create Combatlog
        self.combatlog = InputLog(coords=(1050, 860), max_length=10, size=22, spacing=18, font=FONT)

    @property
    def screen_size(self):
        return pygame.display.Info().current_w, pygame.display.Info().current_h

    def parse_cli(self, msgvalue):
        try:
            # r = a.send(msgvalue)
            self.inputlog.add_line(msgvalue)
            self.out_going_message = msgvalue
            if 'set' in msgvalue:
                if len(msgvalue.split()) == 3:
                    attribute = msgvalue.split()[1]
                    value = msgvalue.split()[2]
                    if value.isdigit():
                        value = int(value)
                    if hasattr(self.hero, attribute):
                        setattr(self.hero, attribute, value)
                        self.inputlog.add_line('System: Set {0} to {1}'.format(attribute, value))
                    else:
                        self.inputlog.add_line('System: {0} unknown attribute'.format(attribute))
                else:
                    self.inputlog.add_line('Help: set <attribute> <value>')
            elif 'who room' in msgvalue:
                lifeforms = self.current_room.lifeforms
                for id, lifeform in lifeforms.items():
                    self.inputlog.add_line('{0} : {1}'.format(id, lifeform.name))
            elif 'get' in msgvalue:
                if len(msgvalue.split()) == 3:
                    instance = msgvalue.split()[1]
                    attribute = msgvalue.split()[2]
                    value = getattr(eval(instance), attribute)
                    self.inputlog.add_line(str(value))
                else:
                    self.inputlog.add_line('Help: get <instance> <attribute>')
            elif 'eval' in msgvalue:
                result = eval(msgvalue.replace('eval', '').lstrip())
                self.inputlog.add_line(str(result))
            elif 'exec' in msgvalue:
                exec (msgvalue.replace('exec', '').lstrip())
            elif 'quit' == msgvalue.split()[0].lower():
                self.running = False
            elif 'camera' == msgvalue.split()[0].lower():
                self.hero.camera.spd = int(msgvalue.split()[1])
            elif 'debug' == msgvalue.split()[0].lower():
                global DEBUG_MODE
                if msgvalue.split()[1].lower() == 'on':
                    DEBUG_MODE = True
                else:
                    DEBUG_MODE = False
        except:
            self.inputlog.add_line('Some unknown error occurred')

    def handle_input(self, dt):
        """ Handle pygame input events"""
        # event = poll()
        events = pygame.event.get()

        # while event:
        for event in events:
            # update text_box

            if event.type == QUIT:
                self.running = False
                break

            # This is where key press events go
            elif event.type == KEYDOWN:
                msgvalue = self.text_box.update(events)
                if msgvalue:
                    self.parse_cli(msgvalue)

                if event.key == K_ESCAPE:
                    self.running = False
                    break

                elif event.key == K_EQUALS:
                    self.map_layer.zoom += .1

                elif event.key == K_MINUS:
                    value = self.map_layer.zoom - .1
                    if value > 0:
                        self.map_layer.zoom = value

            # this will be handled if the window is resized
            elif event.type == VIDEORESIZE:
                init_screen(event.w, event.h)
                self.map_layer.set_size((event.w, event.h))

            elif event.type == KEYUP:
                if event.key == K_LSHIFT or event.key == K_RSHIFT:
                    self.text_box.shifted = False
            # event = poll()

        # using get_pressed is slightly less accurate than testing for events
        # but is much easier to use.
        moved = False
        if self.hero.move_timer <= 0:
            if not self.hero.moving:
                pressed = pygame.key.get_pressed()
                target_coords = [None, None]
                if pressed[K_UP]:
                    # This is a diagonal fix, pre-checking for collision on one of the axis
                    if not self.collision_check([self.hero.x, self.hero.y - TILE_SIZE]):
                        moved = True
                        target_coords[1] = self.hero.y - TILE_SIZE
                elif pressed[K_DOWN]:
                    if not self.collision_check([self.hero.x, self.hero.y + TILE_SIZE]):
                        target_coords[1] = self.hero.y + TILE_SIZE
                        moved = True

                if pressed[K_LEFT]:
                    target_coords[0] = self.hero.x - TILE_SIZE
                    moved = True
                elif pressed[K_RIGHT]:
                    target_coords[0] = self.hero.x + TILE_SIZE
                    moved = True

                if moved:
                    target_coords = [self.hero.position[i] if item is None else
                                     item for i, item in enumerate(target_coords)]
                    self.move_timer_reset()
                    self.move_lifeform(target_coords)
        else:
            return

    def move_timer_reset(self):
        self.hero.move_timer = self.hero.move_time

    def move_lifeform(self, position):
        """
        moves lifeform on grid while checking for collision
        :param position: position to move to
        :return:
        """
        if not self.collision_check(position):
            # Immediately set actual lifeform co-ordinates to new position
            self.hero.lifeform.coords = position

            # Set new coords as target for sprite animation to move to
            self.hero.target_coords = [int(position[0]), int(position[1])]
            self.hero.moving = True

            # Update server that we are moving
            self.client.send_command('move', [self.hero.target_coords])

    def collision_check(self, position, layers=None):
        """
        Checks if given coordinates are occupied by a tile marked 'wall'
        :param position:
        :return:
        """
        if not layers:
            layers = [0, 1]
        else:
            layers = layers
        # Get all tiles at this position, in all layers and check for 'wall' == 'true'
        collide = False
        tile_pos_x = position[0] / TILE_SIZE
        tile_pos_y = position[1] / TILE_SIZE
        tiles = [self.map_data.get_tile_properties(tile_pos_x, tile_pos_y, layer) for layer in layers]
        tiles = [tile['wall'] for tile in tiles if tile]
        for wall in tiles:
            if wall == 'true':
                collide = True
        return collide

    def poll_server(self, dt=60):
        """Count down to next contact with server"""
        self.poll_timer -= dt / 50.
        if self.poll_timer <= 0:
            self.poll_timer = self.poll_frequency
            r = self.client.send_command('update_coords', [])
            self.update_lifeforms(r['response'])

    def update_lifeforms(self, lifeforms):
        """Update current lifeforms with new information from server"""
        # Update data on all lifeforms in room
        self.current_room.lifeforms.update(lifeforms)

        # If object exists on server but not on client yet, create it
        for id, lifeform in self.current_room.lifeforms.items():
            if id not in self.others.keys():
                if lifeform.name != self.hero.lifeform.name:
                    self.others[id] = RemoteSprite(lifeform=lifeform)
                    self.group.add(self.others[id])

        # If object doesn't exist on server but exists here, remove it
        for id, sprite in self.others.items():
            if id not in self.current_room.lifeforms.keys():
                del self.others[id]

        # Update positions of all gameobjects
        for id, sprite in self.others.items():
            self.others[id].position = self.current_room.lifeforms[id].coords

    def update(self, dt):
        """ Tasks that occur over time should be handled here"""
        self.group.update(dt)
        # update camera
        self.hero.camera.update(dt)

        # STATE: 'moving'
        # (If we are moving to another tile)
        self.hero.move_timer -= dt / 100.
        if self.hero.moving:
            distance_x, distance_y = (self.hero.target_coords[0] - self.hero.x,
                                      self.hero.target_coords[1] - self.hero.y)
            stepx, stepy = (negpos(distance_x), negpos(distance_y))

            self.hero.x += stepx
            self.hero.y += stepy

            if self.hero.move_timer <= 0:
                self.hero.moving = False
                self.hero.position = self.hero.target_coords
                self.hero.lifeform.coords = self.hero.target_coords

    def draw(self, surface):
        # center the map/screen on our Hero
        self.group.center(self.hero.camera.rect.center)

        # draw the map and all sprites
        self.group.draw(surface)

    def screen_coords(self, coords):
        """
        :param coords: percentage of each axis.  i.e. (50, 50) will put an object in the center of the screen
        :return: Actual co-ords per resolution
        """
        screen_x, screen_y = self.screen_size
        new_x = (coords[0]/100) * screen_x
        new_y = (coords[1]/100) * screen_y
        return new_x, new_y

    def run(self):
        """ Run the game loop"""
        clock = pygame.time.Clock()
        self.running = True

        from collections import deque
        times = deque(maxlen=30)

        try:
            while self.running:
                dt = clock.tick(60)
                times.append(clock.get_fps())

                # Update From Server
                try:
                    self.poll_server(dt)
                except PacketSizeMismatch:
                    self.inputlog.add_line('Packet size mismatch!! Ignoring')

                # Handle input and render
                self.handle_input(dt)
                self.update(dt)
                self.draw(screen)

                # debug draw co-ordinates
                if DEBUG_MODE:
                    # pos = [coord/16 for coord in self.hero.position]
                    draw_text('hero.position:. . . . {0}'.format(str(self.hero.position)), screen, coords=(10, 10))
                    draw_text('lifeform.position:. . {0}'.format(str(self.hero.lifeform.coords)), screen, coords=(10, 25))
                    draw_text('delta t:. . . . . . . {0}'.format(str(dt)), screen, coords=(10, 40))
                    draw_text('server poll:. . . . . {0}'.format(str(self.poll_timer)), screen, coords=(10, 55))
                    draw_text('moving: . . . . . . . {0}'.format(str(self.hero.moving)), screen, coords=(10, 70))
                    draw_text('target_coords:. . . . {0}'.format(str(self.hero.target_coords)), screen, coords=(10, 85))
                    draw_text('map_zoom: . . . . . . {0}'.format(str(self.map_layer.zoom)), screen, coords=(10, 100))
                    draw_text('screen size:. . . . . {0}'.format(str(self.screen_size)), screen, coords=(10, 115))
                    draw_text(str(pygame.display.Info().current_w), screen, coords=(10, 130))

                # blit text objects to screen
                self.text_box.draw(screen)
                self.inputlog.draw(screen)
                self.combatlog.draw(screen)

                pygame.display.flip()

        except KeyboardInterrupt:
            self.running = False


if __name__ == "__main__":
    print('Testing Client::: PREALPHA')
    charactername = raw_input('charactername: ')
    username = raw_input('Username: ')
    password = raw_input('Password: ')

    pygame.init()
    pygame.font.init()
    screen = init_screen(*DEFAULT_RESOLUTION)
    pygame.display.set_caption('Little v0.0.1')

    try:
        game = Game(charactername=charactername, username=username, password=password)
        game.run()
    except:
        pygame.quit()
        raise