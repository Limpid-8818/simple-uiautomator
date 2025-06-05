import time

import UiAutomatorController.ui_automator


def test_login_with_toast():
    automator = UiAutomatorController.ui_automator.UiAutomatorController()
    try:
        # 启动APP
        automator.start_app("com.example.jiyulearning", "com.example.jiyulearning.LoginActivity")

        # 启动Toast监控
        automator.start_toast_monitor()

        # 输入错误的用户名和密码
        automator.input_text("com.example.jiyulearning:id/et_account", "wrong_username")
        automator.input_text("com.example.jiyulearning:id/et_password", "wrong_password")
        automator.click_element(resource_id="com.example.jiyulearning:id/btn_login")

        # 等待特定Toast出现
        if automator.wait_for_toast("账号不存在~", timeout=10):
            print("成功捕获预期的Toast消息")
        else:
            print("未捕获到预期的Toast消息")

        automator.input_text("com.example.jiyulearning:id/et_account", "123")
        automator.input_text("com.example.jiyulearning:id/et_password", "wrong_password")
        automator.click_element(resource_id="com.example.jiyulearning:id/btn_login")

        # 等待特定Toast出现
        if automator.wait_for_toast("密码错误,请重新输入~", timeout=10):
            print("成功捕获预期的Toast消息")
        else:
            print("未捕获到预期的Toast消息")

    finally:
        # 停止Toast监控
        automator.stop_toast_monitor()
        # 关闭APP
        automator.close_app("com.example.jiyulearning")


if __name__ == '__main__':
    test_login_with_toast()
