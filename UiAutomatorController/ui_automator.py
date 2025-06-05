import queue
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
import os
import json
import re
from typing import Tuple, Optional, Dict, Any, Callable


class UiAutomatorController:
    """使用ADB和UI Automator实现的Android UI自动化控制器，支持优化的页面缓存"""

    def __init__(self, use_cache: bool = True, cache_dir: str = "ui_cache", device_index: int = 0):
        # 验证ADB是否安装
        try:
            subprocess.run(["adb", "version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise EnvironmentError("未找到ADB工具，请确保已安装Android SDK Platform-Tools并添加到PATH中")

        # 验证设备是否连接
        devices = self._get_connected_devices()
        if not devices:
            raise ConnectionError("未检测到已连接的Android设备，请确保设备已开启USB调试并连接到电脑")
        self.device = devices[device_index]  # 使用指定索引的设备
        print(f"使用设备: {self.device}")

        # 缓存配置
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

        # 预加载所有已知Activity的缓存
        self.activity_cache = self._preload_activity_cache()

        # 当前Activity
        self.current_activity = None

        # 弹窗处理配置
        self.popup_handlers = {}
        self.permission_handlers = {}
        self._register_default_handlers()

        # Toast监测配置
        self.toast_queue = queue.Queue()
        self.toast_listeners = []
        self.toast_monitor_thread = None
        self.is_monitoring_toast = False

    def _get_connected_devices(self) -> list:
        """获取已连接的Android设备列表"""
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")[1:]  # 跳过标题行
        return [line.split()[0] for line in lines if line.strip() and "device" in line]

    def _get_current_activity(self) -> str:
        """获取当前活动的Activity名称，使用更健壮的解析逻辑"""
        result = subprocess.run(["adb", "shell", "dumpsys", "window", "windows"], capture_output=True, text=True)

        # 使用正则表达式匹配Activity名称
        pattern = r'ActivityRecord\{[^}]+\s+([^/]+/[^}]+)\}'
        pattern_alt = r'mCurrentFocus=.*?([^/]+/[^}\s]+)'

        match = None
        for line in result.stdout.split("\n"):
            if "ActivityRecord" in line or "mCurrentFocus" in line:
                match = re.search(pattern, line) or re.search(pattern_alt, line)
                if match:
                    activity = match.group(1).strip()
                    break

        if match:
            # 清理Activity名称，移除版本号、任务ID等动态部分
            activity = self._sanitize_activity_name(activity)
            self.current_activity = activity
            return activity

        print("警告: 无法获取当前Activity名称！")
        return ""

    def _sanitize_activity_name(self, name: str) -> str:
        """清理Activity名称，移除动态部分并替换非法文件名字符"""
        # 移除类似 " t1234" 或 "/t1234" 的任务ID部分
        name = re.sub(r'\s*/?\s*t\d+', '', name)
        # 替换非法文件名字符
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def _preload_activity_cache(self) -> Dict[str, Dict[str, Any]]:
        """预加载所有已知Activity的缓存"""
        activity_cache = {}
        if not self.use_cache:
            return activity_cache

        for file in os.listdir(self.cache_dir):
            if file.endswith(".json") and not file.startswith("temp_"):
                # 从文件名提取设备ID和Activity名称
                parts = file.replace(".json", "").split("_", 1)
                if len(parts) != 2:
                    continue  # 跳过格式不正确的文件
                device_id, activity_name = parts

                if device_id == self.device:
                    cache_file = os.path.join(self.cache_dir, file)
                    try:
                        with open(cache_file, "r") as f:
                            activity_cache[activity_name] = json.load(f)
                        print(f"预加载Activity缓存: {activity_name}")
                    except Exception as e:
                        print(f"无法加载缓存 {file}: {e}")
        return activity_cache

    def _save_activity_cache(self, activity_name: str, cache_data: Dict[str, Any]) -> None:
        """保存Activity缓存"""
        if not self.use_cache:
            return

        # 确保Activity名称已清理
        activity_name = self._sanitize_activity_name(activity_name)
        cache_file = os.path.join(self.cache_dir, f"{self.device}_{activity_name}.json")

        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)
        print(f"保存Activity缓存: {activity_name} ({cache_file})")

    def _get_element_key(self, resource_id: Optional[str] = None,
                         text: Optional[str] = None,
                         class_name: Optional[str] = None) -> str:
        """生成元素的唯一键"""
        parts = []
        if resource_id:
            parts.append(f"id={resource_id}")
        if text:
            parts.append(f"text={text}")
        if class_name:
            parts.append(f"class={class_name}")
        return "_".join(parts)

    def find_element(self, resource_id: Optional[str] = None,
                     text: Optional[str] = None,
                     class_name: Optional[str] = None) -> Tuple[int, int]:
        """通过resource_id、text或class_name查找元素，并返回其中心坐标"""
        # 如果启用缓存，尝试从缓存中获取元素
        if self.use_cache:
            activity = self._get_current_activity()

            if not activity:
                print("警告: 由于Activity名称为空，无法使用缓存")

            # 检查Activity缓存是否存在
            if activity and activity not in self.activity_cache:
                self.activity_cache[activity] = {}

            # 生成元素键
            element_key = self._get_element_key(resource_id, text, class_name)

            # 检查缓存中是否有该元素
            if activity and element_key in self.activity_cache[activity]:
                print(f"从缓存中获取元素: {element_key}，center: {self.activity_cache[activity][element_key]}")
                return tuple(self.activity_cache[activity][element_key])

        # 缓存未命中，从实际UI中查找
        root = self._get_ui_hierarchy()

        # 构建XPath查询
        xpath = ".//node"
        conditions = []
        if resource_id:
            conditions.append(f'@resource-id="{resource_id}"')
        if text:
            conditions.append(f'@text="{text}"')
        if class_name:
            conditions.append(f'@class="{class_name}"')

        if conditions:
            xpath += f'[{" and ".join(conditions)}]'

        element = root.find(xpath)
        if element is None:
            raise ValueError(f"未找到元素: resource_id={resource_id}, text={text}, class_name={class_name}")

        # 获取元素边界
        bounds = element.attrib.get("bounds", "[]")
        # 解析边界字符串 "[x1,y1][x2,y2]"
        coords = bounds.strip("[]").split("][")
        x1, y1 = map(int, coords[0].split(","))
        x2, y2 = map(int, coords[1].split(","))

        # 计算中心坐标
        center = ((x1 + x2) // 2, (y1 + y2) // 2)

        # 如果启用缓存，保存元素信息
        if self.use_cache and activity:
            self.activity_cache[activity][element_key] = center
            self._save_activity_cache(activity, self.activity_cache[activity])
            print(f"缓存元素: {element_key} = {center}")

        return center

    def _get_ui_hierarchy(self) -> ET.Element:
        """获取当前界面的UI层次结构"""
        self.current_activity = None

        dump_file = os.path.join(self.cache_dir, "temp_ui.xml")
        subprocess.run(["adb", "shell", "uiautomator", "dump", "/sdcard/ui.xml"], check=True)
        subprocess.run(["adb", "pull", "/sdcard/ui.xml", dump_file], check=True)
        return ET.parse(dump_file).getroot()

    def _register_default_handlers(self) -> None:
        """注册默认的弹窗和权限处理器"""
        # 注册常见权限弹窗处理器
        self.register_permission_handler(
            text="允许",
            action=lambda: self.click_element(text="允许")
        )

        self.register_permission_handler(
            text="始终允许",
            action=lambda: self.click_element(text="始终允许")
        )

    def _handle_popups(self) -> None:
        """处理所有已注册的弹窗"""
        # 先处理权限弹窗
        for text, action in self.permission_handlers.items():
            if self.check_element_exists(text=text):
                print(f"检测到权限弹窗，处理中: {text}")
                action()
                time.sleep(1)  # 处理后等待
                return

        # 再处理普通弹窗
        for text, action in self.popup_handlers.items():
            if self.check_element_exists(text=text):
                print(f"检测到弹窗，处理中: {text}")
                action()
                time.sleep(1)  # 处理后等待
                return

    def register_popup_handler(self, text: str, action: Callable) -> None:
        """注册弹窗处理器"""
        self.popup_handlers[text] = action

    def register_permission_handler(self, text: str, action: Callable) -> None:
        """注册权限弹窗处理器"""
        self.permission_handlers[text] = action

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕尺寸 (宽度, 高度)"""
        result = subprocess.run(["adb", "shell", "wm", "size"], capture_output=True, text=True)
        output = result.stdout.strip()

        # 解析输出 "Physical size: 1080x2340"
        match = re.search(r'(\d+)x(\d+)', output)
        if match:
            width = int(match.group(1))
            height = int(match.group(2))
            return (width, height)

        # 如果无法从wm size获取，则使用默认值
        print("警告: 无法获取屏幕尺寸，使用默认值 1080x1920")
        return (1080, 1920)

    def click_element(self, resource_id: Optional[str] = None,
                      text: Optional[str] = None,
                      class_name: Optional[str] = None) -> None:
        """点击指定元素"""
        x, y = self.find_element(resource_id, text, class_name)
        subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], check=True)
        time.sleep(0.3)  # 点击后等待

    def long_click(self, resource_id: Optional[str] = None,
                   text: Optional[str] = None,
                   class_name: Optional[str] = None,
                   duration: float = 1.0) -> None:
        """长按指定元素"""
        x, y = self.find_element(resource_id, text, class_name)
        # 将持续时间转换为毫秒
        duration_ms = int(duration * 1000)
        subprocess.run(["adb", "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)], check=True)
        time.sleep(0.5)  # 长按后等待

    def input_text(self, resource_id: str, text: str) -> None:
        """在指定元素中输入文本"""
        self.click_element(resource_id=resource_id)
        # 清除现有文本
        subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_MOVE_END"], check=True)
        for _ in range(30):  # 假设最多30个字符
            subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_DEL"], check=True)

        # 输入新文本（处理空格和特殊字符）
        escaped_text = text.replace(" ", "%20")  # 替换空格为URL编码
        subprocess.run(["adb", "shell", "input", "text", escaped_text], check=True)
        time.sleep(0.3)  # 输入后等待

    def check_element_exists(self, resource_id: Optional[str] = None,
                             text: Optional[str] = None,
                             class_name: Optional[str] = None) -> bool:
        """检查元素是否存在"""
        try:
            self.find_element(resource_id, text, class_name)
            return True
        except ValueError:
            return False

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.3) -> None:
        """从起点滑动到终点，持续指定时间"""
        # 将持续时间转换为毫秒
        duration_ms = int(duration * 1000)
        subprocess.run(["adb", "shell", "input", "swipe",
                        str(start_x), str(start_y),
                        str(end_x), str(end_y),
                        str(duration_ms)], check=True)
        time.sleep(0.5)  # 滑动后等待

    def start_app(self, package_name: str, activity_name: str) -> None:
        """启动指定APP"""
        self.current_activity = None
        subprocess.run(["adb", "shell", "am", "start", "-n", f"{package_name}/{activity_name}"], check=True)
        print(f"启动APP: {package_name}/{activity_name}")
        time.sleep(2)  # 启动后等待

    def close_app(self, package_name: str) -> None:
        """关闭指定APP"""
        subprocess.run(["adb", "shell", "am", "force-stop", package_name], check=True)
        print(f"关闭APP: {package_name}")
        time.sleep(0.5)  # 关闭后等待

    def take_screenshot(self, filename: str) -> None:
        """截取当前屏幕"""
        subprocess.run(["adb", "shell", "screencap", "-p", f"/sdcard/{filename}"], check=True)
        subprocess.run(["adb", "pull", f"/sdcard/{filename}", filename], check=True)
        print(f"截图已保存至: {filename}")

    def start_toast_monitor(self) -> None:
        """开始监控Toast消息"""
        if self.is_monitoring_toast:
            print("Toast监控已在运行中")
            return

        self.is_monitoring_toast = True
        self.toast_monitor_thread = threading.Thread(target=self._monitor_toast, daemon=True)
        self.toast_monitor_thread.start()
        print("Toast监控已启动")

    def stop_toast_monitor(self) -> None:
        """停止监控Toast消息"""
        self.is_monitoring_toast = False
        if self.toast_monitor_thread and self.toast_monitor_thread.is_alive():
            print("等待Toast监控进程关闭")
            # 使用音量键强制唤起uiautomator events避免阻塞，绝大多数情况下不影响程序执行
            subprocess.run(["adb", "-s", self.device, "shell", "input", "keyevent", "KEYCODE_VOLUME_UP"], check=True)
            time.sleep(0.2)  # 等待0.2秒
            subprocess.run(["adb", "-s", self.device, "shell", "input", "keyevent", "KEYCODE_VOLUME_DOWN"], check=True)
            time.sleep(0.2)  # 等待0.2秒
            self.toast_monitor_thread.join()
        print("Toast监控已停止")

    def _monitor_toast(self) -> None:
        """在后台线程中监控Toast消息（优化版：指定utf-8编码）"""
        try:
            # 启动uiautomator events命令，明确指定utf-8编码
            process = subprocess.Popen(
                ["adb", "-s", self.device, "shell", "uiautomator", "events", "-u"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",  # 指定utf-8编码
                errors="replace",  # 替换无法解码的字符（可选）
                bufsize=1  # 行缓冲模式
            )

            print("Toast监控线程已启动")

            while self.is_monitoring_toast:
                try:
                    # 读取事件，若无事件则阻塞
                    line = process.stdout.readline()
                    if not line:
                        # 输出流关闭，尝试重启（可选）
                        print("警告：uiautomator events输出流已关闭，尝试重启...")
                        process.terminate()
                        time.sleep(1)
                        process = subprocess.Popen(
                            ["adb", "-s", self.device, "shell", "uiautomator", "events", "-u"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            bufsize=1
                        )
                        continue

                    # 解析Toast事件
                    if "TYPE_NOTIFICATION_STATE_CHANGED" in line and "ClassName: android.widget.Toast" in line:
                        toast_text = self._parse_toast_text(line)
                        if toast_text:
                            print(f"检测到Toast: {toast_text}")
                            self.toast_queue.put(toast_text)
                            for listener in self.toast_listeners:
                                try:
                                    listener(toast_text)
                                except Exception as e:
                                    print(f"监听器错误: {e}")

                except UnicodeDecodeError as e:
                    # 处理解码错误（记录但不中断线程）
                    print(f"解码错误: {e}，跳过当前行")
                    continue
                except subprocess.TimeoutExpired:
                    # 超时处理（考虑到实际上开启uiautomator events的时间长短可能不同，就不进行超时处理了）
                    pass

            # 正常退出时终止进程
            process.terminate()
            process.wait(timeout=2.0)
            print("Toast监控线程已停止")

        except Exception as e:
            print(f"Toast监控线程异常: {e}")
            self.is_monitoring_toast = False

    def _parse_toast_text(self, line: str) -> Optional[str]:
        """从事件行中解析Toast文本"""
        # 查找Text字段
        text_start = line.find("Text: [")
        if text_start == -1:
            return None

        text_start += len("Text: [")
        text_end = line.find("];", text_start)
        if text_end == -1:
            return None

        toast_text = line[text_start:text_end].strip()
        return toast_text if toast_text else None

    def get_toast(self, timeout: float = 5.0) -> Optional[str]:
        """获取下一个Toast消息，超时返回None"""
        try:
            return self.toast_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def add_toast_listener(self, listener: Callable[[str], None]) -> None:
        """添加Toast监听器"""
        self.toast_listeners.append(listener)

    def remove_toast_listener(self, listener: Callable[[str], None]) -> None:
        """移除Toast监听器"""
        if listener in self.toast_listeners:
            self.toast_listeners.remove(listener)

    def wait_for_toast(self, expected_text: str, timeout: float = 10.0) -> bool:
        """等待特定的Toast消息出现，超时返回False"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            toast = self.get_toast(timeout=timeout)
            if toast and expected_text in toast:
                return True
        return False

    def get_all_toasts_in_time(self, timeout: float = 10.0) -> list:
        """返回给定时间内捕获到的所有toast，以列表形式返回"""
        start_time = time.time()
        all_toasts = []
        while time.time() - start_time < timeout:
            toast = self.get_toast(timeout=timeout - (time.time() - start_time))
            if toast:
                all_toasts.append(toast)
        return all_toasts
