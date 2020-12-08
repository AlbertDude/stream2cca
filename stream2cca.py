#!/usr/bin/env python3
"""
stream audio to Chromecast Audio
TODO:
    - detect reconnect situation (I think what happens is get callback for track ended...)
      - test the implementation of this
      - update web page to handle the connected status value
    - add ability to select available devices from web-i/f
"""
import argparse
import datetime
import logging
import mutagen.easyid3  # pip3 install mutagen
import mutagen.id3      # pip3 install mutagen
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



# helpers
#

# Network port to use
# 9812 - Unassigned
#      - https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml?&page=117
PORT = 9812

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
    js_file.write("const port = '%d';\n" % PORT)

def to_min_sec(seconds, resolution="seconds"):
    """ convert floating pt seconds value to mm:ss.xx or mm:ss.x or mm:ss
    """
    if not isinstance(seconds, float):
        return '--:--'

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

def _clear_line2():
    """ clears line and places cursor back to start of the line
    """
    print("\r" + " " * 120 + "\r", end='')


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
        self.new_media_status_callback = kwargs.get('new_media_status_callback', None)
        self.mc = None
        self.state = 'UNKNOWN'
        self.prev_playing_interrupted = datetime.datetime.now()
        self.prev_filename = None
        self.playlist = []
        self.playlist_index = None
        self.muted = False
        self.pre_muted_vol = 0
        self.consecutive_update_status_exceptions = 0

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

    def new_media_status(self, status):  # {
        """ status listener implementation
            this method is called by media controller
            - it is registered via the call: self.mc.register_status_listener(self)
        """

        # (status.player_state == 'IDLE' and status.idle_reason == 'FINISHED')
        # - is a normal case indicating the song previously playing has completed
        # - i.e. device is IDLE because it FINISHED
        if status is None or (status.player_state == 'IDLE' and status.idle_reason == 'FINISHED'):
            if self.state != 'IDLE':
                # typically self.state == 'PLAYING' -- indicating we were playing a song
                self.verbose_logger("Status: FINISHED")
                self.state = 'IDLE'
                # play the next playlist entry if that's what we were doing (indicated by valid playlist)
                if self.playlist:
                    self.incr_playlist_index()
                    logger.info("Advancing PlayList to Track#: %d/%d" % (self.playlist_index, len(self.playlist)))
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

        # if caller specified a listener/callback, call that
        if self.new_media_status_callback:
            self.new_media_status_callback()
    # }

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
            server='http://' + IP_ADDRESS + ':%d/' % PORT,
            verbose_listener=True):
        """
        """
        self.prev_filename = filename
        assert os.path.isfile(filename), "Invalid file: %s" % (filename)
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

        # extract cover art to 'cover.jpg'
        assert SERVER_DIRECTORY, "SERVER_DIRECTORY not set properly"
        assert WEB_PAGE_REL_PATH, "WEB_PAGE_REL_PATH not set properly"
        pic_filename = os.path.join(SERVER_DIRECTORY, WEB_PAGE_REL_PATH, "cover.jpg")
        try:
            os.remove(pic_filename)  # remove old image
        except OSError:  # in case file doesn't exist
            pass

        tags = mutagen.id3.ID3(filename)
        keys = ["APIC:", "APIC:Cover"]  # try these keys
        for key in keys:
            pic_tag = tags.get(key)
            if pic_tag:
                pic_data = pic_tag.data
                if len(pic_data) > 0:
                    with open(pic_filename, "wb") as pic_file:
                        pic_file.write(pic_data)
                    break

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

    def get_paused(self):
        return self.state == 'PAUSED'

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
            returns tuple of strings for (artist, title, album, current_time, duration)
            returns None if loses connection with device
        """
        self._prep_media_controller()
        track_info = ""
        if self.state == 'PLAYING' or self.state == 'PAUSED':
            try:
                self.mc.update_status()
            except (pychromecast.error.UnsupportedNamespace, pychromecast.error.NotConnected) as error:
                logger.warning("Handled exception from: self.mc.update_status()!: %d" % self.consecutive_update_status_exceptions)
                logger.warning("  %s" % error)
                track_info = ("artist?", "title?", "album?", "cur_time?", "duration?")
                if self.consecutive_update_status_exceptions == 0:
                    self.update_status_exceptions_start_time = datetime.datetime.now()
                else:
                    elapsed = datetime.datetime.now() - self.update_status_exceptions_start_time
                    MAX_DURATION_EXCEPTIONS = 4
                    if elapsed.seconds >= MAX_DURATION_EXCEPTIONS:
                        logger.error("Got %d consecutive update status exceptions over %d seconds, disconnecting.."
                                % (self.consecutive_update_status_exceptions, elapsed.seconds))
                        return None
                self.consecutive_update_status_exceptions += 1
            else:
                artist = self.mc.status.artist
                artist = "??" if artist is None else artist
                title = self.mc.status.title
                title = "??" if title is None else title
                album = self.mc.status.album_name
                album = "??" if album is None else album
                track_info = (artist, title, album,
                    to_min_sec(self.mc.status.current_time),
                    to_min_sec(self.mc.status.duration))
                self.consecutive_update_status_exceptions = 0
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


# globals, overwrite these with proper values
PLAYLIST_FOLDER = None
SERVER_DIRECTORY = None
WEB_PAGE_REL_PATH = None


import http.server
import socketserver
class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):  # {
    """ Subclass to:
        - serve files from specific directory
        - redirect log_message to logger (rather than screen)
    """
    def __init__(self, *args, **kwargs):
        # TODO: why does this get called every second!!!

        try:
            super().__init__(*args, directory=SERVER_DIRECTORY, **kwargs)
        except BrokenPipeError as error:
            logger.warning("Handled exception from: http.server.SimpleHTTPRequestHandler.__init__()!")
            logger.warning("  %s" % error)


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
            self.path = os.path.join('/', WEB_PAGE_REL_PATH, 'web_page.html')
        elif not '.mp3' in self.path:
            # since the path starts with '/', need to use raw string concat methods
            # rather than os.path.join()
            self.path = '/' + WEB_PAGE_REL_PATH + self.path

        # Occasionally get this exception
        """
        File "./stream2cca.py", line 571, in do_GET
        return super().do_GET()
        File "/usr/lib/python3.7/http/server.py", line 653, in do_GET
        self.copyfile(f, self.wfile)
        File "/usr/lib/python3.7/http/server.py", line 844, in copyfile
        shutil.copyfileobj(source, outputfile)
        File "/usr/lib/python3.7/shutil.py", line 82, in copyfileobj
        fdst.write(buf)
        File "/usr/lib/python3.7/socketserver.py", line 799, in write
        self._sock.sendall(b)
        ConnectionResetError: [Errno 104] Connection reset by peer
        ----------------------------------------
        """

        try:
            super().do_GET()
        except ConnectionResetError as error:
            logger.warning("Handled exception from: super().do_GET()!")
            logger.warning("  %s" % error)

    def do_POST(self):  # {
        content_len = self.headers['Content-Length']
        content = self.rfile.read(int(content_len)).decode('utf-8') if content_len else ""

        def get_status():
            """
                sends response with status information composed of 8 elements, separated by "\n"
                - connected ("0"|"1")
                - device ("device name")
                - volume (000-100)
                - artist
                - title
                - album
                - current_time ("--:--")
                - duration ("--:--")
                - paused ("1")
            """
            statuses = thePlayer.get_status()
            try:
                status = "\n".join(statuses)
            except TypeError:
                status = "\n".join(["??"]*7)
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
# } ## class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):


def simple_threaded_server(server):
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logger.info("Started simple server at port: %d" % PORT)

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
        self.connected = False

        self._get_devices()

    def _get_devices(self):
        """ Gets chromecast audio devices and groups
            Modifies:
              .cc_audios - Chromecast Audio devices
              .cc_groups - Chromecast groups
              .cc_key_mapping - dictionary mapping from key -> CC audio or group
                  - devices ascend from 1 in alphabetic order
                  - groups descend from 0 in alphabetic order

        """
        self.cc_audios, self.cc_groups = CcAudioStreamer.get_devices()

        # sort the lists alphabetically by name
        self.cc_audios.sort(key=lambda x: x.name)
        self.cc_groups.sort(key=lambda x: x.name)

        # current mapping scheme has a limit of 10 devices and groups
        MAX_LIMIT = 10
        assert len(self.cc_audios) + len(self.cc_groups) <= MAX_LIMIT, "Update code to handle more than 10 CCA devices and groups"

        # NOTE: this code will fail for more than 10 devices+groups
        keys = [str((i+1)%10) for i in range(10)]   # ['1', ..., '9', '0']
        self.cc_key_mapping = dict(zip(keys, self.cc_audios))
        self.cc_key_mapping.update(dict(zip(reversed(keys), self.cc_groups)))

        #print("LEN", len(self.cc_key_mapping))
        #print(self.cc_key_mapping)

    def start(self):
        self._start_server()
        self._show_key_mappings(self.cc_key_mapping)
        self._main_loop()
        logger.warning("Exitted _main_loop")    # Debugging slow quitting

    def _start_server(self):
        self.my_server = MyThreadingTCPServer(("", PORT), MyHTTPRequestHandler)
        simple_threaded_server(self.my_server)
        logger.info("Server started")
        print("Server started")

    def _new_media_status_callback(self):  # {
        """ callback fcn to hook into CAS's new_media_status
            register this method wth CAS so that cas.new_media_status() calls this fcn
        """
        # cas.new_media_status() getting called means we're connected to the ChromeCast
        self.connected = True
    # }

    def _main_loop(self):  # {
        with NonBlockingConsole() as nbc:  # {
            while True:  # {
                # display a status leader
                _clear_line2()

                statuses = self.get_status()
                connected, device, volume, artist, title, album, current_time, duration, paused = statuses
                if device == "":
                    # This branch taken at startup when no device or group is selected
                    status = "Select device or group:"
                else:
                    if connected == "1":  # {

                        # Ideally would use these from "Misc Technical" but the PLAY doesn't display properly with my default mac font
                        # http://unicode.org/charts/PDF/U2300.pdf
    #                   PLAY_CH = "\u23f5"
    #                   STOP_CH = "\u23f9"
    #                   PAUSE_CH = "\u23f8"

                        # Instead, use "Block Elements" and the double vertical line:
                        # http://unicode.org/charts/PDF/U2580.pdf
                        PLAY_CH  = "\u25b6" # ▶
                        STOP_CH  = "\u25a0" # ■
                        PAUSE_CH = "\u2016" # ‖

                        status = "%s: %s: " % (device, volume)
                        if artist == "" and title == "" and album == "" and current_time == "" and duration == "":
                            status += "%s " % STOP_CH
                        else:
                            if paused == "1":
                                play_pause_ch = PAUSE_CH
                            else:
                                play_pause_ch = PLAY_CH
                            status += "%s " % play_pause_ch

                            status += "%s - %s (%s): " % (artist, title, album)
                            status += "%s/%s " % (current_time, duration)
                    # }
                    else:
                        DISCONNECTED_CH = "\u2716"  # ✖
                        status = "%s: %s " % (device, DISCONNECTED_CH)
                status += ">"
                print("\r%s " % status, end='')

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
                if k in self.cc_key_mapping:
                    cc  = self.cc_key_mapping[k]
                    self.cas = CcAudioStreamer(cc, new_media_status_callback=self._new_media_status_callback)
                    self.connected = True   # Assume connection OK
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
                    self._get_devices()
                    self._show_key_mappings(self.cc_key_mapping)

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

    def get_status(self):  # {
        """ returns status as 8-element tuple
            - connected, device, volume, artist, title, album, current_time, duration
        """
        device = ""
        volume = ""
        artist = ""
        title = ""
        album = ""
        current_time = ""
        duration = ""
        paused = ""
        if self.cas:
            device = self.cas.get_name()
            if self.connected:  # {

                muted, pre_muted_vol = self.cas.get_muted()
                # unicode speaker characters
                SPEAKER = "\U0001F508"
                SPEAKER_1 = "\U0001F509"
                SPEAKER_3 = "\U0001F50A"
                SPEAKER_MUTE = "\U0001F507"
                if muted:
                    volume = SPEAKER_MUTE + "%03d" % int(100 * pre_muted_vol + 0.5)
                else:
                    volume = SPEAKER_3 + "%03d" % int(100 * self.cas.get_vol() + 0.5)

                track_info = self.cas.get_track_info()
                if track_info is None:
                    print("Disconnected from device:")
                    self.connected = False
                else:
                    if track_info != "":
                        artist, title, album, current_time, duration = track_info
    #                   track_status = "%s - %s (%s)" % (artist, title, album)
    #                   playback_status = "%s/%s " % (current_time, duration)

                try:
                    if self.cas.get_paused():
                        paused = "1"
                    else:
                        paused = "0"
                except AttributeError:
                    # think this can occur if self.cas happens to die in the midst
                    pass
            # }

        connected = "1" if self.connected else "0"
        return connected, device, volume, artist, title, album, current_time, duration, paused
    # }

    @staticmethod
    def _show_key_mappings(cc_key_mapping):  # {
        """
           cc_key_mapping - dictionary mapping from key -> CC audio or group
        """

        def print_mapping(keys, descr):
            print("%s = %s" % (keys.center(5), descr))

        divider = "-"*66
        print(divider)
        print("Chromecast Audio Devices and Cast Groups:")
        if len(cc_key_mapping) > 0:
            for k, cc in cc_key_mapping.items():
                print("", k, "=", cc.name, "(%s)" % cc.model_name)
        else:
                print("  no devices available")
        print()
        print_mapping('- +', 'volume down/up')
        print_mapping('p', 'playfolder')
        print_mapping(',< >.', 'previous/next track')
        print_mapping('SPACE', 'pause/resume')
        print_mapping('q', 'quit')
        print_mapping('?', 'show key mappings')
        print(divider)
    # }
# } ## class InteractivePlayer():


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

    # set server directory to common folder of this file and the specified PLAYLIST_FOLDER
    cwd = os.getcwd()
    path_of_this_file = os.path.dirname(os.path.realpath(__file__))
    global SERVER_DIRECTORY
    SERVER_DIRECTORY = os.path.commonpath([path_of_this_file,
        os.path.normpath(os.path.join(cwd, PLAYLIST_FOLDER))])
#   print("SERVER_DIRECTORY:", SERVER_DIRECTORY)

    # relative path from server directory to this file (and the web_page
    # resources)
    global WEB_PAGE_REL_PATH
    WEB_PAGE_REL_PATH = os.path.relpath(path_of_this_file, SERVER_DIRECTORY)
#   print("WEB_PAGE_REL_PATH:", WEB_PAGE_REL_PATH)

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




