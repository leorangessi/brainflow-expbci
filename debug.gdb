# 设置共享库搜索路径
set solib-search-path python_package/brainflow/lib

# 加载 Python 可执行文件
file python

# 设置断点在 prepare_session 函数
break prepare_session

# 当程序停在断点时，打印参数
commands
    print board_id
    print json
    bt
    continue
end

# 设置 Python 脚本参数
set args test_debug.py

# 运行程序
run 