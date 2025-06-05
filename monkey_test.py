import subprocess
import time

# 定义设备 ID（如果有多个设备连接，需要指定设备 ID）
device_id = None

package_name = "com.example.jiyulearning"

monkey_command = [
    "adb"
]

if device_id:
    monkey_command.extend(["-s", device_id])

monkey_command.extend([
    "shell",
    "monkey",
    "-p", package_name,
    "-v", "5000"  # 发送 5000 个随机事件
])

try:
    # 执行 Monkey 命令
    print("开始执行 Monkey 压测...")
    process = subprocess.Popen(monkey_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # 实时输出 Monkey 命令的执行结果
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())

    # 获取命令执行的返回码和错误信息
    return_code = process.poll()
    stderr = process.stderr.read()

    if return_code == 0:
        print("Monkey 压测执行成功！")
    else:
        print(f"Monkey 压测执行失败，返回码: {return_code}")
        print(f"错误信息: {stderr}")

except Exception as e:
    print(f"执行 Monkey 压测时出现错误: {e}")