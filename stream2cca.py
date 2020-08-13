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
import pychromecast as pycc     # req's 7.1.1:  pip install PyChromecast
import random
import socket
import time
import urllib


# configure logging

logging.basicConfig(
        #level=os.environ.get("LOGLEVEL", logging.INFO),
        format='%(asctime)s.%(msecs)03d:%(levelname)s:%(name)s: %(message)s',
        datefmt='%m/%d %H:%M:%S',
        )
logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOGLEVEL", logging.INFO))


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

def clear_line():
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
            server='http://' + IP_ADDRESS + ':8000/',
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
        if self.state == 'PLAYING':
            self.pause()
        elif self.state == 'PAUSED':
            self.resume()

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

    def vol_down(self, step=0.1):
        """
        """
        cur_vol = self.cc.status.volume_level
        new_vol = max(cur_vol - step, 0)
        logger.info("VolDown: Adjusting volume from %.2f -> %.2f" % (cur_vol, new_vol))
        self.cc.set_volume(new_vol)

    def set_vol(self, new_vol):
        """
        """
        new_vol = float(new_vol)
        logger.info("SetVol: Setting volume to %.2f" % (new_vol))
        self.cc.set_volume(new_vol)

    def monitor_status(self):
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
            if self.state != prev_state:
                clear_line()
                addtl_info = ": " + track_info if self.state == 'PLAYING' else ""
                logger.info("State change -> %s%s" % (self.state, addtl_info))
                prev_state = self.state
            if self.state == 'PLAYING':
                print("%s %s/%s \r" % (
                    track_info,
                    to_min_sec(self.mc.status.current_time),
                    to_min_sec(self.mc.status.duration)), end='')

            time.sleep(0.5)

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


def interactive_mode():  # {
    """
    NOTE: initially tried using pynput, but had these issues:
      - pynput does not work on RPI over SSH -- presumably problem is trying to run over SSH
        - just trying to `import pynput` results in error
      - pynput run locally on Mac grabs ALL keypresses, even those intended for different window/app
    """

    cas = None

    cc_audios, cc_groups = CcAudioStreamer.get_devices()
    ccs = cc_audios + cc_groups
    assert ccs, "No Chromecasts"
    if len(ccs) > 10:
        # TODO: perhaps separate: 0-9 as CCAudios, <SHIFT>0-9 as CCGroups
        logger.warn("More than 10 Chromecast devices, only able to select up to 10")

    digits = [str(i) for i in range(10)]    # ['0', '1', ..., '9']
    cc_selectors = digits[:len(ccs)]

    # display key mappings
    print("-"*66)
    for i, cc in zip(cc_selectors, ccs):
        print(i, "=", cc.name, "(%s)" % cc.model_name)
    print("+ = volume up")
    print("- = volume down")
    print("p = playfolder")
    print("<SPACE> = pause/resume")
    print("> = next track")
    print("< = previous track")
    print("q = quit")
    print("-"*66)

    # main loop
    with NonBlockingConsole() as nbc:
        while True:  # {
            # Throttle the polling loop so python doesn't consume 100% of a core
            # - this reduces CPU to < 1% on Mac
            time.sleep(1/60)

            k = nbc.get_data()  # returns False if no data
            if not k:
                continue

            # quit: q, <ESC>
            if k == '' or k == 'q':
                break

            # select CC: 0, 1, ...
            if k in cc_selectors:
                cc  = ccs[int(k)]
                cas = CcAudioStreamer(cc)
                print("selected:", cc.name, "(%s)"%cc.model_name)

            # vol up & down
            elif k == '+':
                if cas:
                    cas.vol_up(0.05)
            elif k == '-':
                if cas:
                    cas.vol_down(0.05)

            # toggle pause/resume: <space>
            elif k == ' ':
                if cas:
                    cas.toggle_pause()

            # play folder: p
            elif k == 'p':
                if cas:
                    folder = "test_content"     # TODO:
                    posixPath_list = list(pathlib.Path(folder).rglob("*.[mM][pP]3"))
                    filelist = [str(pp) for pp in posixPath_list]
                    random.shuffle(filelist)
                    print("Playing playlist with %d files:" % len(filelist), filelist)
                    cas.play_list(filelist)

            # next & prev track
            elif k == '>' or k == '.':
                if cas:
                    cas.next_track()
            elif k == '<' or k == ',':
                if cas:
                    cas.prev_track()

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



"""

# file must be served...
# see: https://rinzewind.org/blog-en/2018/how-to-send-local-files-to-chromecast-with-python.html
# basically start simple http server from folder with the files:
#    python3 -m http.server
# can do this on the pi4...

"""

