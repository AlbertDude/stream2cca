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
import pychromecast as pycc     # pip install PyChromecast==7.2.0  ## Other versions may work also
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

def to_min_sec(seconds, resolution="seconds"):
    """ convert floating pt seconds value to mm:ss.xx or mm:ss.x or mm:ss
    """
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
    print(" " * 100 + "\r", end='')


class CcAudioStreamer():  # {
    """ Chromecast audio streamer
    """
    @staticmethod
    def get_devices():
        """
        """
        logger.info("Getting devices..")
        # get chromecasts
        ccs, browser = pycc.get_chromecasts()

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
        self.incr_playlist_index()
        self.play(self.playlist[self.playlist_index], verbose_listener=False)

    def prev_track(self):
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
    def vol_up(self, step=0.1):
        """
        """
        cur_vol = self.cc.status.volume_level
        new_vol = min(cur_vol + step, 1.0)
        logger.info("VolUp: Adjusting volume from %.2f -> %.2f" % (cur_vol, new_vol))
        self.cc.set_volume(new_vol)
        return cur_vol, new_vol

    def vol_down(self, step=0.1):
        """
        """
        cur_vol = self.cc.status.volume_level
        new_vol = max(cur_vol - step, 0)
        logger.info("VolDown: Adjusting volume from %.2f -> %.2f" % (cur_vol, new_vol))
        self.cc.set_volume(new_vol)
        return cur_vol, new_vol

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
            self.mc.update_status()
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

# }


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


# Helpers to setup a simple http server
# alternatively basic functionality could be accomplished via
#    python3 -m http.server


# figure out path from where script is run to where script is located (and where the web page is located)
path_of_this_file = os.path.dirname(os.path.realpath(__file__))
cwd = os.getcwd()
assert path_of_this_file.startswith(cwd), "The '%s' script needs to be run from the same folder as/or a parent folder of the script" % os.path.basename(__file__)
rel_path_to_web_page = os.path.relpath(path_of_this_file, cwd)
#print(rel_path_to_web_page)


import http.server
import socketserver
class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """ Subclass to redirect log_message to logger (rather than screen)
    """
    def log_message(self, format, *args):
        logger.info(format % args)

    def do_GET(self):
        # redirect landing page (IP_ADDRESS:PORT or localhost:PORT)
        if self.path == '/':
            self.path = os.path.join('/', rel_path_to_web_page, 'web_page.html')

        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        print("do_POST!!")


def simple_threaded_server(server):
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logger.info("Started simple server at port: %s" % PORT)

def interactive_print(*args, **kwargs):
    clear_line = kwargs.pop('clear_line', False)
    if clear_line:
        _clear_line()
    else:
        # otherwise advance to next line
        print()
    print(" ".join(map(str, args)), **kwargs)

def interactive_mode():  # {
    """
    """

    cas = None

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    ccs = cc_audios + cc_groups
    assert ccs, "No Chromecasts"
    if len(ccs) > 10:
        # TODO: perhaps separate: 0-9 as CCAudios, <SHIFT>0-9 as CCGroups
        logger.warning("More than 10 Chromecast devices, only able to select up to 10")

    # startup server
    handler = MyHTTPRequestHandler
    my_server = socketserver.ThreadingTCPServer(("", PORT), handler)
    simple_threaded_server(my_server)

    digits = [str(i) for i in range(10)]    # ['0', '1', ..., '9']
    cc_selectors = digits[:len(ccs)]

    # show key mappings
    def show_key_mappings():  # {

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

    show_key_mappings()

    # main loop
    with NonBlockingConsole() as nbc:
        while True:  # {
            # display a status leader
            _clear_line()
            if cas:
                device_name = cas.get_name()
                status = "%s: " % (device_name)
                track_info = cas.get_track_info()
                if track_info:
                    artist, title, album, current_time, duration = track_info
                    status += "%s - %s (%s), " % (artist, title, album)
                    status += "%s/%s " % (current_time, duration)

                status += ">"

            else:
                status = "No connected device: >"
            print("%s \r" % status, end='')

            # Throttle the polling loop so python doesn't consume 100% of a core
            # - this reduces CPU to < 1% on Mac
            time.sleep(1/60)

            k = nbc.get_data()  # returns False if no data
            if not k:
                continue

            # quit: q   ##, <ESC>
            #if k == chr(27) or k == 'q':   ## testing for <ESC> also triggered by cursor keys
            if k == 'q':
                my_server.shutdown()
                interactive_print("Quitting")
                break

            # select CC: 0, 1, ...
            if k in cc_selectors:
                cc  = ccs[int(k)]
                cas = CcAudioStreamer(cc)
                print("Selected:", cc.name, "(%s)"%cc.model_name)

            # vol up & down
            elif k == '+' or k == '=':
                if cas:
                    prev, new = cas.vol_up(0.05)
                    interactive_print("Vol: %.2f -> %.2f" % (prev, new), clear_line=True)
            elif k == '-' or k == '_':
                if cas:
                    prev, new = cas.vol_down(0.05)
                    interactive_print("Vol: %.2f -> %.2f" % (prev, new), clear_line=True)

            # toggle pause/resume: <space>
            elif k == ' ':
                if cas:
                    prev, new = cas.toggle_pause()
                    interactive_print(new, clear_line=True)

            # play folder: p
            elif k == 'p':
                if cas:
                    folder = "test_content"     # TODO:
                    posixPath_list = list(pathlib.Path(folder).rglob("*.[mM][pP]3"))
                    filelist = [str(pp) for pp in posixPath_list]
                    random.shuffle(filelist)
                    print("Playing playlist with %d files: [" % len(filelist), end="")
                    max_files_to_print = 3
                    for i in range(min(max_files_to_print, len(filelist))):
                        print("%s, " % os.path.basename(filelist[i]), end="")
                    if len(filelist) > max_files_to_print:
                        print("...]")

                    cas.play_list(filelist)

            # next & prev track
            elif k == '>' or k == '.':
                if cas:
                    cas.next_track()
                    interactive_print("Next track")
            elif k == '<' or k == ',':
                if cas:
                    cas.prev_track()
                    interactive_print("Prev track")

            elif k == '?':
                print("Help")
                show_key_mappings()

            # unused:
            else:
                print('Unmapped key pressed:', k)
        # }
# }


def main(args):  # {
    """
    """

    if len(args.command_args) == 0:
        interactive_mode()

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
            assert len(args.command_args) == 2, "Need to specify folder to play"
            folder = args.command_args[1]

            posixPath_list = list(pathlib.Path(folder).rglob("*.[mM][pP]3"))
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

    parser.add_argument( "command_args", help="[list|status|playfile file|playfolder folder|pause|resume|stop|volup|voldown|setvol v]", nargs="*" )
#   parser.add_argument( "output_folder", help="folder to place test results" )
#   parser.add_argument( '-l', '--list_devices', action="store_true", dest='list_devices',
#                   default=False, help='list CC audio and group devices' )
    parser.add_argument( '-d', '--devicename',
                    help='specify device (default is first audio device' )
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




