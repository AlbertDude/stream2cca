#!/usr/bin/env python3
"""
stream audio to Chromecast Audio
"""
import argparse
import datetime
import logging
import mutagen.easyid3  # pip3 install mutagen
import os
import pathlib
import pychromecast     # pip install PyChromecast==7.2.0  ## Other versions may work also
import random
import socket
import threading
import time
import urllib


# configure logging

#   logging.basicConfig(
#           #level=os.environ.get("LOGLEVEL", logging.INFO),
#           format='%(asctime)s.%(msecs)03d:%(levelname)s:%(name)s: %(message)s',
#           datefmt='%m/%d %H:%M:%S',
#           )

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOGLEVEL", logging.INFO))

logging_formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d:%(levelname)s:%(name)s: %(message)s',
        datefmt='%m/%d %H:%M:%S',
        )

# log to file
logging_fh = logging.FileHandler('s2c.log', mode='w')
logging_fh.setFormatter(logging_formatter)
logging_fh.setLevel(logging.INFO)
logger.addHandler(logging_fh)

# log warnings to console screen
logging_ch = logging.StreamHandler()
logging_ch.setFormatter(logging_formatter)
logging_ch.setLevel(logging.WARN)
logger.addHandler(logging_ch)


# Network port to use
PORT = 8000


# helpers
#


def get_ip_address():
    """ returns the machines local ip address
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # doesn't even have to be reachable
    s.connect(('10.255.255.255', 1))
    ip_address = s.getsockname()[0]
    s.close()
    return ip_address

IP_ADDRESS = get_ip_address()
with open("ip_address.js", "w") as js_file:
    js_file.write("// Dynamically generated js file for IP address\n")
    js_file.write("const ip_address = '%s';\n" % IP_ADDRESS)

def to_min_sec(seconds, resolution="seconds"):
    """ convert floating pt seconds value to mm:ss.xx or mm:ss.x or mm:ss
    """
    if not isinstance(seconds, float):
        return 'min:sec?'

    if resolution == 'seconds':
        seconds += 0.5

    mins = int(seconds / 60)
    secs = int(seconds) - 60 * mins

    if resolution == 'tenths':
        tenths = int(10 * (seconds - int(seconds)) + 0.5)
        return '%02d:%02d.%01d' % (mins, secs, tenths)
    elif resolution == 'hundredths':
        hundredths = int(100 * (seconds - int(seconds)) + 0.5)
        return '%02d:%02d.%02d' % (mins, secs, hundredths)
    else:
        # default to "seconds"
        return '%02d:%02d' % (mins, secs)

def _clear_line():
    """ clears line and places cursor back to start of the line
    """
    print(" " * 120 + "\r", end='')


class CcAudioStreamer():  # {
    """ Chromecast audio streamer
    """
    @staticmethod
    def get_devices():
        """
        """
        logger.info("Getting devices..")
        # get chromecasts
        ccs, browser = pychromecast.get_chromecasts()

        # get audios
        cc_audios = [cc for cc in ccs if cc.cast_type=='audio']

        # get groups
        cc_groups = [cc for cc in ccs if cc.cast_type=='group']

        logger.info("..done")
        return cc_audios, cc_groups

    def __init__(self, cc_device, **kwargs):
        """
        """
        self.cc = cc_device
        self.cc.wait()
        self.mc = None
        self.state = 'UNKNOWN'
        self.prev_playing_interrupted = datetime.datetime.now()
        self.prev_filename = None
        self.playlist = []
        self.playlist_index = None
        self.muted = False
        self.pre_muted_vol = 0

    def get_name(self):
        return self.cc.name

    def _prep_media_controller(self, verbose_listener=False):
        """
        """
        self.verbose_listener = verbose_listener
        if self.mc is None:
            self.mc = self.cc.media_controller
            self.mc.register_status_listener(self)  # this registers the new_media_status() method

    def verbose_logger(self, msg):
        """
        """
        if self.verbose_listener:
            logger.info(msg)

    def incr_playlist_index(self):
        if not self.playlist_index is None:
            self.playlist_index += 1
            if self.playlist_index >= len(self.playlist):
                self.playlist_index = 0

    def decr_playlist_index(self):
        if not self.playlist_index is None:
            self.playlist_index -= 1
            if self.playlist_index < 0:
                self.playlist_index = len(self.playlist) - 1

    def new_media_status(self, status):
        """ status listener implementation
            this method is called by media controller
            - it is registered via the call: self.mc.register_status_listener(self)
        """

        if status is None or (status.player_state == 'IDLE' and status.idle_reason == 'FINISHED'):
            if self.state != 'IDLE':
                self.verbose_logger("Status: FINISHED")
                self.state = 'IDLE'
                # playout the playlist if it exists
                if self.playlist:
                    self.incr_playlist_index()
                    self.play(self.playlist[self.playlist_index], verbose_listener = self.verbose_listener)
        elif status.player_state == 'IDLE' and status.idle_reason == 'CANCELLED':
            if self.state != 'IDLE':
                self.verbose_logger("Status: STOPPED")
                self.state = 'IDLE'
        elif status.player_state == 'PLAYING' and status.idle_reason == None:
            if self.state != 'PLAYING':
                self.verbose_logger("Status: STARTED_FROM_IDLE")
                self.state = 'PLAYING'
        elif status.player_state == 'PLAYING' and status.idle_reason == 'FINISHED':
            if self.state != 'PLAYING':
                self.verbose_logger("Status: STARTED_FROM_FINISHED")
                self.state = 'PLAYING'
        elif status.player_state == 'PLAYING' and status.idle_reason == 'INTERRUPTED':
            if self.state == 'PAUSED':
                self.verbose_logger("Status: RESUMED")
            elif self.state == 'PLAYING':
                cur_time = datetime.datetime.now()
                diff = cur_time - self.prev_playing_interrupted
                #logger.info(" -- time since previous: %d.%06d" % (diff.seconds, diff.microseconds))
                if diff.seconds >= 2:
                    self.verbose_logger("Status: STARTED_NEW_SONG (interrupting previous)")
                self.prev_playing_interrupted = cur_time
            else:
                self.verbose_logger("Status: Spurious PLAYING/INTERRUPTED")
            self.state = 'PLAYING'
        elif status.player_state == 'PAUSED':
            self.verbose_logger("Status: PAUSED")
            self.state = 'PAUSED'
        elif status.player_state == 'BUFFERING':
            self.verbose_logger("Status: BUFFERING")
            self.state = 'BUFFERING'
        else:
            #self.verbose_logger("Status: Spurious event: .player_state = %s, idle_reason = %s" % (status.player_state, status.idle_reason))
            pass

#           try:
#               next(self._media)
#               time.sleep(3)
#           except StopIteration:
#               self.cc.quit_app()
#               self.cc.__del__()

    def play_list(self, filelist, verbose_listener=False):
        """
        """
        self.playlist = filelist
        self.playlist_index = 0
        self.play(self.playlist[self.playlist_index], verbose_listener=verbose_listener)

    def get_playlist(self):
        """
        """
        return self.playlist

    def get_playlist_index(self):
        """
        """
        return self.playlist_index

    def get_playlist_current_file(self):
        """
        """
        return self.playlist[self.playlist_index]

    # playback controls
    def play(self, filename, mime_type='audio/mpeg',
            server='http://' + IP_ADDRESS + ':%s/' % PORT,
            verbose_listener=True):
        """
        """
        self.prev_filename = filename
        url = server + urllib.request.pathname2url(filename)
        logger.info("Play: %s" % url)
        self._prep_media_controller(verbose_listener=verbose_listener)
        ez = mutagen.easyid3.EasyID3(filename)
        try:
            artist = ez['artist'][0]
        except:
            artist = "Unknown artist"
        try:
            title = ez['title'][0]
        except:
            title = "Unknown title"
        try:
            album = ez['album'][0]
        except:
            album = "Unknown album"
        metadata = {'artist': artist, 'title': title, 'albumName': album}
        self.mc.play_media(url, mime_type, metadata=metadata)
        self.mc.block_until_active(3) # required to "connect" the media controller to the CC session

    def next_track(self):
        if self.playlist:
            self.incr_playlist_index()
            self.play(self.playlist[self.playlist_index], verbose_listener=False)

    def prev_track(self):
        if self.playlist:
            self.decr_playlist_index()
            self.play(self.playlist[self.playlist_index], verbose_listener=False)

    def pause(self):
        logger.info("Pause: ")
        self._prep_media_controller()
        self.mc.pause()

    def resume(self):
        logger.info("Resume: ")
        self._prep_media_controller()
        self.mc.play()

    def toggle_pause(self):
        """ toggles between pause and resume
        """
        prev = self.state
        if self.state == 'PLAYING':
            self.pause()
            new = 'PAUSED'
        elif self.state == 'PAUSED':
            self.resume()
            new = 'RESUMED'
        return prev, new

    def stop(self):
        logger.info("Stop: ")
        self._prep_media_controller()
        self.mc.stop()


    # volume commands
    def vol_toggle_mute(self):
        """
        """
        if self.muted:
            self.set_vol(self.pre_muted_vol)
            self.muted = False
            logger.info("Vol UNMuted")
        else:
            self.pre_muted_vol = self.get_vol()
            self.set_vol(0)
            self.muted = True
            logger.info("Vol Muted")

    def vol_up(self, step=0.1):
        """
        """
        if self.muted:
            cur_vol = self.get_vol()
            self.vol_toggle_mute()
            new_vol = self.get_vol()
        else:
            cur_vol = self.get_vol()
            new_vol = min(cur_vol + step, 1.0)
            logger.info("VolUp: Adjusting volume from %.2f -> %.2f" % (cur_vol, new_vol))
            self.cc.set_volume(new_vol)
        return cur_vol, new_vol

    def vol_down(self, step=0.1):
        """
        """
        if self.muted:
            cur_vol = self.get_vol()
            self.vol_toggle_mute()
            new_vol = self.get_vol()
        else:
            cur_vol = self.get_vol()
            new_vol = max(cur_vol - step, 0)
            logger.info("VolDown: Adjusting volume from %.2f -> %.2f" % (cur_vol, new_vol))
            self.cc.set_volume(new_vol)
        return cur_vol, new_vol

    def get_vol(self):
        """
        """
        return self.cc.status.volume_level

    def get_muted(self):
        """ returns tuple with elements:
            - boolean indicating mute status
            - pre-mute volume (if muted)
        """
        return self.muted, self.pre_muted_vol

    def set_vol(self, new_vol):
        """
        """
        new_vol = float(new_vol)
        logger.info("SetVol: Setting volume to %.2f" % (new_vol))
        self.cc.set_volume(new_vol)

    def get_track_info(self):  # {
        """
            returns (artist, title, album, current_time, duration) if PLAYING
            else returns None
        """
        self._prep_media_controller()
        track_info = None
        if self.state == 'PLAYING' or self.state == 'PAUSED':
            try:
                self.mc.update_status()
            except pychromecast.error.UnsupportedNamespace as error:
                #logger.error(str(error))
                logger.error(error)
                logger.error("Exception calling self.mc.update_status()!")
                track_info = ("artist?", "title?", "album?", "cur_time?",
                        "duration?")
            else:
                artist = self.mc.status.artist
                title = self.mc.status.title
                album = self.mc.status.album_name
                track_info = (artist, title, album,
                    to_min_sec(self.mc.status.current_time),
                    to_min_sec(self.mc.status.duration))
        return track_info
    # }

    def monitor_status(self):  # {
        """
        """
        self._prep_media_controller()
        prev_state = None
        while True:
            if self.state == 'PLAYING':
                self.mc.update_status()
                artist = self.mc.status.artist
                title = self.mc.status.title
                album = self.mc.status.album_name
                track_info = "%s - %s (%s)" % (artist, title, album)
            if self.state != prev_state:    # TODO: doesn't always catch a change...
                _clear_line()
                addtl_info = ": " + track_info if self.state == 'PLAYING' else ""
                logger.info("State change -> %s%s" % (self.state, addtl_info))
                prev_state = self.state
            if self.state == 'PLAYING':
                print("%s %s/%s \r" % (
                    track_info,
                    to_min_sec(self.mc.status.current_time),
                    to_min_sec(self.mc.status.duration)), end='')

            time.sleep(0.25)
    # }

# } ## class CcAudioStreamer():


def list_devices(cc_audios, cc_groups):
    """
    """
    # print audios
    print("Found %d Chromecast Audio devices:" % len(cc_audios))
    for cca in cc_audios:
        print("  '%s' (%s)" % (cca.name, cca.model_name))

    # print groups
    print("Found %d Chromecast Group devices:" % len(cc_groups))
    for cca in cc_groups:
        print("  '%s' (%s)" % (cca.name, cca.model_name))


import sys
import select
import tty
import termios
class NonBlockingConsole():
    """
        Taken from: https://stackoverflow.com/questions/2408560/python-nonblocking-console-input

        NOTE: initially tried using pynput for keypress detection, but had these issues:
          - pynput does not work on RPI over SSH -- presumably problem is trying to run over SSH
            - just trying to `import pynput` results in error
          - pynput run locally on Mac grabs ALL keypresses, even those intended for different window/app
    """

    def __enter__(self):
        self.old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, type, value, traceback):
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)

    def get_data(self):
        if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
            return sys.stdin.read(1)
        return False


# Helpers to setup an http server
#
# basic file serving functionality could be accomplished simply via
#    python3 -m http.server
#
# however, our customized http server provides for additional functionality:
# - interprets POST requests as commands to the interactive-player
# - supports serving both the player-controller web-page content (.html, .jpgs,
# .css, .js files) and the user-specified playlist files (.mp3)
#   - this adds complications because want to allow user to specify
#   arbitrary folder for the playlist
#   - thus, we'll need to set the root directory for the http server to the
#   commonpath of the playlist-folder and the web-page-folder
#   - additionally, we'll need to intercept and translate the paths of the
#   web-page file requests to incorporate the relative path from
#   server-root-directory to the web-page folder


# global, overwrite with value from command-line param
PLAYLIST_FOLDER = None


import http.server
import socketserver
class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):  # {
    """ Subclass to:
        - serve files from specific directory
        - redirect log_message to logger (rather than screen)
    """
    def __init__(self, *args, **kwargs):
        # TODO: why does this get called every second!!!
        assert not PLAYLIST_FOLDER is None, "Invalid PLAYLIST_FOLDER!"
#       print("PLAYLIST_FOLDER:", PLAYLIST_FOLDER)

        # set server directory to common folder of this file and the specified PLAYLIST_FOLDER
        cwd = os.getcwd()
        path_of_this_file = os.path.dirname(os.path.realpath(__file__))
        server_directory = os.path.commonpath([path_of_this_file,
            os.path.normpath(os.path.join(cwd, PLAYLIST_FOLDER))])
#       print("server_directory:", server_directory)

        # relative path from server directory to this file (and the web_page
        # resources)
        self.web_page_rel_path = os.path.relpath(path_of_this_file, server_directory)
#       print("web_page_rel_path:", self.web_page_rel_path)

        try:
            super().__init__(*args, directory=server_directory, **kwargs)
        except BrokenPipeError as error:
            logger.error(error)
            logger.error("Exception calling http.server.SimpleHTTPRequestHandler.__init__()!")


    def log_message(self, format, *args):
        #logger.info(format % args)
        pass

    def end_headers(self):
        """ HACKISH override so that I can insert my own headers
        """
        self.send_my_headers()
        super().end_headers()

    def send_my_headers(self):
        """ my specific headers
        """
        # these to force image files to refresh (avoid cached versions) since we
        # always use the same filename ('cover.jpg') for cover art
        self.send_header("Cache-Control", "max-age=0, must-revalidate, no-store")


    def do_GET(self):
        # redirect landing page (IP_ADDRESS:PORT or localhost:PORT)
        if self.path == '/':
            self.path = os.path.join('/', self.web_page_rel_path, 'web_page.html')
        elif not '.mp3' in self.path:
            # since the path starts with '/', need to use raw string concat methods
            # rather than os.path.join()
            self.path = '/' + self.web_page_rel_path + self.path

        return super().do_GET()

    def do_POST(self):  # {
        content_len = self.headers['Content-Length']
        content = self.rfile.read(int(content_len)).decode('utf-8') if content_len else ""

        def get_status():
            device_status, track_status, playback_status = thePlayer.get_status()
            status = "\n".join([device_status, track_status, playback_status])
            bstatus = status.encode()
            self.send_header("Content-Length", str(len(bstatus)))
            self.end_headers()
            self.wfile.write(bstatus)
            self.wfile.flush()

        # dictionary of commands and their respective handlers
        commands = {
                "volume_toggle_mute": thePlayer.volume_toggle_mute,
                "volume_up": thePlayer.volume_up,
                "volume_down": thePlayer.volume_down,
                "prev_track": thePlayer.prev_track,
                "next_track": thePlayer.next_track,
                "toggle_pause": thePlayer.toggle_pause,
                "get_status": get_status,
                }
        if content in commands:
            self.send_response(200)  # 200 OK
            self.send_header('Content-type', 'text/plain')
            # TODO: HACKY! special handling for get_status()
            # - don't log get_status() since they come in every 1000 ms
            if content != "get_status":
                self.end_headers()
                logger.info("Got POST command: %s" % content)
            if commands[content]:
                commands[content]()
        else:
            self.send_response(400)  # 400 Bad Request
            self.end_headers()
            logger.error("Unknown POST command: %s" % content)
    # }
# }


def simple_threaded_server(server):
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logger.info("Started simple server at port: %s" % PORT)

class MyThreadingTCPServer(socketserver.ThreadingTCPServer):  # {
    """
    This to address occasional error when quit and restart server:
        OSError: [Errno 48] Address already in use
    See: https://stackoverflow.com/questions/6380057/python-binding-socket-address-already-in-use/18858817#18858817

    Seems to work on Mac and RPi4
    """
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
# }


thePlayer = None    # global singleton

class InteractivePlayer():  # {
    """ Interactive Playlist player

        Incorporates
        - HTTP server for servicing music-file GET requests (from Chromecast) and player-command POST requests (from player-controller web page)
        - console-based key-char-based player-controller
    """
    def __init__(self, playlist_folder):
        self.playlist_folder = playlist_folder
        self.cas = None     # CC Audio Streamer

        self.cc_audios, self.cc_groups = CcAudioStreamer.get_devices()
        self.ccs = self.cc_audios + self.cc_groups
        assert self.ccs, "No Chromecasts"
        if len(self.ccs) > 10:
            # TODO: perhaps separate: 0-9 as CCAudios, <SHIFT>0-9 as CCGroups
            logger.warning("More than 10 Chromecast devices, only able to select up to 10")

        digits = [str(i) for i in range(10)]    # ['0', '1', ..., '9']
        self.cc_selectors = digits[:len(self.ccs)]

    def start(self):
        self._start_server()
        self._show_key_mappings(self.cc_selectors, self.ccs)
        self._main_loop()

    def _start_server(self):
        self.my_server = MyThreadingTCPServer(("", PORT), MyHTTPRequestHandler)
        simple_threaded_server(self.my_server)
        logger.info("Server started")
        print("Server started")

    def _main_loop(self):  # {
        with NonBlockingConsole() as nbc:  # {
            while True:  # {
                # display a status leader
                _clear_line()

                statuses = self.get_status()    # device, track, playback statuses
                status = " ".join(statuses)
                status += ">"
                print("%s \r" % status, end='')

                # Throttle the polling loop so python doesn't consume 100% of a core
                # - running @ 60Hz reduces CPU to < 1% on Mac but ~12% on RPi4
                # - running @ 30Hz reduces CPU to ~ 7% on RPi4
                # - running @ 20Hz reduces CPU to ~ 5% on RPi4
                time.sleep(1/20)

                k = nbc.get_data()  # returns False if no data
                if not k:
                    continue

                # quit: q   ##, <ESC>
                #if k == chr(27) or k == 'q':   ## testing for <ESC> also triggered by cursor keys
                if k == 'q':
                    self.my_server.shutdown()
                    interactive_print("Quitting")
                    break

                # select CC: 0, 1, ...
                if k in self.cc_selectors:
                    cc  = self.ccs[int(k)]
                    self.cas = CcAudioStreamer(cc)
                    print("Selected:", cc.name, "(%s)"%cc.model_name)

                # vol up & down
                elif k == '+' or k == '=':
                    self.volume_up()
                elif k == '-' or k == '_':
                    self.volume_down()

                # toggle pause/resume: <space>
                elif k == ' ':
                    self.toggle_pause()

                # play folder: p
                elif k == 'p':
                    if self.cas:
                        posixPath_list = list(pathlib.Path(self.playlist_folder).rglob("*.[mM][pP]3"))
                        if posixPath_list:
                            filelist = [str(pp) for pp in posixPath_list]
                            random.shuffle(filelist)
                            print("Playing playlist folder (%s) with %d files" % (self.playlist_folder, len(filelist)))

                            self.cas.play_list(filelist)
                        else:
                            print("No files found under playlist folder: %s" % (self.playlist_folder))

                # next & prev track
                elif k == '>' or k == '.':
                    self.next_track()
                elif k == '<' or k == ',':
                    self.prev_track()

                elif k == '?':
                    print("Help")
                    self._show_key_mappings(self.cc_selectors, self.ccs)

                # unused:
                else:
                    print('Unmapped key pressed:', k)
            # }
        # }
    # }

    def volume_toggle_mute(self):
        if self.cas:
            self.cas.vol_toggle_mute()

    def volume_up(self):
        if self.cas:
            prev, new = self.cas.vol_up(0.05)
            #interactive_print("Vol: %.2f -> %.2f" % (prev, new), clear_line=True)

    def volume_down(self):
        if self.cas:
            prev, new = self.cas.vol_down(0.05)
            #interactive_print("Vol: %.2f -> %.2f" % (prev, new), clear_line=True)

    def toggle_pause(self):
        if self.cas:
            prev, new = self.cas.toggle_pause()
            #interactive_print(new, clear_line=True)

    def next_track(self):
        if self.cas:
            self.cas.next_track()
            #interactive_print("Next track")

    def prev_track(self):
        if self.cas:
            self.cas.prev_track()
            #interactive_print("Prev track")

    def get_status(self):
        """ returns status as 3-element tuple
        """
        track_status = ""
        playback_status = ""
        if self.cas:
            device_name = self.cas.get_name()
            device_status = "%s " % (device_name)
            muted, pre_muted_vol = self.cas.get_muted()
            if muted:
                device_status += "(%.2fx): " % pre_muted_vol
            else:
                device_status += "(%.2f): " % self.cas.get_vol()

            track_info = self.cas.get_track_info()
            if track_info:
                artist, title, album, current_time, duration = track_info
                track_status = "%s - %s (%s)" % (artist, title, album)
                playback_status = "%s/%s " % (current_time, duration)
        else:
            device_status = "No connected device:"

        return device_status, track_status, playback_status

    @staticmethod
    def _show_key_mappings(cc_selectors, ccs):  # {

        def print_mapping(keys, descr):
            print("%s = %s" % (keys.center(7), descr))

        divider = "-"*66
        print(divider)
        print("Devices:")
        for i, cc in zip(cc_selectors, ccs):
            print("",i, "=", cc.name, "(%s)" % cc.model_name)
        print()
        print_mapping('- +', 'volume down/up')
        print_mapping('p', 'playfolder')
        print_mapping(',< >.', 'previous/next track')
        print_mapping('<SPACE>', 'pause/resume')
        print_mapping('q', 'quit')
        print_mapping('?', 'show key mappings')
        print(divider)
    # }
# }


def interactive_print(*args, **kwargs):
    clear_line = kwargs.pop('clear_line', False)
    if clear_line:
        _clear_line()
    else:
        # otherwise advance to next line
        print()
    print(" ".join(map(str, args)), **kwargs)


def main(args):  # {
    """
    """
    global PLAYLIST_FOLDER
    PLAYLIST_FOLDER = args.folder

    if len(args.command_args) == 0:
        global thePlayer
        thePlayer = InteractivePlayer(PLAYLIST_FOLDER)
        thePlayer.start()

    else:  # {
        # CLI commands

        command = args.command_args[0].lower()

        cc_audios, cc_groups = CcAudioStreamer.get_devices()

        if command == 'list':
            list_devices(cc_audios, cc_groups)
            exit()

        # set cc device
        if len(cc_audios) == 0 and len(cc_groups) == 0:
            print("No audio or group chromecast devices, exitting")
            exit()
        cc = None
        if args.devicename == None:
            if len(cc_audios) > 0:
                cc = cc_audios[0]
            else:
                cc = cc_groups[0]
            print("Defaulting to device ('%s')" % cc.name)
        else:
            for check in cc_audios + cc_groups:
                if check.name == args.devicename:
                    cc = check
                    break
        if cc is None:
            print("Unable to locate specified device ('%s'), exitting" % args.devicename)
            print("Available devices:")
            list_devices(cc_audios, cc_groups)
            print("Exitting")
            exit()

        cas = CcAudioStreamer(cc)

        # volume commands
        if command == 'volup':
            cas.vol_up()
            exit()

        if command == 'voldown':
            cas.vol_down()
            exit()

        if command == 'setvol':
            assert len(args.command_args) == 2, "Need to specify volume value in range [0, 1.0]"
            new_vol = float(args.command_args[1])
            cas.set_vol(new_vol)
            exit()


        # monitor status
        if command == 'status':
            cas.monitor_status()
            exit()


        # playback controls

        # play folder
        if command == 'playfolder':
            posixPath_list = list(pathlib.Path(PLAYLIST_FOLDER).rglob("*.[mM][pP]3"))
            filelist = [str(pp) for pp in posixPath_list]
            random.shuffle(filelist)
            print("Playing playlist with %d files:" % len(filelist), filelist)
            cas.play_list(filelist)
            prev_len_playlist = 0
            cur_playlist = cas.get_playlist()
            while cur_playlist:
                len_playlist = len(cur_playlist)
                if len_playlist != prev_len_playlist:
                    logger.info("Remaining files in playlist: %d" % len_playlist)
                    prev_len_playlist = len_playlist
                time.sleep(20)
                cur_playlist = cas.get_playlist()

        # play single file
        if command == 'playfile':
            assert len(args.command_args) == 2, "Need to specify filename to play"
            filename = args.command_args[1]
            assert os.path.isfile(filename)
            cas.play(filename)
            exit()

        if command == 'pause':
            cas.pause()
            exit()

        if command == 'resume':
            cas.resume()
            exit()

        if command == 'stop':
            cas.stop()
            exit()

        # Unknown command
        print("Unknown command: %s" % command)
        exit()
    # }

#}


if __name__ == '__main__': #{
    parser = argparse.ArgumentParser(description='Stream Audio to Chromecast (Audio)')

    parser.add_argument( "command_args", help="[list|status|playfile file|playfolder|pause|resume|stop|volup|voldown|setvol v]", nargs="*" )
#   parser.add_argument( '-l', '--list_devices', action="store_true", dest='list_devices',
#                   default=False, help='list CC audio and group devices' )
    parser.add_argument( '-d', '--devicename',
                    help='specify device (default is first audio device' )
    DEFAULT_FOLDER = 'ZPL'
    parser.add_argument( '-f', '--folder',
                    help='specify folder path to play (default="%s")' % DEFAULT_FOLDER, default=DEFAULT_FOLDER )
#   parser.add_argument( '-p', '--perception_only', action="store_false", dest='pnnf_input_files',
#                   default=True, help='skip generation of #pnnf_input.dat files' )

    args = parser.parse_args()
    main(args)
#}



#
# pytest unit tests
#
#   pytest -v -s stream2cca.py
#
# other pytest options:
#   --disable-warnings
#

def test0():
    """
        Monitor status
    """
    print()

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    print("AUDIOS:", cc_audios)
    print("GROUPS:", cc_groups)

    if cc_audios:
        cas = CcAudioStreamer(cc_audios[0])
        cas.monitor_status()

def test1():
    """
        Volume controls
    """
    print()

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    print("AUDIOS:", cc_audios)
    print("GROUPS:", cc_groups)

    if cc_audios:
        cas = CcAudioStreamer(cc_audios[0])

        cas.vol_down()
        time.sleep(3)
        cas.vol_up()
        time.sleep(3)
        cas.set_vol(0.3)

def test2():
    """
        Simple playback test
    """
    print()

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    print("AUDIOS:", cc_audios)
    print("GROUPS:", cc_groups)

    if cc_audios:
        cas = CcAudioStreamer(cc_audios[0])
        cas.set_vol(0.3)
        cas.play("Baby.30.mp3")
        time.sleep(65)

def test3():
    """
        Playback controls
    """
    print()

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    print("AUDIOS:", cc_audios)
    print("GROUPS:", cc_groups)

    if cc_audios:
        cas = CcAudioStreamer(cc_audios[0])
        cas.set_vol(0.3)
        cas.play("StayHigh.mp3")
        time.sleep(20)
        cas.play("Baby.30.mp3")
        time.sleep(10)
        cas.pause()
        time.sleep(5)
        cas.resume()
        time.sleep(30)
        cas.stop()
        time.sleep(5)
        cas.play("Baby.mp3")
        time.sleep(10)
        cas.stop()
        time.sleep(5)

def test4():
    """
        Play list of files
    """
    print()

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    print("AUDIOS:", cc_audios)
    print("GROUPS:", cc_groups)

    if cc_audios:
        cas = CcAudioStreamer(cc_audios[0])
        cas.set_vol(0.3)
        cas.play_list(["StayHigh.mp3", "ShortAndSweet.mp3", "Baby.mp3"])
        time.sleep(600)




