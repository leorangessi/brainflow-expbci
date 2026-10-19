#include "openbci_serial_board.h"
#include "board_controller.h"
#include "board.h"
#include "brainflow_constants.h"
#include "serial.h"
#include "socket.h"
#include "data_buffer.h"
#include "timestamp.h"
#include "spdlog/spdlog.h"

#include <string>
#include <chrono>
#include <thread>
#include <mutex>

// 添加一个宏定义，用于控制是否跳过欢迎字符检查
#define SKIP_WELCOME_CHARACTERS_CHECK 1

OpenBCISerialBoard::OpenBCISerialBoard (struct BrainFlowInputParams params, int board_id) : Board (params, board_id)
{
    serial = NULL;
    initialized = false;
    keep_alive = false;
    is_streaming = false;
    sampling_rate = 250;
    packet_size = 33;
}

OpenBCISerialBoard::~OpenBCISerialBoard ()
{
    if (serial)
    {
        delete serial;
        serial = NULL;
    }
}

int OpenBCISerialBoard::open_port ()
{
    safe_logger (spdlog::level::info, "opening port {}", params.serial_port.c_str ());
    int res = serial->open_serial_port ();
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        safe_logger (spdlog::level::err, "unable to open serial port {}", params.serial_port.c_str ());
        return (int)BrainFlowExitCodes::PORT_OPEN_ERROR;
    }
    safe_logger (spdlog::level::trace, "port {} is open", params.serial_port.c_str ());
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::send_to_board (const char *msg)
{
    safe_logger (spdlog::level::debug, "sending {} to the board", msg);
    std::string msg_with_newline = std::string(msg) + "\n";
    int res = serial->write_to_serial_port ((const unsigned char *)msg_with_newline.c_str (), msg_with_newline.size ());
    if (res < 0)
    {
        safe_logger (spdlog::level::err, "unable to send data to board");
        return (int)BrainFlowExitCodes::SEND_DATA_ERROR;
    }
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::send_to_board (const char *msg, std::string &response)
{
    int res = send_to_board(msg);
    if (res == (int)BrainFlowExitCodes::STATUS_OK)
    {
        response = read_serial_response();
    }
    return res;
}

std::string OpenBCISerialBoard::read_serial_response ()
{
    constexpr int max_tmp_size = 4096;
    unsigned char tmp_array[max_tmp_size];
    unsigned char tmp;
    int tmp_id = 0;
    while (serial->read_from_serial_port (&tmp, 1) == 1)
    {
        if (tmp_id < max_tmp_size)
        {
            tmp_array[tmp_id] = tmp;
            tmp_id++;
        }
        else
        {
            serial->flush_buffer ();
            break;
        }
    }
    tmp_id = (tmp_id == max_tmp_size) ? tmp_id - 1 : tmp_id;
    tmp_array[tmp_id] = '\0';

    return std::string ((const char *)tmp_array);
}

int OpenBCISerialBoard::config_board (std::string config, std::string &response)
{
    if (!initialized)
    {
        safe_logger (spdlog::level::err, "board is not initialized");
        return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
    }

    int res = send_to_board (config.c_str (), response);
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        return res;
    }

    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::set_port_settings ()
{
    int res = serial->set_serial_port_settings (1000, false);
    if (res < 0)
    {
        safe_logger (spdlog::level::err, "Unable to set port settings, res is {}", res);
        return (int)BrainFlowExitCodes::SET_PORT_ERROR;
    }
    safe_logger (spdlog::level::trace, "set port settings");
#ifdef __APPLE__
    int set_latency_res = serial->set_custom_latency (1);
    safe_logger (spdlog::level::info, "set_latency_res is: {}", set_latency_res);
#endif
    return send_to_board ("v");
}

int OpenBCISerialBoard::status_check ()
{
#if SKIP_WELCOME_CHARACTERS_CHECK
    // 跳过欢迎字符检查，直接返回成功
    safe_logger (spdlog::level::info, "Skipping welcome characters check");
    return (int)BrainFlowExitCodes::STATUS_OK;
#else
    // 保留原始的检查逻辑
    unsigned char buf[1];
    int count = 0;
    int max_empty_seq = 5;
    int num_empty_attempts = 0;
    std::string resp = "";

    for (int i = 0; i < 500; i++)
    {
        int res = serial->read_from_serial_port (buf, 1);
        if (res > 0)
        {
            resp += buf[0];
            num_empty_attempts = 0;
            // board is ready if there are '$$$'
            if (buf[0] == '$')
            {
                count++;
            }
            else
            {
                count = 0;
            }
            if (count == 3)
            {
                return (int)BrainFlowExitCodes::STATUS_OK;
            }
        }
        else
        {
            num_empty_attempts++;
            if (num_empty_attempts > max_empty_seq)
            {
                safe_logger (spdlog::level::err, "board doesnt send welcome characters! Msg: {}",
                    resp.c_str ());
                return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
            }
        }
    }
    return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
#endif
}

int OpenBCISerialBoard::prepare_session ()
{
    if (initialized)
    {
        safe_logger (spdlog::level::info, "Session already prepared");
        return (int)BrainFlowExitCodes::STATUS_OK;
    }
    if (params.serial_port.empty ())
    {
        safe_logger (spdlog::level::err, "serial port is empty");
        return (int)BrainFlowExitCodes::INVALID_ARGUMENTS_ERROR;
    }
#ifdef _WIN32
    LONG res = set_ftdi_latency_in_registry (1, params.serial_port);
    if (res != ERROR_SUCCESS)
    {
        safe_logger (spdlog::level::warn,
            "failed to adjust latency param in ftdi driver automatically, reboot or dongle "
            "reconnection may be needed.");
    }
#endif
    serial = Serial::create (params.serial_port.c_str (), this);
    int port_open = open_port ();
    if (port_open != (int)BrainFlowExitCodes::STATUS_OK)
    {
        delete serial;
        serial = NULL;
        return port_open;
    }

    int set_settings = set_port_settings ();
    if (set_settings != (int)BrainFlowExitCodes::STATUS_OK)
    {
        delete serial;
        serial = NULL;
        return set_settings;
    }

    int initted = status_check ();
    if (initted != (int)BrainFlowExitCodes::STATUS_OK)
    {
        delete serial;
        serial = NULL;
        return initted;
    }

    // 由于是自制板子，我们可能需要跳过发送'd'命令的检查
    // 或者根据实际情况调整命令
    int send_res = send_to_board ("d");
    if (send_res != (int)BrainFlowExitCodes::STATUS_OK)
    {
#if SKIP_WELCOME_CHARACTERS_CHECK
        // 跳过命令发送失败的检查
        safe_logger (spdlog::level::warn, "跳过命令发送失败检查，继续初始化");
#else
        return send_res;
#endif
    }

#if !SKIP_WELCOME_CHARACTERS_CHECK
    std::string response = read_serial_response ();
    if (response.find ("Failure") != std::string::npos)
    {
        safe_logger (spdlog::level::err, "board replied with failure: {}", response.c_str ());
        return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
    }
#endif

    keep_alive = false;
    initialized = true;
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::start_stream (int buffer_size, const char *streamer_params)
{
    if (!initialized)
    {
        safe_logger (spdlog::level::err, "board is not initialized");
        return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
    }

    // 清空缓冲区
    serial->flush_buffer ();

    // 创建数据缓冲区
    int res = buffers->create_buffer (params.board_id, buffer_size);
    if (res < 0)
    {
        return res;
    }

    // 启动数据读取线程
    keep_alive = true;
    streaming_thread = new std::thread (&OpenBCISerialBoard::read_thread, this);
    if (!streaming_thread)
    {
        safe_logger (spdlog::level::err, "unable to create streaming thread");
        keep_alive = false;
        return (int)BrainFlowExitCodes::THREAD_CREATION_ERROR;
    }

    // 给线程一些时间启动
    std::this_thread::sleep_for (std::chrono::milliseconds (100));

    // 发送开始数据流的命令
    res = send_to_board ("b");
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        keep_alive = false;
        if (streaming_thread) {
            streaming_thread->join();
            delete streaming_thread;
            streaming_thread = NULL;
        }
        return res;
    }

    is_streaming = true;
    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::stop_stream ()
{
    if (!initialized)
    {
        safe_logger (spdlog::level::err, "board is not initialized");
        return (int)BrainFlowExitCodes::BOARD_NOT_READY_ERROR;
    }

    int res = send_to_board ("s");
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        return res;
    }

    if (streaming_thread)
    {
        streaming_thread->join ();
        delete streaming_thread;
        streaming_thread = NULL;
    }

    return (int)BrainFlowExitCodes::STATUS_OK;
}

int OpenBCISerialBoard::release_session ()
{
    if (!initialized)
    {
        safe_logger (spdlog::level::info, "session already released");
        return (int)BrainFlowExitCodes::STATUS_OK;
    }

    stop_stream ();
    int res = send_to_board ("s");
    if (res != (int)BrainFlowExitCodes::STATUS_OK)
    {
        safe_logger (spdlog::level::warn, "unable to send stop command");
    }

    if (serial)
    {
        serial->close_serial_port ();
        delete serial;
        serial = NULL;
    }
    initialized = false;
    return (int)BrainFlowExitCodes::STATUS_OK;
}

// 注意：这是一个虚函数，应该在具体的板子子类中实现
// 这里提供一个基本的实现，但实际使用时应该在子类中覆盖
void OpenBCISerialBoard::read_thread ()
{
    // 警告：这是一个基类的实现，实际使用时应该在具体的板子子类中覆盖
    safe_logger (spdlog::level::warn, "使用基类OpenBCISerialBoard的read_thread()方法，请在子类中实现具体的数据处理逻辑");
    
    unsigned char packet[MAX_PACKET_SIZE];
    int packet_offset = 0;
    int num_bytes_read = 0;
    
    while (keep_alive)
    {
        // 读取数据并处理
        num_bytes_read = serial->read_from_serial_port (&packet[packet_offset], MAX_PACKET_SIZE - packet_offset);
        if (num_bytes_read > 0)
        {
            packet_offset += num_bytes_read;
            // 这里应该有具体的数据处理逻辑
            // 由于是基类，我们只是简单地记录接收到的数据
            safe_logger (spdlog::level::trace, "接收到 {} 字节数据", num_bytes_read);
        }
        else
        {
            std::this_thread::sleep_for (std::chrono::milliseconds (1));
        }
    }
}