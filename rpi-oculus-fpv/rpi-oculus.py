#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2015, Florent Thiery 

import logging
logger = logging.getLogger('FpvPipeline')

import gi
gi.require_version('Gst', '1.0')

from gi.repository import GObject, Gst

#source = "v4l2src ! video/x-raw, format=(string)YUY2, width=(int)640, height=(int)360"
source = 'videotestsrc ! video/x-raw, format=(string)YUY2, width=(int)720, height=(int)480'

display = 'tee name=src ! queue name=qtimeoverlay ! timeoverlay name=timeoverlay font-desc="Arial 30" silent=true ! glupload ! glcolorconvert ! glcolorscale ! videorate ! video/x-raw(memory:GLMemory), width=(int)1280, height=(int)800, pixel-aspect-ratio=(fraction)1/1, interlace-mode=(string)progressive, framerate=(fraction)60/1, format=(string)RGBA ! gltransformation name=gltransformation ! glshader location=oculus.frag ! glimagesink name=glimagesink'

encoder = 'src. ! queue ! videoconvert ! x264enc tune=zerolatency speed-preset=1 bitrate=4000 ! mp4mux ! filesink location=test.mp4'

def init():
    GObject.threads_init()
    Gst.init(None)
    Gst.debug_set_active(True)
    Gst.debug_set_colored(True)
    Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)

init()

settings = {
    'headtracker_enable': True,
}

class FpvPipeline:
    def __init__(self):
        self.actions_after_eos = list()
        self.record = False

    def toggle_record(self):
        self.record = not self.record
        logger.info('Toggling record to state %s' %self.record)
        self.start()

    def start(self):
        if self.is_running():
            self.add_action_after_eos(self.start)
            self.stop()
            return
        logger.info("Record: %s" %self.record)
        pipeline_desc = self.get_pipeline(self.record)
        logger.debug("Running %s" %pipeline_desc)
        self.pipeline = self.parse_pipeline(pipeline_desc)
        if self.record:
            self.set_record_overlay()
        self.activate_bus()
        if settings.get('headtracker_enable', False):
            self.activate_frame_callback()
        self.pipeline.set_state(Gst.State.PLAYING)

    def set_record_overlay(self):
        o = self.pipeline.get_by_name('timeoverlay')
        o.set_property('text', 'Rec')
        o.set_property('silent', False)

    def is_running(self):
        if not hasattr(self, 'pipeline'):
            return False
        return self.pipeline.get_state(Gst.CLOCK_TIME_NONE)[1] == Gst.State.PLAYING

    def stop(self):
        self.send_eos()

    def get_pipeline(self, record=False):
        elts = [source, display]
        p = ' ! '.join(elts)
        if record:
            p = "%s %s" %(p, encoder)
        return p

    def parse_pipeline(self, pipeline):
        return Gst.parse_launch(pipeline)

    def send_eos(self, *args):
        logger.info("Sending EOS")
        event = Gst.Event.new_eos()
        Gst.Element.send_event(self.pipeline, event)

    def on_eos(self):
        logger.info("Got EOS")
        self.pipeline.set_state(Gst.State.NULL)
        self.run_actions_after_eos()

    def run_actions_after_eos(self):
        for action in self.actions_after_eos:
            logger.debug('Calling %s' %action)
            action()

    def add_action_after_eos(self, action):
        if callable(action):
            self.actions_after_eos.append(action)
        else:
            logger.error('Action %s not callable' %action)

    def activate_bus(self):
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message', self._on_message)

    def activate_frame_callback(self):
        sink = self.pipeline.get_by_name('glimagesink')
        sink.connect("client-draw", self._on_draw)

    def _on_draw(self, src, glcontext, sample, *args):
        print('Frame')

    def _on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            error_string = "{0} {1}".format(err, debug)
            logger.info("Error: {0}".format(error_string))
        elif t == Gst.MessageType.EOS:
            self.on_eos()
        elif t == Gst.MessageType.ELEMENT:
            name = message.get_structure().get_name()
            res = message.get_structure()
            source = message.src.get_name()  # (str(message.src)).split(":")[2].split(" ")[0]
            #self.launch_event(name, {"source": source, "data": res})
            #self.launch_event('gst_element_message', {"source": source, "name": name, "data": res})
        else:
            logger.debug("got unhandled message type {0}, structure {1}".format(t, message))

if __name__ == '__main__':

    import logging
    import sys
    import signal


    logging.basicConfig(
        level=getattr(logging, "DEBUG"),
        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        stream=sys.stderr
    )

    f = FpvPipeline()
    GObject.idle_add(f.start)
    #GObject.timeout_add_seconds(10, f.toggle_record)
    #GObject.timeout_add_seconds(20, f.toggle_record)
    ml = GObject.MainLoop()

    def signal_handler(signal, frame):
        print('You pressed Ctrl+C!')
        f.add_action_after_eos(sys.exit)
        f.stop()
    GObject.idle_add(signal.signal, signal.SIGINT, signal_handler)

    ml.run()
