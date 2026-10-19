from pylsl import StreamInlet, resolve_byprop, StreamInfo, StreamOutlet, local_clock
import numpy as np
import matplotlib.pyplot as plt

# 查找两个EEG流
streams_eeg1 = resolve_byprop('type', 'EEG1', timeout=5)
streams_eeg2 = resolve_byprop('type', 'EEG2', timeout=5)

if len(streams_eeg1) == 0 or len(streams_eeg2) == 0:
    print("未找到两个 EEG 流。请检查 LSL 流的类型是否正确。")
    exit()

# 初始化两个 LSL 输入流
inlet_eeg1 = StreamInlet(streams_eeg1[0])
inlet_eeg2 = StreamInlet(streams_eeg2[0])
info = StreamInfo('OpenBCI_EEG', 'EEG', 16, 250, 'float32', 'myuid12345')
outlet = StreamOutlet(info)  
# 设置绘图
# plt.ion()
# fig, ax = plt.subplots()
# line, = ax.plot(np.zeros(16))

while True:
    # 从两个流中分别接收数据
    sample_eeg1, _ = inlet_eeg1.pull_sample()
    sample_eeg2, _ = inlet_eeg2.pull_sample()

    # 合并两个8通道的数据成一个16通道数据
    combined_sample = sample_eeg1 + sample_eeg2  # 合并为16通道

    timestamp = local_clock() 
    outlet.push_sample(combined_sample, timestamp) 
    # 打印合并后的数据
    # print("Combined EEG Sample:", combined_sample)
    
    # 更新绘图
    # line.set_ydata(combined_sample)
    # plt.pause(0.01)
