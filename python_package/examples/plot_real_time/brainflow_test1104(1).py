import brainflow  
import time  
from pylsl import StreamInfo, StreamOutlet, local_clock  
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
  
# 配置Brainflow参数  
params = BrainFlowInputParams()
board_id = 5  # OpenBCI Cyton WiFi  
params.ip_address = "192.168.31.254"  # 修改为你的WiFi板IP地址
params.ip_port = 4  # 默认端口，可以根据需要调整
params.board_id = 5
params.sampling_rate = 250  # OpenBCI Cyton的采样率  
  
# 启动Brainflow板  
board = brainflow.BoardShim(board_id, params)  
board.prepare_session()  
board.start_stream()  
  
# 配置LSL流信息  
# info = StreamInfo('EEG', 'EEG_from_OpenBCI_Cyton_WiFi', 8, 250, 'float32', 'myuid12345')  

# 创建LSL输出流  
# channel_format = info.desc().append_child("channels").first_desc()  
# channel_format.append_child("name").set_value("EEG")  
# channel_format.append_child("unit").set_value("microVolts")  
# channel_format.append_child("type").set_value("EEG")  
# channel_format.append_child("dimension").set_value('0')  
  
# outlet = StreamOutlet(info)  
  
try:  
    while True:  
        # 从Brainflow板获取数据  
        board_data = board.get_board_data()  
        if board_data is None:  
            print("Failed to get data from board")  
            continue  
  
        # 提取EEG数据  
        eeg_data = board_data[0:8]  # OpenBCI Cyton有8个EEG通道  
  
        # 发送数据到LSL  
        timestamp = local_clock()  
        # outlet.push_sample(eeg_data, timestamp)  
          
        # 打印一些调试信息  
        print(f"Sent sample: {eeg_data} at timestamp: {timestamp}")  
          
        # 延迟以匹配采样率  
        time.sleep(1.0 / 250)  
  
except KeyboardInterrupt:  
    print("Stopping...")  
finally:  
    # 清理资源  
    board.stop_stream()  
    board.release_session()  