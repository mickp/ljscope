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
            self.device.streamStop()
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


    def config(self, gainIndex, frequency):
        self.device.streamConfig(NumChannels=len(self.channels),
                                 ChannelNumbers=self.channels,
                                 ChannelOptions=len(self.channels)*[DIFFERENTIAL | gainIndex],
                                 SampleFrequency=frequency
                                )


    def start(self):
        self.device.streamStart()


    def stop(self):
        self.device.streamStop()


    def fetch(self, channel, numpnts):
        data = []

        d_iter = self.device.streamData()
        #while len(data) < numpnts:
        #    r = d_iter.next()
        #    if r['missed'] == 0:
        #        data.extend(r['AIN' + str(channel)])
        for r in d_iter:
            if r['missed'] != 0:
                if len(data) == 0:
                    continue
                else:
                    data.extend((numpnts - len(data)) * [0])
            else:
                data.extend(r['AIN' + str(channel)])
            if len(data) >= numpnts:
                break
        return data


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
            dc.SetPen(wx.Pen(wx.BLACK, 1))
            dc.DrawLine(0, self.h / 2, self.w, self.h / 2)
            dc.DrawLine(self.w / 2, 0, self.w / 2, self.h)

            dc.SetPen(wx.Pen(wx.RED, 3))
            #d = self.data[0]
            d = self.data

            y_mean = numpy.mean(d)
            y_range = float(max(d) - min(d))
            x_range = float(len(d))

            x_scale = self.w / x_range
            y_scale = self.h / y_range

            for x, y in enumerate(d):
                #dc.DrawPoint(x * x_scale,  y_scale * (0.5 * y_range + y - y_mean) )
                #dc.DrawCheckMark(x * x_scale,  y_scale * (0.5 * y_range + y - y_mean), 12, 12)
                #dc.CrossHair(x * x_scale,  y_scale * (0.5 * y_range + y - y_mean) )
                dc.DrawCircle(x * x_scale,  y_scale * (0.5 * y_range + y - y_mean), 1)

            dc.DrawText('RMS %f\n%f to %f' % (y_mean, min(d), max(d)), 12, 12)



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
            lj.config(0, 50000/2)
            lj.start()
            while not self.shouldExit:
                #lj.acquire(0, 50000, 0.01)
                self.scope.data = lj.fetch(0, 5000)
                wx.PostEvent(self.scope, wx.ThreadEvent())
            lj.stop()
        print ' ... data_thread exiting.'



app = wx.App(False)  # Create a new app, don't redirect stdout/stderr to a window.
frame = LJFrame(None, "LabJack scope") # A Frame is a top-level window.
frame.Show(True)     # Show the frame.
app.MainLoop()