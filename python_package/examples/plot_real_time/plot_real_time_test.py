import argparse
import time
import logging
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter

# 设置日志级别
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial-port', type=str, help='serial port', required=True)
    parser.add_argument('--board', type=int, help='board id, use 0 for Cyton', default=0)
    parser.add_argument('--timeout', type=int, help='timeout for device discovery or connection', default=0)
    args = parser.parse_args()
    
    # 设置参数
    params = BrainFlowInputParams()
    params.serial_port = args.serial_port
    params.timeout = args.timeout
    
    try:
        # 初始化BoardShim
        logger.info(f'尝试初始化板子，board_id: {args.board}, serial_port: {args.serial_port}')
        board_shim = BoardShim(args.board, params)
        
        # 准备会话 - 这里应该使用我们修改后的跳过欢迎字符检查的逻辑
        logger.info('准备会话...')
        start_time = time.time()
        board_shim.prepare_session()
        elapsed = time.time() - start_time
        logger.info(f'会话准备成功！耗时: {elapsed:.2f}秒')
        
        # 启动数据流
        logger.info('启动数据流...')
        board_shim.start_stream(450000)
        time.sleep(2)  # 给一些时间让数据开始流动
        
        # 尝试获取一些数据
        logger.info('尝试获取数据...')
        data = board_shim.get_current_board_data(256)  # 获取最近的256个样本
        logger.info(f'获取到数据，形状: {data.shape}')
        
        # 如果有数据，打印一些基本信息
        if data.size > 0:
            num_channels = data.shape[0]
            num_samples = data.shape[1]
            logger.info(f'数据包含 {num_channels} 个通道，每个通道有 {num_samples} 个样本')
            
            # 打印第一个通道的前10个样本
            if num_channels > 0 and num_samples > 0:
                logger.info(f'通道0的前10个样本: {data[0, :10]}')
        else:
            logger.warning('没有获取到数据')
        
        # 停止数据流
        logger.info('停止数据流...')
        board_shim.stop_stream()
        
        # 释放会话
        logger.info('释放会话...')
        board_shim.release_session()
        
        logger.info('测试完成！')
        
except Exception as e:
        logger.error(f'发生错误: {str(e)}')
        import traceback
        traceback.print_exc()
        
        # 确保即使发生错误也释放会话
        try:
            if 'board_shim' in locals():
                board_shim.release_session()
        except:
            pass
    
if __name__ == '__main__':
    main()