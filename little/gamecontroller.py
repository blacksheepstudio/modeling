from __future__ import division

import pygame
# from pygame.locals import *
# from pytmx.util_pygame import load_pygame

from functions.math import negpos

from gameobjects.gameobject import *
from mp.server import GameServer


class GameController(object):
    """
    Controls all aspect of the game engine, hosts server, interfaces with clients
    """
    def __init__(self):
        """
        :param world: wld template file
        """
        self.goc = GameObjectController()

        # {'playername': <lifeformid>, 'playername': <lifeformid>, ... }
        self.gameserver = GameServer(self.goc)

        self.running = False

    def load_game(self, save_file):
        """ Load GOC """
        pass

    def save_game(self, save_file):
        """ Pickle GOC """
        pass

    def update(self, dt):
        self.goc.update(dt)
        self.gameserver.update(dt)

    def run(self):
        """ Run the game loop """
        clock = pygame.time.Clock()
        self.running = True

        try:
            while self.running:
                dt = clock.tick(60)

                # Update Gameobjects
                self.goc.update(dt)

                # Listen on server for client requests
                # GameServer has access to GOC and can change gameobject's attributes directly
                self.gameserver.listen(self.gameserver.get_clients())

        except KeyboardInterrupt:
            self.running = False
        pass

