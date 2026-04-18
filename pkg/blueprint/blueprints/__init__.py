from __future__ import annotations

from blueprint import BlueprintEntry

from hardcode.blueprints import arena as _arena
from hardcode.blueprints import bar_chart as _bar_chart
from hardcode.blueprints import battlebot as _battlebot
from hardcode.blueprints import bear_of_doom as _bear_of_doom
from hardcode.blueprints import binary_tree as _binary_tree
from hardcode.blueprints import building_blocks as _building_blocks
from hardcode.blueprints import butterfly as _butterfly
from hardcode.blueprints import castle_keep as _castle_keep
from hardcode.blueprints import chemistry_class as _chemistry_class
from hardcode.blueprints import chess as _chess
from hardcode.blueprints import cinnamon_roll as _cinnamon_roll
from hardcode.blueprints import clash_arena as _clash_arena
from hardcode.blueprints import climbing_wall as _climbing_wall
from hardcode.blueprints import coffee as _coffee
from hardcode.blueprints import cold as _cold
from hardcode.blueprints import corridors as _corridors
from hardcode.blueprints import craters as _craters
from hardcode.blueprints import cubes as _cubes
from hardcode.blueprints import default_large1 as _default_large1
from hardcode.blueprints import default_large2 as _default_large2
from hardcode.blueprints import default_medium1 as _default_medium1
from hardcode.blueprints import default_medium2 as _default_medium2
from hardcode.blueprints import default_small1 as _default_small1
from hardcode.blueprints import default_small2 as _default_small2
from hardcode.blueprints import dna as _dna
from hardcode.blueprints import donut as _donut
from hardcode.blueprints import drawing_circles_is_hard as _drawing_circles_is_hard
from hardcode.blueprints import face as _face
from hardcode.blueprints import first_sound as _first_sound
from hardcode.blueprints import flappy_bird as _flappy_bird
from hardcode.blueprints import flowers as _flowers
from hardcode.blueprints import galaxy as _galaxy
from hardcode.blueprints import gaussian as _gaussian
from hardcode.blueprints import git_branches as _git_branches
from hardcode.blueprints import hooks as _hooks
from hardcode.blueprints import hopscotch as _hopscotch
from hardcode.blueprints import hourglass as _hourglass
from hardcode.blueprints import labyrinth as _labyrinth
from hardcode.blueprints import landscape as _landscape
from hardcode.blueprints import mandelbrot as _mandelbrot
from hardcode.blueprints import metropolitan_dystopia as _metropolitan_dystopia
from hardcode.blueprints import minimaze as _minimaze
from hardcode.blueprints import perch_point as _perch_point
from hardcode.blueprints import pixel_forest as _pixel_forest
from hardcode.blueprints import pls_buy_cucats_merch as _pls_buy_cucats_merch
from hardcode.blueprints import pong as _pong
from hardcode.blueprints import rush_bait as _rush_bait
from hardcode.blueprints import separated as _separated
from hardcode.blueprints import settlement as _settlement
from hardcode.blueprints import shish_kebab as _shish_kebab
from hardcode.blueprints import shrub as _shrub
from hardcode.blueprints import sierpinski_evil as _sierpinski_evil
from hardcode.blueprints import socket as _socket
from hardcode.blueprints import spikes as _spikes
from hardcode.blueprints import starry_night as _starry_night
from hardcode.blueprints import strings as _strings
from hardcode.blueprints import tea as _tea
from hardcode.blueprints import the_great_divide as _the_great_divide
from hardcode.blueprints import the_powerful_egg as _the_powerful_egg
from hardcode.blueprints import thread_of_connection as _thread_of_connection
from hardcode.blueprints import tiles as _tiles
from hardcode.blueprints import tree_of_life as _tree_of_life
from hardcode.blueprints import vase as _vase
from hardcode.blueprints import wall as _wall
from hardcode.blueprints import wasteland as _wasteland
from hardcode.blueprints import wasteland_oasis as _wasteland_oasis
from hardcode.blueprints import we_love_tetris as _we_love_tetris
from hardcode.blueprints import window_shopping as _window_shopping

__all__ = ["BLUEPRINTS", "BlueprintEntry"]

BLUEPRINTS: dict[str, tuple[BlueprintEntry, ...]] = {
    "arena": _arena.BLUEPRINT,
    "bar_chart": _bar_chart.BLUEPRINT,
    "battlebot": _battlebot.BLUEPRINT,
    "bear_of_doom": _bear_of_doom.BLUEPRINT,
    "binary_tree": _binary_tree.BLUEPRINT,
    "building_blocks": _building_blocks.BLUEPRINT,
    "butterfly": _butterfly.BLUEPRINT,
    "castle_keep": _castle_keep.BLUEPRINT,
    "chemistry_class": _chemistry_class.BLUEPRINT,
    "chess": _chess.BLUEPRINT,
    "cinnamon_roll": _cinnamon_roll.BLUEPRINT,
    "clash_arena": _clash_arena.BLUEPRINT,
    "climbing_wall": _climbing_wall.BLUEPRINT,
    "coffee": _coffee.BLUEPRINT,
    "cold": _cold.BLUEPRINT,
    "corridors": _corridors.BLUEPRINT,
    "craters": _craters.BLUEPRINT,
    "cubes": _cubes.BLUEPRINT,
    "default_large1": _default_large1.BLUEPRINT,
    "default_large2": _default_large2.BLUEPRINT,
    "default_medium1": _default_medium1.BLUEPRINT,
    "default_medium2": _default_medium2.BLUEPRINT,
    "default_small1": _default_small1.BLUEPRINT,
    "default_small2": _default_small2.BLUEPRINT,
    "dna": _dna.BLUEPRINT,
    "donut": _donut.BLUEPRINT,
    "drawing_circles_is_hard": _drawing_circles_is_hard.BLUEPRINT,
    "face": _face.BLUEPRINT,
    "first_sound": _first_sound.BLUEPRINT,
    "flappy_bird": _flappy_bird.BLUEPRINT,
    "flowers": _flowers.BLUEPRINT,
    "galaxy": _galaxy.BLUEPRINT,
    "gaussian": _gaussian.BLUEPRINT,
    "git_branches": _git_branches.BLUEPRINT,
    "hooks": _hooks.BLUEPRINT,
    "hopscotch": _hopscotch.BLUEPRINT,
    "hourglass": _hourglass.BLUEPRINT,
    "labyrinth": _labyrinth.BLUEPRINT,
    "landscape": _landscape.BLUEPRINT,
    "mandelbrot": _mandelbrot.BLUEPRINT,
    "metropolitan_dystopia": _metropolitan_dystopia.BLUEPRINT,
    "minimaze": _minimaze.BLUEPRINT,
    "perch_point": _perch_point.BLUEPRINT,
    "pixel_forest": _pixel_forest.BLUEPRINT,
    "pls_buy_cucats_merch": _pls_buy_cucats_merch.BLUEPRINT,
    "pong": _pong.BLUEPRINT,
    "rush_bait": _rush_bait.BLUEPRINT,
    "separated": _separated.BLUEPRINT,
    "settlement": _settlement.BLUEPRINT,
    "shish_kebab": _shish_kebab.BLUEPRINT,
    "shrub": _shrub.BLUEPRINT,
    "sierpinski_evil": _sierpinski_evil.BLUEPRINT,
    "socket": _socket.BLUEPRINT,
    "spikes": _spikes.BLUEPRINT,
    "starry_night": _starry_night.BLUEPRINT,
    "strings": _strings.BLUEPRINT,
    "tea": _tea.BLUEPRINT,
    "the_great_divide": _the_great_divide.BLUEPRINT,
    "the_powerful_egg": _the_powerful_egg.BLUEPRINT,
    "thread_of_connection": _thread_of_connection.BLUEPRINT,
    "tiles": _tiles.BLUEPRINT,
    "tree_of_life": _tree_of_life.BLUEPRINT,
    "vase": _vase.BLUEPRINT,
    "wall": _wall.BLUEPRINT,
    "wasteland": _wasteland.BLUEPRINT,
    "wasteland_oasis": _wasteland_oasis.BLUEPRINT,
    "we_love_tetris": _we_love_tetris.BLUEPRINT,
    "window_shopping": _window_shopping.BLUEPRINT,
}
