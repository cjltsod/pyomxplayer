import re
from threading import Thread
from time import sleep

import pexpect

from pyomxplayer.parser import OMXPlayerParser


class OMXPlayer(object):
    _STATUS_REGEX = re.compile(b'M:\s*([\d.]+).*')
    _DONE_REGEX = re.compile(b'have a nice day.*')
    _DURATION_REGEX = re.compile(b'Duration: (.+?):(.+?):(.+?),')
    _TITLE_REGEX = re.compile(b'title           : (.+?)\r\n')

    _LAUNCH_CMD      = 'omxplayer -s "%s" %s'
    _INFO_CMD    = 'omxplayer -i %s'
    _PAUSE_CMD       = 'p'
    _TOGGLE_SUB_CMD  = 's'
    _INC_SPEED_CMD   = '1'
    _DEC_SPEED_CMD   = '2'
    _PREV_AUDIO_CMD  = 'j'
    _NEXT_AUDIO_CMD  = 'k'
    _PREV_SUB_CMD    = 'n'
    _NEXT_SUB_CMD    = 'm'
    _QUIT_CMD        = 'q'
    _PREVIOUS_CMD    = 'i'
    _NEXT_CMD        = 'o'
    _DECREASE_VOLUME = '-'
    _INCREASE_VOLUME = '+'
    _BACK_30_CMD     = '\x1b[D'  # left
    _BACK_600_CMD    = '\x1b[B'  # down
    _FORWARD_30_CMD  = '\x1b[C'  # right
    _FORWARD_600_CMD = '\x1b[A'  # up

    def __init__(self, media_file, args=None, start_playback=False,
                 _parser=OMXPlayerParser, _spawn=pexpect.spawn, stop_callback=None):
        self.subtitles_visible = True
        self.muted = False
        self.media_file = media_file
        self.info_output_buffer = False

        # volume in db
        self.current_volume = 0
        self._spawn = _spawn
        self._launch_omxplayer(media_file, args)
        self.parser = _parser(self._process)
        self.duration = self._get_duration()
        self.title = self._get_title()
        self._info_process.terminate()
        self._monitor_play_position()
        self._stop_callback = stop_callback
        self.audio = self.parser.audio
        self.video = self.parser.video
        self.info_output_buffer = None

        # By default the process starts playing
        self.paused = False
        if not start_playback:
            self.toggle_pause()
        self.toggle_subtitles()

    def _launch_omxplayer(self, media_file, args):
        if not args:
            args = ''
        cmd = self._LAUNCH_CMD % (media_file, args)
        self._process = self._spawn(cmd)
        info_cmd = self._INFO_CMD % (media_file)
        self._info_process = self._spawn(info_cmd)

    def _monitor_play_position(self):
        self._position_thread = Thread(target=self._get_position)
        self._position_thread.start()

    def _get_info_buffer(self):
        self.info_output_buffer = self._info_process.read()

    def _get_title(self):
        if not self.info_output_buffer:
            self._get_info_buffer()
        matches = self._TITLE_REGEX.search(self.info_output_buffer)
        if matches:
            title_info = matches.groups()
            return title_info[0]
        else:
            return 'No title'

    def _get_duration(self):
        if not self.info_output_buffer:
            self._get_info_buffer()
        matches = self._DURATION_REGEX.search(self.info_output_buffer)
        if matches:
            duration_info = matches.groups()
            hours = int(re.sub(b'\x1b.*?m', '', duration_info[0]))
            minutes = int(re.sub(b'\x1b.*?m', '', duration_info[1]))
            seconds = float(re.sub(b'\x1b.*?m', '', duration_info[2]))
            return float(hours*60*60 + minutes*60 + seconds)
        else:
            return 0

    def _get_position(self):
        while True:
            index = self._process.expect([self._STATUS_REGEX,
                                          pexpect.TIMEOUT,
                                          pexpect.EOF,
                                          self._DONE_REGEX])

            def timed_out():
                return index == 1

            def process_finished():
                return index in (2, 3)

            if timed_out():
                continue
            elif process_finished():
                if index == 3 and hasattr(self._stop_callback, '__call__'):
                    self._stop_callback()
                break
            else:
                # Process is still running (happy path)
                self.position = float(self._process.match.group(1)) / 1000000
            sleep(0.05)

    def is_running(self):
        return self._process.isalive()

    def toggle_pause(self):
        if self._process.send(self._PAUSE_CMD):
            self.paused = not self.paused

    def toggle_subtitles(self):
        if self._process.send(self._TOGGLE_SUB_CMD):
            self.subtitles_visible = not self.subtitles_visible

    def stop(self):
        self._process.send(self._QUIT_CMD)
        self._process.terminate(force=True)

    def inc_speed(self):
        self._process.send(self._INC_SPEED_CMD)

    def dec_speed(self):
        self._process.send(self._DEC_SPEED_CMD)

    def inc_vol(self):
        self._process.send(self._INCREASE_VOLUME)
        # omxplayer walks by 3db
        self.current_volume += 3

    def dec_vol(self):
        self._process.send(self._DECREASE_VOLUME)
        # omxplayer walks by 3db
        self.current_volume -= 3

    def set_vol(self, vol):
        while vol < self.current_volume:
            self.dec_vol()
        if vol > self.current_volume:
            self.inc_vol()

    def toggle_mute(self, rate=0):
        if not self.muted:
            while self.current_volume > -75:
                self.dec_vol()
                sleep(rate)
            self.muted = True
        else:
            for i in range(0, 25):
                self.inc_vol()
                sleep(rate)
        self.muted = False

    def prev_audio(self):
        self._process.send(self._PREV_AUDIO_CMD)

    def next_audio(self):
        self._process.send(self._NEXT_AUDIO_CMD)

    def prev_sub(self):
        self._process.send(self._PREV_SUB_CMD)

    def next_sub(self):
        self._process.send(self._NEXT_SUB_CMD)

    def previous_chapter(self):
        self._process.send(self._PREVIOUS_CMD)

    def next_chapter(self):
        self._process.send(self._NEXT_CMD)

    def back_30(self):
        self._process.send(self._BACK_30_CMD)

    def back_600(self):
        self._process.send(self._BACK_600_CMD)

    def forward_30(self):
        self._process.send(self._FORWARD_30_CMD)

    def forward_600(self):
        self._process.send(self._FORWARD_600_CMD)
