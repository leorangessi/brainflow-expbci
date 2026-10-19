import argparse
import logging

import pyqtgraph as pg
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from pyqtgraph.Qt import QtWidgets, QtCore


class Graph:
    def __init__(self, board_shim):
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self.board_id = board_shim.get_board_id()
        self.board_shim = board_shim
        self.exg_channels = BoardShim.get_exg_channels(self.board_id)
        self.sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        self.update_speed_ms = 50
        self.window_size = 10  # 10 seconds
        self.num_points = self.window_size * self.sampling_rate

        self.app = QtWidgets.QApplication([])
        self.win = pg.GraphicsLayoutWidget(title='BrainFlow Plot - Channel 1 Raw Data', size=(800, 600), show=True)

        self._init_pens()
        self._init_timeseries()

        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        timer.start(self.update_speed_ms)
        QtWidgets.QApplication.instance().exec()

    def _init_pens(self):
        self.pens = list()
        self.brushes = list()
        colors = ['#A54E4E', '#A473B6', '#5B45A4', '#2079D2', '#32B798', '#2FA537', '#9DA52F', '#A57E2F', '#A53B2F']
        for i in range(len(colors)):
            pen = pg.mkPen({'color': colors[i], 'width': 2})
            self.pens.append(pen)
            brush = pg.mkBrush(colors[i])
            self.brushes.append(brush)

    def _init_timeseries(self):
        # Only create one plot for channel 1
        self.plot = self.win.addPlot(row=0, col=0)
        self.plot.setTitle('Channel 1 Raw EEG Data')
        self.plot.setLabel('left', 'Voltage', units='μV')
        self.plot.setLabel('bottom', 'Time', units='s')
        self.plot.showGrid(x=True, y=True)
        self.curve = self.plot.plot(pen=self.pens[0])

    def update(self):
        # Get all available data
        data = self.board_shim.get_current_board_data(self.num_points)
        
        if len(self.exg_channels) > 0 and data.shape[1] > 0:
            # Get channel 1 data
            channel_data = data[self.exg_channels[0]]
            
            # Only use the latest 10 seconds of data
            if len(channel_data) > self.num_points:
                # Take only the last num_points samples
                channel_data = channel_data[-self.num_points:]
            
            # Create time axis for exactly 10 seconds (0 to 10)
            time_axis = np.linspace(0, self.window_size, len(channel_data))
            
            # Plot the data
            self.curve.setData(time_axis, channel_data.tolist())
            
            # Force the x-axis to show exactly 0 to 10 seconds
            self.plot.setXRange(0, self.window_size)
            
            # Auto-scale y-axis to fit the data
            if len(channel_data) > 0:
                min_val = np.min(channel_data)
                max_val = np.max(channel_data)
                if max_val > min_val:  # Avoid division by zero
                    margin = (max_val - min_val) * 0.1  # 10% margin
                    self.plot.setYRange(min_val - margin, max_val + margin)

        self.app.processEvents()


def main():
    BoardShim.enable_dev_board_logger()
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    # use docs to check which parameters are required for specific board, e.g. for Cyton - set serial port
    parser.add_argument('--timeout', type=int, help='timeout for device discovery or connection', required=False,
                        default=0)
    parser.add_argument('--ip-port', type=int, help='ip port', required=False, default=3)
    parser.add_argument('--ip-protocol', type=int, help='ip protocol, check IpProtocolType enum', required=False,
                        default=0)
    parser.add_argument('--ip-address', type=str, help='ip address', required=False, default='192.168.4.1')
    parser.add_argument('--serial-port', type=str, help='serial port', required=False, default='')
    parser.add_argument('--mac-address', type=str, help='mac address', required=False, default='')
    parser.add_argument('--other-info', type=str, help='other info', required=False, default='')
    parser.add_argument('--streamer-params', type=str, help='streamer params', required=False, default='')
    parser.add_argument('--serial-number', type=str, help='serial number', required=False, default='')
    parser.add_argument('--board-id', type=int, help='board id, check docs to get a list of supported boards',
                        required=False, default=BoardIds.CYTON_BOARD)#EXPANDABLE_EEG_32_WIFI_BOARD
    parser.add_argument('--file', type=str, help='file', required=False, default='')
    parser.add_argument('--master-board', type=int, help='master board id for streaming and playback boards',
                        required=False, default=BoardIds.NO_BOARD)
    args = parser.parse_args()

    params = BrainFlowInputParams()
    params.ip_port = args.ip_port
    params.serial_port = args.serial_port
    params.mac_address = args.mac_address
    params.other_info = args.other_info
    params.serial_number = args.serial_number
    params.ip_address = args.ip_address
    params.ip_protocol = args.ip_protocol
    params.timeout = args.timeout
    params.file = args.file
    params.master_board = args.master_board

    board_shim = BoardShim(args.board_id, params)
    try:
        board_shim.prepare_session()
        board_shim.start_stream(450000, args.streamer_params)
        Graph(board_shim)
    except BaseException:
        logging.warning('Exception', exc_info=True)
    finally:
        if board_shim.is_prepared():
            logging.info('Releasing session')
            board_shim.release_session()


if __name__ == '__main__':
    main()
