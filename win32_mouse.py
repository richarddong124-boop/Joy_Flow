import win32api
import win32con

def move(dx: int, dy: int):
    win32api.mouse_event(
        win32con.MOUSEEVENTF_MOVE,
        dx,
        dy,
        0,
        0
    )

def click_left():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def click_right():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)