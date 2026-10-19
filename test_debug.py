from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
import time

def main():
    print("Starting test...")
    
    # 设置参数
    params = BrainFlowInputParams()
    params.ip_address = "192.168.1.1"  # 使用一个示例 IP 地址
    params.ip_port = 6677  # 使用一个示例端口
    
    print(f"Parameters set: ip_address={params.ip_address}, ip_port={params.ip_port}")

    # 创建 BoardShim 实例
    print("Creating BoardShim instance...")
    board = BoardShim(BoardIds.CYTON_DAISY_WIFI_BOARD, params)
    print("BoardShim instance created")

    # 准备会话
    print("Preparing session...")
    board.prepare_session()
    print("Session prepared successfully")

if __name__ == "__main__":
    main() 