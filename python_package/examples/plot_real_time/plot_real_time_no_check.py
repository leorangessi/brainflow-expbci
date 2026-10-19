import argparse
import logging
import time
import serial
import numpy as np
import pyqtgraph as pg
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from pyqtgraph.Qt import QtWidgets, QtCore


class CustomBoard:
    def __init__(self, serial_port, baudrate=9600):
        # 直接使用PySerial连接串口，跳过BrainFlow的欢迎字符检测
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.ser = None
        self.is_connected = False
        self.is_streaming = False
        
        # 模拟BrainFlow的通道配置
        self.exg_channels = [0, 1, 2, 3, 4, 5, 6, 7]  # 假设有8个EEG通道
        self.sampling_rate = 250  # 假设采样率为250Hz
        self.data_buffer = []
        
    def connect(self):
        try:
            # 直接打开串口
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baudrate,
                timeout=0.1
            )
            
            if self.ser.is_open:
                self.is_connected = True
                logging.info(f"成功连接到串口: {self.serial_port}")
                # 清除缓冲区
                self.ser.flushInput()
                self.ser.flushOutput()
                return True
            else:
                logging.error(f"无法打开串口: {self.serial_port}")
                return False
        except Exception as e:
            logging.error(f"连接串口时出错: {str(e)}")
            return False
    
    def start_stream(self):
        if not self.is_connected:
            logging.error("未连接到设备，无法开始数据流")
            return False
        
        try:
            # 发送开始数据流的命令（根据用户的描述，应该是'b'命令）
            self.ser.write(b'b')
            self.is_streaming = True
            logging.info("已发送开始数据流命令")
            return True
        except Exception as e:
            logging.error(f"开始数据流时出错: {str(e)}")
            return False
    
    def stop_stream(self):
        if not self.is_connected:
            return
        
        try:
            # 发送停止数据流的命令
            self.ser.write(b's')
            self.is_streaming = False
            logging.info("已发送停止数据流命令")
        except Exception as e:
            logging.error(f"停止数据流时出错: {str(e)}")
    
    def get_data(self, num_samples=250):
        """获取指定数量的样本数据"""
        if not self.is_connected or not self.is_streaming:
            return np.array([])
        
        try:
            # 这里简化处理，实际应该根据设备的数据格式进行解析
            # 假设每个样本是4字节的浮点数
            bytes_needed = num_samples * 4
            data = self.ser.read(bytes_needed)
            
            if len(data) >= bytes_needed:
                # 解析数据
                samples = np.frombuffer(data, dtype=np.float32)
                self.data_buffer.extend(samples.tolist())
                
                # 只保留最新的一定数量的样本
                if len(self.data_buffer) > 10000:  # 保留10000个样本
                    self.data_buffer = self.data_buffer[-10000:]
                
                return samples
            return np.array([])
        except Exception as e:
            logging.error(f"读取数据时出错: {str(e)}")
            return np.array([])
    
    def release(self):
        if self.ser and self.ser.is_open:
            self.stop_stream()
            self.ser.close()
            self.is_connected = False
            logging.info("已关闭串口连接")


class Graph:
    def __init__(self, board):
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        self.board = board
        self.exg_channels = board.exg_channels
        self.sampling_rate = board.sampling_rate
        self.update_speed_ms = 50
        self.window_size = 10  # 10 seconds
        self.num_points = self.window_size * self.sampling_rate

        self.app = QtWidgets.QApplication([])
        self.win = pg.GraphicsLayoutWidget(title='自定义脑电数据实时绘图', size=(800, 600), show=True)

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
        # 为每个通道创建一个图表
        self.plots = list()
        self.curves = list()
        
        # 只创建第一个通道的图表
        if len(self.exg_channels) > 0:
            self.plot = self.win.addPlot(row=0, col=0)
            self.plot.setTitle(f'通道 {self.exg_channels[0] + 1} 原始脑电数据')
            self.plot.setLabel('left', '电压', units='μV')
            self.plot.setLabel('bottom', '时间', units='s')
            self.plot.showGrid(x=True, y=True)
            self.curve = self.plot.plot(pen=self.pens[0])

    def update(self):
        # 获取最新数据
        new_data = self.board.get_data(100)  # 每次获取100个样本
        
        if len(new_data) > 0:
            # 使用第一个通道的数据
            channel_data = new_data
            
            # 创建时间轴
            time_axis = np.linspace(0, self.window_size, len(channel_data))
            
            # 绘制数据
            self.curve.setData(time_axis, channel_data.tolist())
            
            # 调整坐标轴范围
            self.plot.setXRange(0, self.window_size)
            if len(channel_data) > 0:
                min_val = np.min(channel_data)
                max_val = np.max(channel_data)
                if max_val > min_val:  # 避免除零错误
                    margin = (max_val - min_val) * 0.1  # 10%的边距
                    self.plot.setYRange(min_val - margin, max_val + margin)

        self.app.processEvents()


def main():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('--serial-port', type=str, help='串口名称', required=True)
    parser.add_argument('--baudrate', type=int, help='波特率', required=False, default=9600)
    args = parser.parse_args()

    # 创建自定义板子实例
    board = CustomBoard(args.serial_port, args.baudrate)
    
    try:
        # 连接设备
        if not board.connect():
            logging.error("无法连接到设备，程序退出")
            return
        
        # 等待设备初始化
        time.sleep(1)
        
        # 开始数据流
        if not board.start_stream():
            logging.error("无法开始数据流，程序退出")
            return
        
        # 运行绘图程序
        Graph(board)
        
    except Exception as e:
        logging.warning('发生异常', exc_info=True)
    finally:
        # 释放资源
        board.release()


if __name__ == '__main__':
    main()