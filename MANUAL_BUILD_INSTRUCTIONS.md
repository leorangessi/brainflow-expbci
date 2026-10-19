# 手动构建和测试修改后的OpenBCI动态库

由于自动构建过程中遇到了环境配置问题，以下是手动构建和测试的详细步骤：

## 1. 准备修改后的源代码

我们已经创建了修改后的文件 `openbci_serial_board_modified.cpp`，它包含了跳过欢迎字符检查的功能。

主要修改：
- 添加了 `SKIP_WELCOME_CHARACTERS_CHECK` 宏定义
- 修改了 `status_check()` 方法，在宏启用时直接返回成功
- 调整了 `prepare_session()` 方法，跳过了一些检查

## 2. 手动构建步骤

### 方法1：使用Visual Studio IDE

1. 打开 `build\BrainFlow.sln` 解决方案文件
2. 在解决方案资源管理器中，找到并右键点击 `BoardController` 项目
3. 选择 "生成" 或 "重新生成"
4. 构建完成后，检查 `build\x64\Debug\BoardController.dll` 文件是否生成

### 方法2：使用VS开发人员命令提示符

1. 打开 "开始" 菜单，搜索并运行 "Developer Command Prompt for VS 2022"
2. 导航到项目目录：
   ```
   cd e:\Interesting\BCI\brainflow-master
   ```
3. 运行构建命令：
   ```
   msbuild build\BoardController.vcxproj /p:Configuration=Debug /p:Platform=x64
   ```

## 3. 复制动态库到Python包

构建成功后，手动将生成的DLL文件复制到Python包的lib目录：

```
copy build\x64\Debug\BoardController.dll python_package\brainflow\lib\
copy build\x64\Debug\BoardController.lib python_package\brainflow\lib\
```

## 4. 运行测试

使用以下命令运行我们创建的测试脚本：

```
py3.7 -u "python_package\examples\plot_real_time\plot_real_time_test.py" --serial-port COM10 --board 0
```

或者运行原始示例脚本：

```
py3.7 -u "python_package\examples\plot_real_time\plot_real_time.py" --serial-port COM10 --board 0
```

## 5. 恢复原始文件（可选）

如果需要恢复原始文件：

```
copy src\board_controller\openbci\openbci_serial_board.cpp.bak src\board_controller\openbci\openbci_serial_board.cpp
```

## 6. 故障排除

- 如果构建失败，请确保安装了Visual Studio 2022和CMake
- 检查串口设置是否正确，确保COM10是正确的端口
- 检查设备是否正确连接并已上电
- 查看Python脚本输出的日志以获取更多调试信息

## 7. 修改说明

修改后的代码主要解决了自制OpenBCI采集板不发送三个连续'$$$'欢迎字符的问题。通过定义 `SKIP_WELCOME_CHARACTERS_CHECK` 宏，我们跳过了这个检查逻辑，使BrainFlow能够与自制采集板正常通信。

如果需要禁用跳过检查功能，只需将宏定义从 `1` 改为 `0`，然后重新构建即可。

祝您测试顺利！