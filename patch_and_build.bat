@echo off

REM 设置为管理员权限运行
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo 请求管理员权限...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)

REM 设置构建目录
set ROOT_DIR=%cd%
set OPENBCI_DIR=%ROOT_DIR%\src\board_controller\openbci
set BUILD_DIR=%ROOT_DIR%\build
set OUTPUT_DIR=%ROOT_DIR%\custom_libs

REM 创建输出目录
if not exist %OUTPUT_DIR% mkdir %OUTPUT_DIR%

REM 备份原始文件
if exist %OPENBCI_DIR%\openbci_serial_board.cpp (
    echo 备份原始文件...
    copy %OPENBCI_DIR%\openbci_serial_board.cpp %OPENBCI_DIR%\openbci_serial_board.cpp.bak
    if %errorLevel% neq 0 (
        echo 备份失败！
        pause
        exit /b 1
    )
)

REM 复制修改后的文件
if exist %OPENBCI_DIR%\openbci_serial_board_modified.cpp (
    echo 应用修改...
    copy /Y %OPENBCI_DIR%\openbci_serial_board_modified.cpp %OPENBCI_DIR%\openbci_serial_board.cpp
    if %errorLevel% neq 0 (
        echo 复制修改后的文件失败！
        pause
        exit /b 1
    )
)

REM 创建构建目录（如果不存在）
if not exist %BUILD_DIR% mkdir %BUILD_DIR%
cd %BUILD_DIR%

REM 使用CMake生成项目
if not exist %BUILD_DIR%\CMakeCache.txt (
    echo 生成CMake项目...
    cmake -G "Visual Studio 17 2022" -A x64 ..
    if %errorLevel% neq 0 (
        echo CMake生成失败！
        cd %ROOT_DIR%
        pause
        exit /b 1
    )
)

REM 构建BoardController.dll
set BOARD_CONTROLLER_PROJ=%BUILD_DIR%\BoardController.vcxproj
if exist %BOARD_CONTROLLER_PROJ% (
    echo 构建BoardController.dll...
    msbuild %BOARD_CONTROLLER_PROJ% /p:Configuration=Debug /p:Platform=x64
    if %errorLevel% neq 0 (
        echo 构建失败！
        cd %ROOT_DIR%
        pause
        exit /b 1
    )
) else (
    echo BoardController项目文件不存在！
    cd %ROOT_DIR%
    pause
    exit /b 1
)

REM 复制生成的动态库
set DLL_PATH=%BUILD_DIR%\x64\Debug\BoardController.dll
set LIB_PATH=%BUILD_DIR%\x64\Debug\BoardController.lib
set PYTHON_LIB_DIR=%ROOT_DIR%\python_package\brainflow\lib

if exist %DLL_PATH% (
    echo 复制动态库...
    copy /Y %DLL_PATH% %OUTPUT_DIR%
    copy /Y %LIB_PATH% %OUTPUT_DIR%
    copy /Y %DLL_PATH% %PYTHON_LIB_DIR%
    copy /Y %LIB_PATH% %PYTHON_LIB_DIR%
    if %errorLevel% neq 0 (
        echo 复制动态库失败！
        cd %ROOT_DIR%
        pause
        exit /b 1
    )
)

REM 清理
cd %ROOT_DIR%

REM 显示完成信息
echo. 
echo ======================================================
echo 构建完成！
echo 修改后的BoardController.dll已生成在%OUTPUT_DIR%目录中
echo 并已复制到python_package/brainflow/lib目录下
echo. 
echo 使用以下命令运行测试脚本：
echo py3.7 -u "python_package\examples\plot_real_time\plot_real_time_test.py" --serial-port COM10 --board 0
echo. 
echo 或运行原始的示例脚本：
echo py3.7 -u "python_package\examples\plot_real_time\plot_real_time.py" --serial-port COM10 --board 0
echo ======================================================
echo. 
pause