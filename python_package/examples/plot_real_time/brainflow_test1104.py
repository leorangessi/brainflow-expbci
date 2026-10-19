from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from pylsl import StreamInfo, StreamOutlet, local_clock 
import time

# 设置Brainflow连接参数
params = BrainFlowInputParams()
params.ip_address = "192.168.4.1"  # 修改为你的WiFi板IP地址
params.ip_port = 3  # 默认端口，可以根据需要调整
params.board_id = BoardIds.CYTON_WIFI_BOARD.value
# 创建LSL流
# info_eeg = StreamInfo('OpenBCI_EEG', 'EEG', 8, 250, 'float32', 'myuid34234')
# outlet_eeg = StreamOutlet(info_eeg)

# 如果需要加速度数据，添加一个流
# info_accel = StreamInfo('OpenBCI_Accel', 'Accelerometer', 3, 250, 'float32', 'accel34234')
# outlet_accel = StreamOutlet(info_accel)
# 启动Cyton WiFi数据流
board = BoardShim(params.board_id, params)
board.prepare_session()
board.start_stream()

try:
    while True:
        # 获取采集的数据
        data = board.get_board_data()

        # 将EEG数据发送到LSL
        eeg_data = data[0:8]  # OpenBCI Cyton有8个EEG通道  
        print(eeg_data)
        # 发送数据到LSL  
        timestamp = local_clock()  
        # outlet_eeg.push_chunk(eeg_data, timestamp)  
        #outlet_eeg.push_chunk(data[:11])

        # 将加速度数据发送到LSL
        # outlet_accel.push_chunk(data[8:11])
        

        time.sleep(0.04)  # 每0.04秒发送一次数据
except KeyboardInterrupt:
    # 停止并关闭数据流
    board.stop_stream()
    board.release_session()
