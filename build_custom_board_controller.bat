@echo off

REM 设置构建目录
set BUILD_DIR=build_custom
set BOARD_CONTROLLER_SRC_DIR=src\board_controller
set OUTPUT_DIR=custom_libs

REM 创建构建目录
if not exist %BUILD_DIR% mkdir %BUILD_DIR%
if not exist %OUTPUT_DIR% mkdir %OUTPUT_DIR%

REM 复制修改后的文件
copy %BOARD_CONTROLLER_SRC_DIR%\openbci\openbci_serial_board_modified.cpp %BUILD_DIR%\openbci_serial_board.cpp

REM 复制原始头文件
xcopy /E /I %BOARD_CONTROLLER_SRC_DIR%\inc %BUILD_DIR%\inc
xcopy /E /I %BOARD_CONTROLLER_SRC_DIR%\openbci\inc %BUILD_DIR%\openbci_inc

REM 创建自定义的CMakeLists.txt文件
echo ^# 自定义CMakeLists.txt用于构建修改后的BoardController.dll > %BUILD_DIR%\CMakeLists.txt
echo cmake_minimum_required(VERSION 3.10) >> %BUILD_DIR%\CMakeLists.txt
echo project(BrainFlowCustomBoardController VERSION 0.0.1 LANGUAGES CXX C) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置C++标准 >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_CXX_STANDARD 11) >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_CXX_STANDARD_REQUIRED ON) >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_CXX_EXTENSIONS OFF) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置可见性预设 >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_CXX_VISIBILITY_PRESET hidden) >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_VISIBILITY_INLINES_HIDDEN YES) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置构建类型为Debug >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_BUILD_TYPE Debug) >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /Zi /Od") >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置BrainFlow版本 >> %BUILD_DIR%\CMakeLists.txt
echo set(BRAINFLOW_VERSION "0.0.1") >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置位置独立代码 >> %BUILD_DIR%\CMakeLists.txt
echo set(CMAKE_POSITION_INDEPENDENT_CODE ON) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 添加包含目录 >> %BUILD_DIR%\CMakeLists.txt
echo include_directories("..\src\utils\inc") >> %BUILD_DIR%\CMakeLists.txt
echo include_directories("inc") >> %BUILD_DIR%\CMakeLists.txt
echo include_directories("openbci_inc") >> %BUILD_DIR%\CMakeLists.txt
echo include_directories("..\third_party") >> %BUILD_DIR%\CMakeLists.txt
echo include_directories("..\third_party\json") >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 定义源文件 >> %BUILD_DIR%\CMakeLists.txt
echo set(BOARD_CONTROLLER_SRC >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\timestamp.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\data_buffer.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\os_serial.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\os_serial_ioctl.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\serial.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\libftdi_serial.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\socket_client_tcp.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\socket_client_udp.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\socket_server_tcp.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\socket_server_udp.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\multicast_client.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\multicast_server.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\broadcast_client.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\utils\broadcast_server.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\galea_v4.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\galea_serial_v4.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\galea.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\galea_serial.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     openbci_serial_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\openbci_wifi_shield_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\ganglion_wifi.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\cyton_wifi.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\cyton_daisy_wifi.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\expandable_eeg32_wifi.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\ganglion.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\ganglion_native.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\cyton.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\openbci\cyton_daisy.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\board_controller.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\board_info_getter.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\brainflow_boards.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\streaming_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\synthetic_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\dyn_lib_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\bt_lib_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\playback_file_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\file_streamer.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\multicast_streamer.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\plotjuggler_udp_streamer.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\gtec\unicorn_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\neuromd_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\brainbit.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\callibri.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\callibri_eeg.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\callibri_ecg.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\callibri_emg.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neurosity\notion_osc.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\mentalab\explore.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\oymotion\gforce_pro.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\oymotion\gforce_dual.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\freeeeg\freeeeg.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\neuromd\brainbit_bled.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\muse\muse_bled.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\ant_neuro\ant_neuro.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\enophone\enophone.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\ble_lib_board.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\muse\muse.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\brainalive\brainalive.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\emotibit\emotibit.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\ntl\ntl_wifi.cpp >> %BUILD_DIR%\CMakeLists.txt
echo     ..\src\board_controller\aavaa\aavaa_v3.cpp >> %BUILD_DIR%\CMakeLists.txt
echo ) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 编译定义 >> %BUILD_DIR%\CMakeLists.txt
echo add_compile_definitions(NOMINMAX BRAINFLOW_VERSION=${BRAINFLOW_VERSION}) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 创建动态库 >> %BUILD_DIR%\CMakeLists.txt
echo add_library(BoardController SHARED ${BOARD_CONTROLLER_SRC}) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 设置输出目录 >> %BUILD_DIR%\CMakeLists.txt
echo set_target_properties(BoardController PROPERTIES >> %BUILD_DIR%\CMakeLists.txt
echo     ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/..\%OUTPUT_DIR%"
>> %BUILD_DIR%\CMakeLists.txt
echo     LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/..\%OUTPUT_DIR%"
>> %BUILD_DIR%\CMakeLists.txt
echo     RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/..\%OUTPUT_DIR%"
>> %BUILD_DIR%\CMakeLists.txt
echo ) >> %BUILD_DIR%\CMakeLists.txt
echo. >> %BUILD_DIR%\CMakeLists.txt
echo ^# 复制到Python包目录 >> %BUILD_DIR%\CMakeLists.txt
echo add_custom_command(TARGET BoardController POST_BUILD >> %BUILD_DIR%\CMakeLists.txt
echo     COMMAND ${CMAKE_COMMAND} -E copy_if_different "${CMAKE_CURRENT_SOURCE_DIR}/..\%OUTPUT_DIR%/BoardController.dll" "${CMAKE_CURRENT_SOURCE_DIR}/../python_package/brainflow/lib/BoardController.dll" >> %BUILD_DIR%\CMakeLists.txt
echo     COMMAND ${CMAKE_COMMAND} -E copy_if_different "${CMAKE_CURRENT_SOURCE_DIR}/..\%OUTPUT_DIR%/BoardController.lib" "${CMAKE_CURRENT_SOURCE_DIR}/../python_package/brainflow/lib/BoardController.lib" >> %BUILD_DIR%\CMakeLists.txt
echo ) >> %BUILD_DIR%\CMakeLists.txt

REM 运行CMake生成项目
cd %BUILD_DIR%
cmake -G "Visual Studio 17 2022" -A x64 ..

REM 构建项目
cmake --build . --config Debug

REM 复制生成的动态库
copy Debug\BoardController.dll ..\%OUTPUT_DIR%
copy Debug\BoardController.lib ..\%OUTPUT_DIR%

REM 提示用户
cd ..
echo 构建完成！修改后的BoardController.dll已生成在%OUTPUT_DIR%目录中
echo 并已复制到python_package/brainflow/lib目录下
echo 现在您可以使用以下命令运行您的程序：
echo py3.7 -u "e:\Interesting\BCI\brainflow-master\python_package\examples\plot_real_time\plot_real_time.py" --serial-port COM10 --board 0
echo.
echo 如果遇到问题，请尝试修改openbci_serial_board_modified.cpp文件中的SKIP_WELCOME_CHARACTERS_CHECK宏定义
echo 或者调整set_port_settings方法中的参数，以适应您的自制采集板
echo.
pause