import argparse
import logging
import sys
import time
import numpy as np
import pyqtgraph as pg
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes
from PyQt5 import QtWidgets, QtCore, QtGui


class Graph:
    def __init__(self, board_shim):
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self.board_id = board_shim.get_board_id()
        self.board_shim = board_shim
        # 只使用通道1（索引为0）
        self.exg_channels = BoardShim.get_exg_channels(self.board_id)
        if len(self.exg_channels) < 1:
            raise ValueError("No EXG channels found for this board")
            
        self.channel_index = self.exg_channels[0]  # 实际通道索引
        self.sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        self.update_speed_ms = 50
        self.window_size = 10  # 10秒滑动窗口
        self.num_points = self.window_size * self.sampling_rate

        self.app = QtWidgets.QApplication(sys.argv)
        self.win = pg.GraphicsLayoutWidget(title='EEG Channel 1', size=(800, 600))
        self.win.setWindowTitle(f'EEG Channel 1 - Real-time Monitoring | Board ID: {self.board_id}')
        
        # 初始化时间序列图
        self._init_timeseries()
        
        # 初始化定时器
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(self.update_speed_ms)
        
        # 显示窗口
        self.win.show()
        
        # 确保应用程序持续运行
        self.app.exec_()

    def _init_timeseries(self):
        """初始化时间序列图"""
        self.plot = self.win.addPlot(title=f"Channel 1 Raw Data (50Hz Notch Filtered) | Sampling Rate: {self.sampling_rate} Hz")
        
        # 设置坐标轴标签
        self.plot.setLabel('left', 'Amplitude', 'μV')
        self.plot.setLabel('bottom', 'Time', 's')
        
        # 启用网格
        self.plot.showGrid(x=True, y=True)
        
        # 创建曲线对象
        self.curve = self.plot.plot(pen='b')
        
        # 设置X轴范围（0到10秒）
        self.plot.setXRange(0, self.window_size, padding=0)
        
        # 添加状态标签
        self.status_label = pg.TextItem(text="Initializing...", color='r', anchor=(0, 1))
        self.status_label.setPos(0, self.plot.getViewBox().viewRange()[1][0])
        self.plot.addItem(self.status_label)
        
        # 添加数据点计数器
        self.point_counter = pg.TextItem(text="Points: 0", color='g', anchor=(1, 1))
        self.point_counter.setPos(self.window_size, self.plot.getViewBox().viewRange()[1][1])
        self.plot.addItem(self.point_counter)

    def apply_notch_filter(self, data):
        """应用50Hz陷波滤波器去除工频噪声"""
        if len(data) == 0:
            return data
            
        try:
            # 转换为浮点数数组
            data = data.astype(np.float64)
            
            # 使用带阻滤波器去除50Hz工频干扰
            # 使用48-52Hz的带阻范围
            DataFilter.perform_bandstop(data, self.sampling_rate, 48.0, 52.0, 4, 
                                       FilterTypes.BUTTERWORTH_ZERO_PHASE, 0)
            return data
        except Exception as e:
            self.status_label.setText(f"Filter Error: {str(e)}")
            logging.error(f"Filter error: {str(e)}")
            return data

    def update(self):
        """更新图表数据"""
        try:
            # 获取当前数据缓冲区中的数据量
            data_count = self.board_shim.get_board_data_count()
            self.point_counter.setText(f"Points: {data_count}")
            
            # 如果数据量不足，等待更多数据
            if data_count < self.num_points:
                self.status_label.setText(f"Buffering... ({data_count}/{self.num_points} points)")
                return
                
            # 获取最新数据
            data = self.board_shim.get_current_board_data(self.num_points)
            
            if data.shape[1] > 0:
                # 获取通道1的数据
                channel_data = data[self.channel_index]
                
                # 确保数据长度正确
                if len(channel_data) != self.num_points:
                    self.status_label.setText(f"Data length mismatch: {len(channel_data)} vs {self.num_points}")
                    return
                
                # 应用50Hz陷波滤波器去除工频噪声
                filtered_data = self.apply_notch_filter(channel_data.copy())
                
                # 创建时间轴（从0到10秒）
                time_axis = np.linspace(0, self.window_size, len(filtered_data))
                
                # 更新曲线数据
                self.curve.setData(time_axis, filtered_data)
                
                # 自动调整Y轴范围以适应数据
                min_val = np.min(filtered_data) - 50
                max_val = np.max(filtered_data) + 50
                self.plot.setYRange(min_val, max_val, padding=0.1)
                
                # 更新状态
                self.status_label.setText(f"Data OK | Min: {min_val:.1f}μV, Max: {max_val:.1f}μV")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            logging.error(f"Update error: {str(e)}", exc_info=True)

        QtCore.QCoreApplication.processEvents()


def main():
    BoardShim.enable_dev_board_logger()
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser()
    # 参数设置保持不变
    parser.add_argument('--timeout', type=int, help='timeout for device discovery or connection', required=False,
                        default=0)
    parser.add_argument('--ip-port', type=int, help='ip port', required=False, default=3)
    parser.add_argument('--ip-protocol', type=int, help='ip protocol, check IpProtocolType enum', required=False,
                        default=0)
    parser.add_argument('--ip-address', type=str, help='ip address', required=False, default='192.168.4.1')
    parser.add_argument('--serial-port', type=str, help='serial port', required=False, default='COM6')
    parser.add_argument('--mac-address', type=str, help='mac address', required=False, default='')
    parser.add_argument('--other-info', type=str, help='other info', required=False, default='')
    parser.add_argument('--streamer-params', type=str, help='streamer params', required=False, default='')
    parser.add_argument('--serial-number', type=str, help='serial number', required=False, default='')
    parser.add_argument('--board-id', type=int, help='board id, check docs to get a list of supported boards',
                        required=False, default=BoardIds.CYTON_DAISY_BOARD)
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
        logging.info("Preparing session...")
        board_shim.prepare_session()
        logging.info("Session prepared. Starting stream...")
        
        # 增加缓冲区大小
        buffer_size = 450000 * 2  # 双倍缓冲区大小
        board_shim.start_stream(buffer_size, args.streamer_params)
        
        logging.info("Stream started. Waiting for data buffer to fill...")
        
        # 等待缓冲区填充
        start_time = time.time()
        while board_shim.get_board_data_count() < 100 and (time.time() - start_time) < 10:
            time.sleep(0.1)
            logging.info(f"Waiting for data... Current count: {board_shim.get_board_data_count()}")
        
        data_count = board_shim.get_board_data_count()
        if data_count > 0:
            logging.info(f"Data buffer filled with {data_count} points. Creating graph window...")
            graph = Graph(board_shim)  # 保持对Graph对象的引用
        else:
            logging.error("No data received after 10 seconds. Check device connection.")
            QtWidgets.QMessageBox.critical(None, "Error", "No data received from device. Check connection and parameters.")
    except BaseException as e:
        logging.error(f'Exception: {str(e)}', exc_info=True)
        QtWidgets.QMessageBox.critical(None, "Error", f"An error occurred: {str(e)}")
    finally:
        if board_shim.is_prepared():
            logging.info('Releasing session')
            board_shim.release_session()


if __name__ == '__main__':
    main()