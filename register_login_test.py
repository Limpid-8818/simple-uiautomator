import time

import UiAutomatorController


class JiYuLearningAutomator(UiAutomatorController.ui_automator.UiAutomatorController):
    """集寓学习APP自动化测试类"""

    def __init__(self, use_cache: bool = True, cache_dir: str = "ui_cache", device_index: int = 0):
        super().__init__(use_cache, cache_dir, device_index)
        self.package_name = "com.example.jiyulearning"
        self.login_activity = "com.example.jiyulearning.LoginActivity"

    def login(self, username: str, password: str) -> None:
        """登录APP"""
        self.start_app(self.package_name, self.login_activity)

        # 输入用户名和密码
        self.input_text("com.example.jiyulearning:id/et_account", username)
        self.input_text("com.example.jiyulearning:id/et_password", password)

        # 点击登录按钮
        self.click_element(resource_id="com.example.jiyulearning:id/btn_login")
        time.sleep(2)  # 等待登录完成

    def register(self, username: str, level: str, account: str, password: str) -> None:
        """注册新账号"""
        self.start_app(self.package_name, self.login_activity)

        # 跳转到注册页
        self.click_element(resource_id="com.example.jiyulearning:id/rb_register")
        assert self.check_element_exists(resource_id="com.example.jiyulearning:id/et_username"), "未成功跳转到注册页"

        # 输入注册信息
        self.input_text("com.example.jiyulearning:id/et_username", username)
        self.input_text("com.example.jiyulearning:id/et_level", level)
        self.input_text("com.example.jiyulearning:id/et_account", account)
        self.input_text("com.example.jiyulearning:id/et_password", password)
        self.input_text("com.example.jiyulearning:id/et_password_confirm", password)

        # 点击注册按钮
        self.click_element(resource_id="com.example.jiyulearning:id/btn_register")
        time.sleep(1.5)
        self.click_element(resource_id="com.example.jiyulearning:id/rb_login")

    def logout(self) -> None:
        """退出登录"""
        self.click_element(resource_id="com.example.jiyulearning:id/btn_logout")
        time.sleep(1)


def run_registration_login_test():
    """执行注册登录测试流程"""
    automator = JiYuLearningAutomator(use_cache=True)

    try:
        print("开始执行注册登录测试...")

        # 生成唯一的测试账号
        timestamp = str(int(time.time()) % 10000)
        username = f"testUser{timestamp}"
        account = f"test{timestamp}"
        password = "testPassword"
        level = "1"

        # 注册新账号
        automator.register(username, level, account, password)

        # 使用新账号登录
        automator.login(account, password)

        # 验证是否成功登录
        assert automator.check_element_exists(resource_id="com.example.jiyulearning:id/tv_welcome"), "未成功登录"

        print("注册登录流程执行成功！")

    except Exception as e:
        print(f"执行过程中出现错误: {e}")
        # 截图保存错误现场
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        automator.take_screenshot(f"error_screenshot_{timestamp}.png")

    finally:
        # 关闭APP
        automator.close_app(automator.package_name)


if __name__ == "__main__":
    run_registration_login_test()
