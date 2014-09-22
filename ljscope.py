from collections import namedtuple
from datetime import datetime
import numpy
import threading
import u6
import wx

#channels to acquire
CHANNELS=[0]#[0,2]#[0,1,2] #[0,1,4]
DIFFERENTIAL = 1<<7
MAX_TIME = 12

StartStopDt = namedtuple('StartStopDt', ['start', 'stop', 'dt'])

class CaptureDevice():
    def __init__(self):
        self.channels = CHANNELS
        self.data = None
        self.device = None
        self.missed = None
        self.timing = None

    def __enter__(self):
        self.connect()
        try:
            self.streamStop()
        except:
            pass
        return self


    def __exit__(self, type, value, traceback):
        self.close()


    def connect(self):
        self.device = u6.U6()
        self.device.getCalibrationData()


    def close(self):
        self.device.close()


    def acquire(self, gainIndex, frequency, timeout=MAX_TIME):
        self.device.streamConfig(NumChannels=len(self.channels),
                                 ChannelNumbers=self.channels,
                                 ChannelOptions=len(self.channels)*[DIFFERENTIAL | gainIndex],
                                 SampleFrequency=frequency
                                )
        self.missed = 0
        dataIn = []
        self.data = {channel: [] for channel in CHANNELS}

        start = datetime.now()
        self.device.streamStart()
        for r in self.device.streamData():
            if r is not None:
                # stop condition
                if (datetime.now() - start).seconds >= timeout:
                    break
                # check for errors
                if r['errors'] != 0:
                    pass
                # check for underflow
                if r['numPackets'] != self.device.packetsPerRequest:
                    pass
                # check for missed packets
                if r['missed'] != 0:
                    self.missed += r['missed']

                dataIn.append(r)

        self.device.streamStop()
        stop = datetime.now()

        total = len(dataIn) * self.device.packetsPerRequest * self.device.streamSamplesPerPacket
        total -= self.missed
        runTime = (stop - start).seconds + float((stop - start).microseconds)/1000000

        try:
            dt = runTime/float(total)
        except:
            dt = None

        self.timing = StartStopDt(start, stop, dt)

        for result in dataIn:
            for channel in CHANNELS:
                self.data[channel].extend(result['AIN' + str(channel)])



class LJScope (wx.Panel):
    def __init__(self, parent):
        super(LJScope, self).__init__(parent)
        self.parent = parent
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_THREAD, self.on_thread)
        self.data = None
        self.w = None
        self.h = None


    def on_thread(self, event):
        self.Refresh()


    def on_size(self, event):
        event.Skip()
        self.w, self.h = self.GetSize()
        self.Refresh()
    

    def on_paint(self, event):
        w, h = self.GetClientSize()
        dc = wx.AutoBufferedPaintDC(self)
        
        if self.data:
            dc.Clear()
            d = self.data[0]

            y_mean = numpy.mean(d)
            y_range = max(d) - min(d)
            x_range = len(d)

            x_scale = x_range / self.w
            y_scale = y_range / self.h

            for x, y in enumerate(d):
                dc.DrawPoint(x * x_scale, y_scale * (y - y_mean) + (y_scale / 2))
            



class LJFrame (wx.Frame):
    def __init__(self, parent, title):
        wx.Frame.__init__(self, parent, title=title, size=(512, 256))
        self.scope = LJScope(self)
        self.shouldExit = False
        
        self.data_thread = threading.Thread(target=self.generate_data)
        self.data_thread.start()
        self.Bind(wx.EVT_CLOSE, self.on_close)


    def on_close(self, event):
        print 'Stopping data_thread ...'
        self.shouldExit = True
        self.data_thread.join()
        super(LJFrame, self).Destroy()


    def generate_data(self):
        with CaptureDevice() as lj:
            print lj
            while not self.shouldExit:
                lj.acquire(0, 50000, 0.01)
                self.scope.data = lj.data
                wx.PostEvent(self.scope, wx.ThreadEvent())
        print ' ... data_thread exiting.'





app = wx.App(False)  # Create a new app, don't redirect stdout/stderr to a window.
frame = LJFrame(None, "LabJack scope") # A Frame is a top-level window.
frame.Show(True)     # Show the frame.
app.MainLoop()