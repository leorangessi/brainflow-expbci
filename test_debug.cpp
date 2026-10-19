#include <iostream>
#include <string>
#include "board_controller/inc/board_controller.h"

int main() {
    // 设置参数
    struct BrainFlowInputParams params;
    params.ip_address = "192.168.1.1";
    params.ip_port = 6677;

    // 准备会话
    int board_id = (int)BoardIds::CYTON_DAISY_WIFI_BOARD;
    int res = prepare_session(board_id, &params);
    
    if (res != (int)StatusCodes::STATUS_OK) {
        std::cout << "Error preparing session: " << res << std::endl;
        return 1;
    }

    std::cout << "Session prepared successfully" << std::endl;
    return 0;
} 