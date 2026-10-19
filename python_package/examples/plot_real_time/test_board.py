import logging
import sys
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

def main():
    # 配置日志输出到控制台
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 启用 BrainFlow 日志
    BoardShim.enable_dev_board_logger()

    # 创建参数
    params = BrainFlowInputParams()
    params.ip_address = '192.168.4.1'
    params.ip_port = 3
    params.ip_protocol = 1  # TCP

    # 创建板子实例
    board = BoardShim(BoardIds.EXPANDABLE_EEG_32_WIFI_BOARD, params)

    try:
        # 准备会话
        logging.info("Preparing session...")
        board.prepare_session()
        logging.info("Session prepared successfully")

        # 获取板子信息
        logging.info(f"Board ID: {board.get_board_id()}")
        logging.info(f"Sampling rate: {BoardShim.get_sampling_rate(board.get_board_id())}")
        logging.info(f"EEG channels: {BoardShim.get_eeg_channels(board.get_board_id())}")
        logging.info(f"Accel channels: {BoardShim.get_accel_channels(board.get_board_id())}")

    except Exception as e:
        logging.error(f"Error occurred: {str(e)}", exc_info=True)
    finally:
        if board.is_prepared():
            logging.info("Releasing session")
            board.release_session()

if __name__ == "__main__":
    main() 