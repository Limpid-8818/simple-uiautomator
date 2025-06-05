import UiAutomatorController.ui_automator


def get_toast(timeout=60):
    automator = UiAutomatorController.ui_automator.UiAutomatorController()
    try:
        # 启动Toast监控
        automator.start_toast_monitor()

        # 尝试捕获这段时间出现的所有Toast
        all_toasts = automator.get_all_toasts_in_time(timeout)

        return all_toasts

    finally:
        # 停止Toast监控
        automator.stop_toast_monitor()


if __name__ == '__main__':
    toasts = get_toast(50)
    print(toasts)
