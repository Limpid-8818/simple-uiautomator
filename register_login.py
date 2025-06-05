import subprocess
import time
import xml.etree.ElementTree as ET
import os
import json
import re
from typing import Tuple, Optional, Dict, Any


class UiAutomatorController:
    """使用ADB和UI Automator实现的Android UI自动化控制器，支持优化的页面缓存"""

    def __init__(self, use_cache: bool = True, cache_dir: str = "ui_cache"):
        # 验证ADB是否安装
        try:
            subprocess.run(["adb", "version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise EnvironmentError("未找到ADB工具，请确保已安装Android SDK Platform-Tools并添加到PATH中")

        # 验证设备是否连接
        devices = self._get_connected_devices()
        if not devices:
            raise ConnectionError("未检测到已连接的Android设备，请确保设备已开启USB调试并连接到电脑")
        self.device = devices[0]  # 默认使用第一个设备

        # APP相关配置
        self.package_name = "com.example.jiyulearning"
        self.login_activity = "com.example.jiyulearning.LoginActivity"

        # 缓存配置
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

        # 预加载所有已知Activity的缓存
        self.activity_cache = self._preload_activity_cache()

        # 当前Activity
        self.current_activity = None

    def _get_connected_devices(self) -> list:
        """获取已连接的Android设备列表"""
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        lines = result.stdout.strip().split("\n")[1:]  # 跳过标题行
        return [line.split()[0] for line in lines if line.strip() and "device" in line]

    def _get_current_activity(self) -> str:
        """获取当前活动的Activity名称，使用更健壮的解析逻辑"""
        # if self.current_activity:
        #     print(f"使用缓存的Activity名称: {self.current_activity}")
        #     return self.current_activity

        # print("尝试获取当前Activity名称...")
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
                    # print(f"匹配到Activity: {activity}")
                    break

        if match:
            # 清理Activity名称，移除版本号、任务ID等动态部分
            activity = self._sanitize_activity_name(activity)

            self.current_activity = activity
            print(f"成功获取当前Activity: {activity}")
            return activity

        print("警告: 无法获取当前Activity名称！")
        return ""

    def _sanitize_activity_name(self, name: str) -> str:
        """清理Activity名称，移除动态部分并替换非法文件名字符"""
        # 移除类似 " t1234" 或 "/t1234" 的任务ID部分
        name = re.sub(r'\s*/?\s*t\d+', '', name)

        # 替换非法文件名字符
        sanitized = re.sub(r'[\\/:*?"<>|]', '_', name)

        # if name != sanitized:
        #     print(f"清理Activity名称: {name} -> {sanitized}")
        return sanitized

    def _preload_activity_cache(self) -> Dict[str, Dict[str, Any]]:
        """预加载所有已知Activity的缓存"""
        activity_cache = {}
        if not self.use_cache:
            return activity_cache

        for file in os.listdir(self.cache_dir):
            if file.endswith(".json") and not file.startswith("temp_"):
                # 从文件名还原Activity名称（移除扩展名并取消清理）
                device_id, activity_name = file.replace(".json", "").split("_", 1)
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
                # 继续执行，尝试从UI中查找元素

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

    def click_element(self, resource_id: Optional[str] = None,
                      text: Optional[str] = None,
                      class_name: Optional[str] = None) -> None:
        """点击指定元素"""
        x, y = self.find_element(resource_id, text, class_name)
        subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], check=True)
        time.sleep(0.3)  # 进一步减少等待时间

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
        time.sleep(0.3)  # 进一步减少等待时间

    def check_element_exists(self, resource_id: Optional[str] = None,
                             text: Optional[str] = None,
                             class_name: Optional[str] = None) -> bool:
        """检查元素是否存在"""
        try:
            self.find_element(resource_id, text, class_name)
            return True
        except ValueError:
            return False

    def start_app(self) -> None:
        """启动APP"""
        # 启动应用前重置current_activity，确保获取最新的Activity
        self.current_activity = None
        subprocess.run(["adb", "shell", "am", "start", "-n", f"{self.package_name}/{self.login_activity}"], check=True)
        print(f"启动APP: {self.package_name}/{self.login_activity}")
        time.sleep(2)  # 减少启动等待时间

    def close_app(self) -> None:
        """关闭APP"""
        subprocess.run(["adb", "shell", "am", "force-stop", self.package_name], check=True)
        print(f"关闭APP: {self.package_name}")
        time.sleep(0.5)  # 减少关闭等待时间


def run_registration_login_test():
    """执行注册登录测试流程"""
    controller = UiAutomatorController(use_cache=True)  # 启用缓存

    try:
        print("开始执行注册登录测试...")

        # 启动APP
        controller.start_app()

        # 从登录页跳转到注册页
        controller.click_element(resource_id="com.example.jiyulearning:id/rb_register")
        assert controller.check_element_exists(resource_id="com.example.jiyulearning:id/et_username"), "未成功跳转到注册页"

        # 在注册页输入注册信息
        username = "testUser" + str(int(time.time()) % 10000)  # 使用时间戳确保用户名唯一
        level = "1"
        account = "test" + str(int(time.time()) % 10000)  # 使用时间戳确保账号唯一
        password = "testPassword"

        controller.input_text("com.example.jiyulearning:id/et_username", username)
        controller.input_text("com.example.jiyulearning:id/et_level", level)
        controller.input_text("com.example.jiyulearning:id/et_account", account)
        controller.input_text("com.example.jiyulearning:id/et_password", password)
        controller.input_text("com.example.jiyulearning:id/et_password_confirm", password)

        # 点击注册按钮
        controller.click_element(resource_id="com.example.jiyulearning:id/btn_register")
        time.sleep(1.5)  # 减少等待时间

        # 跳转回登录页
        controller.click_element(resource_id="com.example.jiyulearning:id/rb_login")
        assert controller.check_element_exists(resource_id="com.example.jiyulearning:id/et_account"), "未成功跳转到登录页"

        # 在登录页输入注册的账号和密码
        controller.input_text("com.example.jiyulearning:id/et_account", account)
        controller.input_text("com.example.jiyulearning:id/et_password", password)

        # 点击登录按钮
        controller.click_element(resource_id="com.example.jiyulearning:id/btn_login")
        time.sleep(2)  # 减少等待时间

        # 验证是否成功跳转到主界面
        assert controller.check_element_exists(resource_id="com.example.jiyulearning:id/tv_welcome"), "未成功跳转到主界面"

        print("注册登录流程执行成功！")

    except Exception as e:
        print(f"执行过程中出现错误: {e}")
        # 截图保存错误现场
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            screenshot_file = f"error_screenshot_{timestamp}.png"
            subprocess.run(["adb", "shell", "screencap", "-p", f"/sdcard/{screenshot_file}"], check=True)
            subprocess.run(["adb", "pull", f"/sdcard/{screenshot_file}", screenshot_file], check=True)
            print(f"错误截图已保存至: {screenshot_file}")
        except Exception:
            print("无法保存错误截图")
    finally:
        # 关闭APP
        controller.close_app()


if __name__ == "__main__":
    run_registration_login_test()