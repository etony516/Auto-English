import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
from ctypes import wintypes
import keyboard
import mouse
import threading
import time
import json
import os
import pystray
import sys
from PIL import Image, ImageDraw
import pyperclip
import converter

APP_VERSION = "2.2.1"

# quiet-utility 토큰 (표시·설정 창)
UI_BG = "#f8f8f9"
UI_TEXT = "#1f2328"
UI_TEXT_MUTED = "#67696d"
UI_ACCENT = "#526371"
UI_ACCENT_SECONDARY = "#74c2b4"
UI_BORDER = "#cecfd0"
OVERLAY_HANGUL = UI_ACCENT_SECONDARY
OVERLAY_ENGLISH = UI_ACCENT
OVERLAY_UNKNOWN = UI_BORDER

# --- Win32 API ---
user32 = ctypes.WinDLL('user32', use_last_error=True)
imm32 = ctypes.WinDLL('imm32', use_last_error=True)

imm32.ImmGetContext.argtypes = [wintypes.HWND]
imm32.ImmGetContext.restype = wintypes.HANDLE
imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
imm32.ImmReleaseContext.restype = wintypes.BOOL
imm32.ImmGetConversionStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
imm32.ImmGetConversionStatus.restype = wintypes.BOOL
imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]
imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
imm32.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
imm32.ImmGetOpenStatus.restype = wintypes.BOOL

user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short

user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]

user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

if sys.maxsize > 2**32:
    GetWindowLong = user32.GetWindowLongPtrW
    GetWindowLong.restype = ctypes.c_ssize_t
    GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    SetWindowLong = user32.SetWindowLongPtrW
    SetWindowLong.restype = ctypes.c_ssize_t
    SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
else:
    GetWindowLong = user32.GetWindowLongW
    GetWindowLong.restype = wintypes.LONG
    GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    SetWindowLong = user32.SetWindowLongW
    SetWindowLong.restype = wintypes.LONG
    SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]

WM_IME_CONTROL = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
IMC_SETCONVERSIONMODE = 0x0002
IME_CMODE_HANGUL = 0x0001
VK_HANGUL = 0x15

class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT)
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.ChildWindowFromPoint.argtypes = [wintypes.HWND, POINT]
user32.ChildWindowFromPoint.restype = wintypes.HWND
user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ScreenToClient.restype = wintypes.BOOL

# --- 팬텀 키보드 버퍼 (대소문자 복원용) ---
_phantom_buffer = ""
_phantom_lock = threading.Lock()
_restore_timer = None

# --- 선택 영역(Selection) 추적기 ---
_selection_active = False
_last_click_time = 0
_mouse_down_pos = None

def _is_capslock_on():
    return user32.GetKeyState(0x14) & 1

def _phantom_key_hook(event):
    global _phantom_buffer, _typo_running, _selection_active
    if _typo_running:
        return
    if event.event_type != keyboard.KEY_DOWN:
        return
        
    name = event.name
    if not name: return
    
    with _phantom_lock:
        if name == 'space':
            _phantom_buffer += " "
            _selection_active = False
        elif name == 'enter':
            _phantom_buffer += "\n"
            _selection_active = False
        elif name == 'backspace':
            _phantom_buffer = _phantom_buffer[:-1]
            _selection_active = False
        elif name in ('left', 'right', 'up', 'down', 'home', 'end', 'page up', 'page down', 'tab'):
            _phantom_buffer = ""
            if keyboard.is_pressed('shift'):
                _selection_active = True
            else:
                _selection_active = False
        elif name == 'a' and keyboard.is_pressed('ctrl'):
            _selection_active = True
        elif len(name) == 1:
            is_shift = keyboard.is_pressed('shift')
            is_caps = _is_capslock_on()
            if is_shift != is_caps:
                name = name.upper()
            _phantom_buffer += name
            _selection_active = False
            
        if len(_phantom_buffer) > 200:
            _phantom_buffer = _phantom_buffer[-200:]
            
keyboard.hook(_phantom_key_hook)

def _mouse_hook(event):
    global _selection_active, _last_click_time, _mouse_down_pos, _phantom_buffer
    if isinstance(event, mouse.ButtonEvent):
        if event.event_type == 'down' and event.button == 'middle':
            if (app_state.get("enabled") and app_state.get("typo_enabled", True)
                    and app_state.get("trigger_mode") == "middle_click"
                    and check_target_window() and not _typo_running):
                if _selection_active:
                    _request_typo_convert("middle_click")
                else:
                    _debug_log("Middle click ignored: no text selection")
                return
        if event.event_type == 'down':
            now = time.time()
            if now - _last_click_time < 0.4:
                _selection_active = True # 더블 클릭은 단어 선택
            else:
                _selection_active = False # 일반 클릭은 선택 해제 (드래그 전제)
            _last_click_time = now
            _mouse_down_pos = mouse.get_position()
            
            with _phantom_lock:
                _phantom_buffer = ""
        elif event.event_type == 'up':
            if _mouse_down_pos:
                curr = mouse.get_position()
                # 5픽셀 이상 이동했으면 드래그(선택)로 간주
                if abs(curr[0] - _mouse_down_pos[0]) > 5 or abs(curr[1] - _mouse_down_pos[1]) > 5:
                    _selection_active = True
                _mouse_down_pos = None

mouse.hook(_mouse_hook)

def get_active_window_title():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def get_focused_hwnd():
    hwnd = user32.GetForegroundWindow()
    if not hwnd: return None
    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    thread_id = user32.GetWindowThreadProcessId(hwnd, None)
    if user32.GetGUIThreadInfo(thread_id, ctypes.byref(gui_info)):
        return gui_info.hwndFocus if gui_info.hwndFocus else hwnd
    return hwnd

_overlay_exclude_hwnds = set()

def _register_overlay_hwnd(hwnd):
    if hwnd:
        _overlay_exclude_hwnds.add(hwnd)

def _hwnd_at_cursor():
    """마우스 아래 가장 깊은 자식 창 (Chrome 입력 필드 등)."""
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd or hwnd in _overlay_exclude_hwnds:
        return None
    child = hwnd
    for _ in range(16):
        if child in _overlay_exclude_hwnds:
            return None
        client_pt = POINT(pt.x, pt.y)
        user32.ScreenToClient(child, ctypes.byref(client_pt))
        deeper = user32.ChildWindowFromPoint(child, client_pt)
        if not deeper or deeper == child or deeper in _overlay_exclude_hwnds:
            break
        child = deeper
    return child

def _ime_mode_from_hwnd(hwnd):
    if not hwnd:
        return None
    himc = imm32.ImmGetContext(hwnd)
    if himc:
        try:
            if not imm32.ImmGetOpenStatus(himc):
                return 0
            conv = wintypes.DWORD()
            sent = wintypes.DWORD()
            if imm32.ImmGetConversionStatus(himc, ctypes.byref(conv), ctypes.byref(sent)):
                return conv.value
        finally:
            imm32.ImmReleaseContext(hwnd, himc)
    hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
    if hime_wnd:
        return user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
    return None

def _ime_hwnd_candidates_weighted():
    """(hwnd, weight) — 커서·캐럿 우선, 상위 Chrome 창은 낮은 가중치."""
    items = []
    seen = set()

    def add(hwnd, weight):
        if hwnd and hwnd not in seen and hwnd not in _overlay_exclude_hwnds:
            seen.add(hwnd)
            items.append((hwnd, weight))

    fg = user32.GetForegroundWindow()
    if fg:
        gui_info = GUITHREADINFO()
        gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
        thread_id = user32.GetWindowThreadProcessId(fg, None)
        if user32.GetGUIThreadInfo(thread_id, ctypes.byref(gui_info)):
            add(gui_info.hwndCaret, 4)
            add(gui_info.hwndFocus, 3)
    add(_hwnd_at_cursor(), 5)
    if fg:
        add(fg, 1)
    add(get_focused_hwnd(), 2)
    return items

def _is_hangul_from_key_state():
    return (user32.GetKeyState(VK_HANGUL) & 1) != 0

def _read_ime_hangul_imm():
    """여러 HWND 가중 투표로 Imm 상태 판별."""
    hangul_w = 0
    english_w = 0
    for hwnd, weight in _ime_hwnd_candidates_weighted():
        mode = _ime_mode_from_hwnd(hwnd)
        if mode is None:
            continue
        if (mode & IME_CMODE_HANGUL) != 0:
            hangul_w += weight
        else:
            english_w += weight
    if hangul_w == 0 and english_w == 0:
        return None
    if hangul_w > english_w:
        return True
    if english_w > hangul_w:
        return False
    return hangul_w > 0

_ime_display_smooth_buf = []
_ime_display_stable = None
_ime_instant_state = None
_ime_instant_until = 0.0
IME_OVERLAY_DEBOUNCE = 0.12

def _apply_ime_instant_display(hangul):
    """한/영 키 직후 VK 기준으로 표시 즉시 반영."""
    global _ime_instant_state, _ime_instant_until, _ime_display_stable, _ime_display_smooth_buf
    _ime_instant_state = "hangul" if hangul else "english"
    _ime_instant_until = time.time() + 0.25
    _ime_display_stable = hangul
    _ime_display_smooth_buf = [hangul] * 3
    update_tray_icon()

def _schedule_ime_display_from_vk():
    def _work():
        time.sleep(0.025)
        _apply_ime_instant_display(_is_hangul_from_key_state())
    threading.Thread(target=_work, daemon=True).start()

def _ime_overlay_debounce_sec():
    if _ime_instant_state and time.time() < _ime_instant_until:
        return 0.0
    return IME_OVERLAY_DEBOUNCE

def _smooth_ime_for_display(instant_hangul):
    """짧은 노이즈(Chrome Imm 튐) 제거 — 최근 샘플 다수결."""
    global _ime_display_stable
    _ime_display_smooth_buf.append(instant_hangul)
    if len(_ime_display_smooth_buf) > 10:
        _ime_display_smooth_buf.pop(0)
    n = len(_ime_display_smooth_buf)
    hangul_votes = sum(_ime_display_smooth_buf)
    if hangul_votes >= n * 0.7:
        _ime_display_stable = True
        return True
    if hangul_votes <= n * 0.3:
        _ime_display_stable = False
        return False
    if _ime_display_stable is not None:
        return _ime_display_stable
    return instant_hangul

def _read_ime_hangul_for_display():
    imm_hangul = _read_ime_hangul_imm()
    if imm_hangul is None:
        instant = _is_hangul_from_key_state()
    else:
        instant = imm_hangul
    return _smooth_ime_for_display(instant)

def get_ime_display_state(check_active=True):
    """'hangul' | 'english' | 'unknown' — 표시용."""
    if check_active and (not app_state.get("enabled", True) or not check_target_window()):
        return "unknown"
    try:
        if _ime_instant_state and time.time() < _ime_instant_until:
            return _ime_instant_state
        return "hangul" if _read_ime_hangul_for_display() else "english"
    except Exception as ex:
        _debug_log(f"get_ime_display_state error: {ex}")
        return "unknown"

def is_hangul_mode():
    hangul = _read_ime_hangul_imm()
    if hangul is not None:
        return hangul
    return _is_hangul_from_key_state()

def set_ime_to_english():
    try:
        hwnd = get_focused_hwnd()
        if not hwnd: return
        hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime_wnd: return
        current_mode = user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        if current_mode & IME_CMODE_HANGUL:
            new_mode = current_mode & ~IME_CMODE_HANGUL
            user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_SETCONVERSIONMODE, new_mode)
    except Exception as e:
        pass
        
    # 크롬 등 SendMessage가 무시되는 앱을 위해, 상태 점검 후 안 바뀌었으면 물리적 한/영키 전송
    time.sleep(0.02)
    if is_hangul_mode():
        si_tap(0x15)

def set_ime_to_hangul():
    try:
        hwnd = get_focused_hwnd()
        if not hwnd: return
        hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime_wnd: return
        current_mode = user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        if not (current_mode & IME_CMODE_HANGUL):
            new_mode = current_mode | IME_CMODE_HANGUL
            user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_SETCONVERSIONMODE, new_mode)
    except Exception as e:
        pass
        
    # 크롬 등 SendMessage가 무시되는 앱을 위해, 상태 점검 후 안 바뀌었으면 물리적 한/영키 전송
    time.sleep(0.02)
    if not is_hangul_mode():
        si_tap(0x15)

def get_mouse_overlay_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x + 15, pt.y + 15)

# --- Core App State ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(SCRIPT_DIR, "settings.json")
app_state = {
    "enabled": True,
    "enter_mode_enabled": True,
    "enter_mode_default": "english",
    "timer_enabled": False,
    "timer_seconds": 3,
    "target_enabled": False,
    "target_mode": "whitelist",
    "target_keywords": [],
    "smart_mode_enabled": False,
    "smart_mode_default": "hangul",
    "smart_mode_timeout": 300,
    "overlay_enabled": False,
    "typo_enabled": True,
    "typo_hotkey": "ctrl+shift+space",
    "realtime_typo_enabled": False,
    "trigger_mode": "hotkey",
    "trigger_mod_key": "shift",
    "trigger_mod_count": 2,
    "trigger_mod_timeout": 600,
    "trigger_symbol_char": ";",
    "trigger_symbol_count": 3,
    "trigger_rare_key": "scroll lock",
    "trigger_rare_count": 2,
}

last_key_time = time.time()
timer_triggered = False

last_haneng_down_time = 0
is_double_click = False

typing_buffer = []
last_auto_converted_orig = ""
last_auto_convert_time = 0

last_mod_key = None
mod_key_count = 0
last_mod_time = 0

running = True
tray_icon = None

def load_settings():
    global app_state
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                app_state.update(saved)
        except:
            pass

def save_settings():
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(app_state, f, ensure_ascii=False, indent=4)

def check_target_window():
    if not app_state["target_enabled"]:
        return True
    if not app_state["target_keywords"]:
        return app_state.get("target_mode", "whitelist") == "blacklist"
    title = get_active_window_title().lower()
    for kw in app_state["target_keywords"]:
        if kw.lower() in title:
            return app_state.get("target_mode", "whitelist") == "whitelist"
    return app_state.get("target_mode", "whitelist") == "blacklist"

_pressed_mods = set()

MODIFIER_KEY_NAMES = frozenset([
    'shift', 'ctrl', 'alt',
    'left shift', 'right shift', 'left ctrl', 'right ctrl', 'left alt', 'right alt',
])

def _normalize_mod_base(name):
    return name.lower().replace('left ', '').replace('right ', '')

def _mod_trigger_match_event(event_name, trigger_key):
    en = event_name.lower()
    tk = trigger_key.lower()
    if tk.startswith('left ') or tk.startswith('right '):
        return en == tk
    return _normalize_mod_base(en) == tk

def _modifier_tap_identity(event_name, trigger_key):
    tk = trigger_key.lower()
    if tk.startswith('left ') or tk.startswith('right '):
        return event_name.lower()
    return _normalize_mod_base(event_name)

def _handle_modifier_tap(event_name):
    global last_mod_key, mod_key_count, last_mod_time
    if not app_state.get("typo_enabled", True):
        return
    if app_state.get("trigger_mode") != "modifier":
        return
    trigger_key = app_state.get("trigger_mod_key", "shift")
    if not _mod_trigger_match_event(event_name, trigger_key):
        return
    tap_id = _modifier_tap_identity(event_name, trigger_key)
    now = time.time()
    mod_timeout = app_state.get("trigger_mod_timeout", 600) / 1000.0
    target_count = app_state.get("trigger_mod_count", 2)
    if last_mod_key == tap_id and (now - last_mod_time) < mod_timeout:
        mod_key_count += 1
    else:
        last_mod_key = tap_id
        mod_key_count = 1
    last_mod_time = now
    _debug_log(f"Modifier tap {mod_key_count}/{target_count} ({tap_id})")
    if mod_key_count >= target_count:
        _request_typo_convert("modifier")
        mod_key_count = 0

def _keys_to_release_before_macro(trigger_source):
    keys = {'ctrl', 'shift', 'alt', 'left ctrl', 'right ctrl', 'left shift', 'right shift', 'left alt', 'right alt'}
    if trigger_source == "hotkey":
        hk = app_state.get("typo_hotkey", "ctrl+shift+space")
        keys.update(k.strip().lower() for k in hk.split('+') if k.strip())
    return keys

def on_key_event(e):
    global last_key_time, timer_triggered, last_haneng_down_time, is_double_click
    global typing_buffer, last_auto_converted_orig, last_auto_convert_time
    global last_mod_key, mod_key_count, last_mod_time
    global _typo_running, _pressed_mods
    
    if _typo_running:
        return
        
    name = e.name.lower()
    
    if e.event_type == 'up':
        if name in MODIFIER_KEY_NAMES:
            mod_base = _normalize_mod_base(name)
            if mod_base in _pressed_mods:
                _pressed_mods.remove(mod_base)
                
    if e.event_type == 'down':
        if name in MODIFIER_KEY_NAMES:
            mod_base = _normalize_mod_base(name)
            if mod_base in _pressed_mods:
                return
            _pressed_mods.add(mod_base)
            if app_state["enabled"]:
                _handle_modifier_tap(e.name)

        if time.time() - last_key_time > 2.0:
            typing_buffer.clear()
        last_key_time = time.time()
        timer_triggered = False
        
    if not app_state["enabled"]:
        return
        
    if e.event_type == 'down':
        name = e.name.lower()
        if name == 'backspace':
            if typing_buffer:
                typing_buffer.pop()
            mod_key_count = 0
        elif name in ['space', 'enter']:
            if app_state.get("typo_enabled", True) and app_state.get("realtime_typo_enabled", False) and check_target_window() and name == 'space':
                word = ''.join(typing_buffer)
                if word:
                    is_typo, target_lang, chars_to_delete = converter.check_realtime_typo(word, is_hangul_mode())
                    if is_typo:
                        threading.Thread(target=do_realtime_convert, args=(word, target_lang, chars_to_delete), daemon=True).start()
            typing_buffer.clear()
            mod_key_count = 0
        elif len(name) == 1:
            typing_buffer.append(name)

            if app_state.get("typo_enabled", True) and app_state.get("trigger_mode") == "symbol":
                sym_char = app_state.get("trigger_symbol_char", ";")
                sym_count = app_state.get("trigger_symbol_count", 3)
                if sym_char and len(sym_char) == 1 and sym_count > 0:
                    if len(typing_buffer) >= sym_count:
                        if all(c == sym_char for c in typing_buffer[-sym_count:]):
                            def _erase_symbol_keys():
                                for _ in range(sym_count):
                                    si_tap(VK_BACK)
                                    time.sleep(0.01)
                            _request_typo_convert("symbol", pre_job=_erase_symbol_keys)
                            typing_buffer.clear()
            mod_key_count = 0
        elif name in MODIFIER_KEY_NAMES:
            pass
        else:
            if name not in ['left', 'right', 'up', 'down', 'page up', 'page down', 'home', 'end', 'tab', 'esc']:
                typing_buffer.clear()
                mod_key_count = 0
                
    is_haneng_key = e.name in ['한/영', 'hangul', 'right alt', 'alt gr']
    
    if is_haneng_key and e.event_type == 'up':
        if app_state.get("smart_mode_enabled", False) and check_target_window():
            default_lang = app_state.get("smart_mode_default", "hangul")
            if is_double_click:
                if default_lang == "hangul":
                    set_ime_to_english()
                else:
                    set_ime_to_hangul()
            else:
                if default_lang == "hangul":
                    set_ime_to_hangul()
                else:
                    set_ime_to_english()
        _schedule_ime_display_from_vk()
        if app_state.get("smart_mode_enabled", False) and check_target_window():
            return
    
    if app_state.get("smart_mode_enabled", False) and check_target_window():
        if is_haneng_key:
            now = time.time()
            if e.event_type == 'down':
                diff_ms = (now - last_haneng_down_time) * 1000
                if diff_ms <= app_state.get("smart_mode_timeout", 300):
                    is_double_click = True
                else:
                    is_double_click = False
                last_haneng_down_time = now
                return
            
    if e.name == 'enter' and e.event_type == 'down':
        if app_state.get("enter_mode_enabled", True) and check_target_window():
            if app_state.get("enter_mode_default", "english") == "english":
                set_ime_to_english()
            else:
                set_ime_to_hangul()

def do_realtime_convert(word, target_lang, chars_to_delete):
    global last_auto_converted_orig, last_auto_convert_time
    try:
        time.sleep(0.01)
        # 스페이스바 방금 쳤으므로 지워야 할 글자수 + 1 (스페이스)
        backspaces = chars_to_delete + 1
        for _ in range(backspaces):
            si_tap(VK_BACK)
            time.sleep(0.01)
            
        if target_lang == "hangul":
            converted = converter.english_to_korean(word)
        else:
            converted = word # 버퍼(word)는 항상 영어 키스트로크이므로, 영어가 타겟이면 그대로 사용
            
        last_auto_converted_orig = word
        last_auto_convert_time = time.time()
        
        orig_clip = safe_paste()
        safe_copy(converted)
        time.sleep(0.02)
        si_hotkey(VK_CONTROL, VK_V)
        time.sleep(0.02)
        si_tap(VK_SPACE)
        
        if target_lang == "hangul":
            set_ime_to_hangul()
        else:
            set_ime_to_english()
            
        def restore_clip():
            time.sleep(0.5)
            safe_copy(orig_clip)
        threading.Thread(target=restore_clip, daemon=True).start()
    except Exception as ex:
        pass

# --- SendInput API (Hardware Scan Code 포함, 크롬 등 모던 앱 호환) ---
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]

class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _INPUTunion)]

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
user32.MapVirtualKeyW.restype = ctypes.c_uint

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
MAPVK_VK_TO_VSC = 0

VK_BACK = 0x08
VK_TAB = 0x09
VK_ENTER = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SPACE = 0x20
VK_HOME = 0x24
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_DELETE = 0x2E
VK_C = 0x43
VK_V = 0x56
VK_X = 0x58
VK_CAPITAL = 0x14
VK_SCROLL = 0x91
VK_OEM_3 = 0xC0
VK_OEM_6 = 0xDD

EXTENDED_KEYS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x91}

RARE_KEY_VK = {
    'scroll lock': VK_SCROLL,
    ']': VK_OEM_6,
    '`': VK_OEM_3,
    'caps lock': VK_CAPITAL,
}

STREAK_TIMEOUT = 0.8

def _make_input(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ii.ki.wVk = vk
    inp.ii.ki.wScan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    flags = 0
    if up:
        flags |= KEYEVENTF_KEYUP
    if vk in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp.ii.ki.dwFlags = flags
    inp.ii.ki.time = 0
    inp.ii.ki.dwExtraInfo = 0
    return inp

def si_press(vk):
    inp = _make_input(vk)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def si_release(vk):
    inp = _make_input(vk, up=True)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def si_tap(vk, delay=0.01):
    si_press(vk)
    time.sleep(delay)
    si_release(vk)

def si_hotkey(*vks, delay=0.02):
    for vk in vks:
        si_press(vk)
        time.sleep(0.01)
    time.sleep(delay)
    for vk in reversed(vks):
        si_release(vk)

def release_all_modifiers():
    si_release(VK_SHIFT)
    si_release(VK_CONTROL)
    # VK_MENU(Alt)는 제외: Alt UP 이벤트는 Windows의 메뉴 활성화를 해서 방해됨
    
    # OS 레벨에서 논리적/물리적 키 상태가 완전히 해제될 때까지 폴링 (동기화)
    end_time = time.time() + 0.5
    while time.time() < end_time:
        if not (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) and \
           not (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
            break
        time.sleep(0.001)

def safe_paste():
    for _ in range(10):
        try:
            return pyperclip.paste()
        except Exception:
            time.sleep(0.02)
    return ""

def safe_copy(text):
    for _ in range(10):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(0.02)
    return False

# --- WH_KEYBOARD_LL (희귀키 연타 트리거, 키 suppress) ---
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_INJECTED = 0x10

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

_ll_hook_proc_ref = None
_ll_hook_handle = None
_ll_hook_thread = None
_ll_hook_thread_id = None

_streak_count = 0
_streak_last_time = 0.0
_streak_captured_clip = None
_streak_had_selection = False

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelKeyboardProc, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_long
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short

def _get_ll_trigger_vk():
    if app_state.get("trigger_mode") != "rare":
        return 0
    rk = app_state.get("trigger_rare_key", "scroll lock").lower()
    return RARE_KEY_VK.get(rk, 0)

def _get_streak_target():
    if app_state.get("trigger_mode") == "rare":
        return max(1, int(app_state.get("trigger_rare_count", 2)))
    return 0

def _reset_streak():
    global _streak_count, _streak_last_time, _streak_captured_clip, _streak_had_selection
    _streak_count = 0
    _streak_last_time = 0.0
    _streak_captured_clip = None
    _streak_had_selection = False

def _ll_keyboard_proc(nCode, wParam, lParam):
    global _streak_count, _streak_last_time, _streak_captured_clip, _streak_had_selection
    if nCode < 0:
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    if wParam not in (WM_KEYDOWN, WM_SYSKEYDOWN):
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
    if kb.flags & LLKHF_INJECTED:
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    if _typo_running:
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    mode = app_state.get("trigger_mode")
    if mode != "rare":
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    if not app_state.get("enabled") or not app_state.get("typo_enabled", True):
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    if not check_target_window():
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    trigger_vk = _get_ll_trigger_vk()
    if trigger_vk == 0 or kb.vkCode != trigger_vk:
        return user32.CallNextHookEx(_ll_hook_handle, nCode, wParam, lParam)

    now = time.time()
    if _streak_count > 0 and (now - _streak_last_time) > STREAK_TIMEOUT:
        _reset_streak()

    _streak_count += 1
    _streak_last_time = now
    target = _get_streak_target()

    if _streak_count >= target:
        _reset_streak()
        _request_typo_convert("rare")

    return 1

def _ll_hook_thread_fn():
    global _ll_hook_handle, _ll_hook_proc_ref
    _ll_hook_proc_ref = LowLevelKeyboardProc(_ll_keyboard_proc)
    _ll_hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _ll_hook_proc_ref, None, 0)
    if not _ll_hook_handle:
        _debug_log("SetWindowsHookExW(LL) failed")
        return
    _debug_log("LL keyboard hook started")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    if _ll_hook_handle:
        user32.UnhookWindowsHookEx(_ll_hook_handle)
        _ll_hook_handle = None
    _debug_log("LL keyboard hook stopped")

def stop_ll_hook():
    global _ll_hook_thread, _ll_hook_thread_id
    if _ll_hook_thread_id is not None:
        user32.PostThreadMessageW(_ll_hook_thread_id, 0x0012, 0, 0)
        _ll_hook_thread_id = None
        _ll_hook_thread = None
        time.sleep(0.05)
    _reset_streak()

def apply_ll_hook():
    global _ll_hook_thread, _ll_hook_thread_id
    stop_ll_hook()
    mode = app_state.get("trigger_mode")
    if app_state.get("typo_enabled", True) and mode == "rare":
        try:
            t = threading.Thread(target=_ll_hook_thread_fn, daemon=True)
            t.start()
            _ll_hook_thread = t
            _ll_hook_thread_id = t.native_id
        except Exception as e:
            _debug_log(f"LL hook start failed: {e}")

_typo_running = False
_last_typo_finish_time = 0.0
TYPO_TRIGGER_COOLDOWN = 0.8

def _request_typo_convert(source, pre_captured_text=None, pre_job=None):
    if _typo_running:
        _debug_log(f"Typo blocked ({source}): busy")
        return
    if time.time() - _last_typo_finish_time < TYPO_TRIGGER_COOLDOWN:
        _debug_log(f"Typo blocked ({source}): cooldown")
        return
    threading.Thread(
        target=lambda: on_typo_hotkey(
            pre_captured_text=pre_captured_text,
            trigger_source=source,
            pre_job=pre_job,
        ),
        daemon=True,
    ).start()

def on_typo_hotkey(pre_captured_text=None, trigger_source="unknown", pre_job=None):
    global _typo_running, _phantom_buffer
    global mod_key_count, last_mod_key, _last_typo_finish_time
    if _typo_running:
        return
    if time.time() - _last_typo_finish_time < TYPO_TRIGGER_COOLDOWN:
        _debug_log(f"Typo aborted ({trigger_source}): cooldown")
        return
    _typo_running = True
    mod_key_count = 0
    last_mod_key = None

    try:
        _debug_log(f"--- Typo Triggered ({trigger_source}) ---")
        if not app_state.get("typo_enabled", True):
            _debug_log("Aborted: disabled")
            return

        if pre_job:
            pre_job()
            
        # 트리거 키가 모두 떼질 때까지 대기
        keys_to_wait = _keys_to_release_before_macro(trigger_source)

        timeout = time.time() + 3.0
        while time.time() < timeout:
            any_pressed = False
            for k in keys_to_wait:
                try:
                    if keyboard.is_pressed(k):
                        any_pressed = True
                        break
                except:
                    pass
            if not any_pressed:
                break
            time.sleep(0.01)

        time.sleep(0.01)
        release_all_modifiers()
        _debug_log("Modifiers released, starting macro")

        orig_clip = safe_paste()

        if pre_captured_text is not None:
            if not pre_captured_text or pre_captured_text.isspace():
                _debug_log("Empty pre-captured selection, aborting")
                safe_copy(orig_clip)
                return
            _debug_log("Using pre-captured selection (LL hook)")
            converted, target_lang = converter.auto_convert(pre_captured_text)
            final_text = converted
        else:
            # Step 1: 현재 선택된 텍스트가 있는지 확인 (수동 드래그)
            seq_before = user32.GetClipboardSequenceNumber()
            si_hotkey(VK_CONTROL, VK_C)
            
            clip1 = ""
            poll_end = time.time() + 0.5
            while time.time() < poll_end:
                if user32.GetClipboardSequenceNumber() != seq_before:
                    time.sleep(0.02)
                    clip1 = safe_paste()
                    break
                time.sleep(0.002)
                
            is_real_drag = _selection_active
            
            if is_real_drag:
                # 수동 드래그: clip1 전체를 변환
                if not clip1 or clip1.isspace():
                    _debug_log("Empty selection, aborting")
                    safe_copy(orig_clip)
                    return
                
                _debug_log("Detected REAL DRAG (via user input tracking)")
                target_text = clip1
                converted, target_lang = converter.auto_convert(target_text)
                final_text = converted
                
            else:
                # 선택 없음: 커서 앞부분(clip2)에서 마지막 단어만 변환
                # Step 2: 현재 줄 텍스트 전체(커서 앞부분) 복사
                si_hotkey(VK_SHIFT, VK_HOME)
                time.sleep(0.02)
                
                seq_before = user32.GetClipboardSequenceNumber()
                si_hotkey(VK_CONTROL, VK_C)
                
                clip2 = ""
                poll_end = time.time() + 0.5
                while time.time() < poll_end:
                    if user32.GetClipboardSequenceNumber() != seq_before:
                        time.sleep(0.02)
                        clip2 = safe_paste()
                        break
                    time.sleep(0.002)
                
                if not clip2 or clip2.isspace():
                    _debug_log("No text found on line, aborting safely")
                    safe_copy(orig_clip)
                    return

                _debug_log("Extracting last word from line")
                import re
                m = re.search(r'(\w+)([^\w]*)$', clip2)
                if not m:
                    # 단어가 없으면 전체 변환
                    converted, target_lang = converter.auto_convert(clip2)
                    final_text = converted
                else:
                    prefix = clip2[:m.start(1)]
                    target_text = m.group(1)
                    trailing = m.group(2)
                    
                    converted, target_lang = converter.auto_convert(target_text)
                    
                    # 팬텀 버퍼를 이용한 대소문자 복원
                    global _phantom_buffer
                    with _phantom_lock:
                        buf = _phantom_buffer.lower()
                        idx = buf.rfind(converted.lower())
                        if idx != -1 and idx >= len(buf) - len(converted) - 10:
                            converted = _phantom_buffer[idx:idx+len(converted)]
                    
                    final_text = prefix + converted + trailing
                
        _debug_log(f"Final text to paste: {repr(final_text)}")
            
        if not safe_copy(final_text):
            _debug_log("Failed to write to clipboard, aborting safely")
            safe_copy(orig_clip)
            return
            
        time.sleep(0.04)
        si_hotkey(VK_CONTROL, VK_V)
        time.sleep(0.02)
        
        if target_lang == "hangul":
            set_ime_to_hangul()
        else:
            set_ime_to_english()
        
        global _restore_timer
        if _restore_timer:
            _restore_timer.cancel()
            
        def restore_clip():
            safe_copy(orig_clip)
            
        # 에디터가 Ctrl+V를 처리하기 전에 클립보드가 원상복구되는 Race Condition 방지 (1.5s)
        _restore_timer = threading.Timer(1.5, restore_clip)
        _restore_timer.start()
        
    except Exception as e:
        _debug_log(f"Exception: {e}")
    finally:
        _pressed_mods.clear()
        _reset_streak()
        _last_typo_finish_time = time.time()
        _typo_running = False

def _debug_log(msg):
    try:
        with open("typo_debug.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} - {msg}\n")
    except:
        pass

_hotkey_thread_id = None

def _hotkey_listener_thread(hk_str):
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000
    
    key_map = {'ctrl': MOD_CONTROL, 'shift': MOD_SHIFT, 'alt': MOD_ALT, 'windows': MOD_WIN, 'win': MOD_WIN}
    VK_MAP = {'space': 0x20, 'enter': 0x0D, 'tab': 0x09, 'escape': 0x1B, 'backspace': 0x08, 'delete': 0x2E, 'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27}
    
    mods = MOD_NOREPEAT
    vk = 0
    
    parts = [p.strip().lower() for p in hk_str.split('+')]
    for p in parts:
        if p in key_map:
            mods |= key_map[p]
        elif p in VK_MAP:
            vk = VK_MAP[p]
        elif len(p) == 1 and 'a' <= p <= 'z':
            vk = ord(p.upper())
        elif len(p) == 1 and '0' <= p <= '9':
            vk = ord(p)
        else:
            try:
                vk = user32.VkKeyScanW(ord(p)) & 0xFF
            except:
                pass
                
    if vk == 0:
        _debug_log(f"Invalid hotkey: {hk_str}")
        return
        
    if not user32.RegisterHotKey(None, 1, mods, vk):
        _debug_log(f"RegisterHotKey failed for {hk_str}")
        return
        
    _debug_log(f"RegisterHotKey success: {hk_str}")
    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == 0x0312: # WM_HOTKEY
            _request_typo_convert("hotkey")
            
    user32.UnregisterHotKey(None, 1)
    _debug_log(f"Hotkey un-registered: {hk_str}")

def apply_hotkeys():
    global _hotkey_thread_id
    keyboard.unhook_all_hotkeys()
    
    if _hotkey_thread_id is not None:
        user32.PostThreadMessageW(_hotkey_thread_id, 0x0012, 0, 0) # WM_QUIT
        _hotkey_thread_id = None
        time.sleep(0.1)
        
    if app_state.get("typo_enabled", True) and app_state.get("trigger_mode", "hotkey") == "hotkey":
        hk = app_state.get("typo_hotkey", "ctrl+shift+space")
        try:
            t = threading.Thread(target=_hotkey_listener_thread, args=(hk,), daemon=True)
            t.start()
            _hotkey_thread_id = t.native_id
        except Exception as e:
            _debug_log(f"Hotkey register failed: {e}")

    apply_ll_hook()

# --- Overlay Widget ---
class OverlayWidget:
    def __init__(self, root):
        self.toplevel = tk.Toplevel(root)
        self.toplevel.overrideredirect(True)
        self.toplevel.attributes("-topmost", True)
        
        TRANS_COLOR = "#000001"
        self.toplevel.config(bg=TRANS_COLOR)
        
        self.canvas = tk.Canvas(self.toplevel, width=14, height=14, bg=TRANS_COLOR, highlightthickness=0)
        self.canvas.pack()
        self.circle = self.canvas.create_oval(1, 1, 13, 13, fill=OVERLAY_HANGUL, outline=TRANS_COLOR)
        self.square = self.canvas.create_rectangle(1, 1, 13, 13, fill=OVERLAY_ENGLISH, outline=TRANS_COLOR)
        self.triangle = self.canvas.create_polygon(7, 1, 1, 13, 13, 13, fill=OVERLAY_UNKNOWN, outline=TRANS_COLOR)
        self.canvas.itemconfig(self.square, state="hidden")
        self.canvas.itemconfig(self.triangle, state="hidden")
        
        self.toplevel.update_idletasks()
        
        self.toplevel.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.toplevel.attributes("-alpha", 0.0)
        
        hwnd = self.toplevel.winfo_id()
        parent_hwnd = user32.GetParent(hwnd)
        target_hwnd = parent_hwnd if parent_hwnd else hwnd
        
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_NOACTIVATE = 0x08000000
        
        ex_style = GetWindowLong(target_hwnd, GWL_EXSTYLE)
        SetWindowLong(target_hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        _register_overlay_hwnd(hwnd)
        _register_overlay_hwnd(parent_hwnd)
        _register_overlay_hwnd(target_hwnd)
        
        self._last_ime_state = None
        self._display_ime_state = None
        self._pending_ime_state = None
        self._pending_ime_since = 0.0
        self.update_loop()
        
    def update_loop(self):
        if not running:
            return
            
        try:
            if app_state.get("overlay_enabled", False) and app_state["enabled"] and check_target_window():
                hwnd_inner = self.toplevel.winfo_id()
                parent_hwnd = user32.GetParent(hwnd_inner)
                target_hwnd = parent_hwnd if parent_hwnd else hwnd_inner

                pos = get_mouse_overlay_pos()
                if pos:
                    x, y = pos
                    
                    HWND_TOPMOST = -1
                    SWP_NOSIZE = 0x0001
                    SWP_NOACTIVATE = 0x0010
                    # 항상 최상단을 유지하도록 HWND_TOPMOST 강제 지정 (SWP_NOZORDER 제거)
                    user32.SetWindowPos(target_hwnd, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    
                    # 반투명도 설정 (조금 덜 투명하게 80%)
                    self.toplevel.attributes("-alpha", 0.8)
                    
                    ime_state = get_ime_display_state(check_active=False)
                    now = time.time()
                    if ime_state != self._display_ime_state:
                        if self._pending_ime_state != ime_state:
                            self._pending_ime_state = ime_state
                            self._pending_ime_since = now
                        elif (now - self._pending_ime_since) >= _ime_overlay_debounce_sec():
                            self._display_ime_state = ime_state
                            if ime_state != self._last_ime_state:
                                self._last_ime_state = ime_state
                                labels = {"hangul": "한글", "english": "영어", "unknown": "불명"}
                                _debug_log(
                                    f"Overlay: {labels.get(ime_state, ime_state)} "
                                    f"win={get_active_window_title()!r}"
                                )
                    else:
                        self._pending_ime_state = None

                    shape = self._display_ime_state if self._display_ime_state is not None else ime_state
                    self._apply_overlay_shape(shape)
            else:
                self.toplevel.attributes("-alpha", 0.0)
        except Exception:
            pass
            
        self.toplevel.after(10, self.update_loop)

    def _apply_overlay_shape(self, state):
        self.canvas.itemconfig(self.circle, state="hidden")
        self.canvas.itemconfig(self.square, state="hidden")
        self.canvas.itemconfig(self.triangle, state="hidden")
        if state == "hangul":
            self.canvas.itemconfig(self.circle, state="normal")
        elif state == "english":
            self.canvas.itemconfig(self.square, state="normal")
        elif state == "unknown":
            self.canvas.itemconfig(self.triangle, state="normal")

# --- Tray Icon ---
def create_circle_image(color):
    image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=color, outline="white")
    return image

def create_square_image(color):
    image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 52, 52), fill=color, outline="white")
    return image

def create_triangle_image(color):
    image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(32, 10), (10, 54), (54, 54)], fill=color, outline="white")
    return image

ICON_HANGUL = create_circle_image(OVERLAY_HANGUL)
ICON_ENGLISH = create_square_image(OVERLAY_ENGLISH)
ICON_UNKNOWN = create_triangle_image(OVERLAY_UNKNOWN)

def _app_tray_title(status=""):
    base = f"자동 영타 전환기 v{APP_VERSION}"
    return f"{base} ({status})" if status else base

def update_tray_icon():
    global tray_icon
    if not tray_icon or not getattr(tray_icon, '_running', False):
        return
    if not app_state["enabled"] or not check_target_window():
        tray_icon.icon = ICON_UNKNOWN
        tray_icon.title = _app_tray_title("비활성")
        return
    state = get_ime_display_state(check_active=False)
    if state == "hangul":
        tray_icon.icon = ICON_HANGUL
        tray_icon.title = _app_tray_title("한글")
    elif state == "english":
        tray_icon.icon = ICON_ENGLISH
        tray_icon.title = _app_tray_title("영어")
    else:
        tray_icon.icon = ICON_UNKNOWN
        tray_icon.title = _app_tray_title("상태 불명")

def setup_tray(root):
    global tray_icon
    def on_show(icon, item):
        def show_window():
            root.deiconify()
            root.attributes("-alpha", 1.0)
            root.lift()
            root.focus_force()
        root.after(0, show_window)
    def on_quit(icon, item):
        icon.stop()
        global running
        running = False
        save_settings()
        os._exit(0)
        
    menu = pystray.Menu(
        pystray.MenuItem("설정 열기", on_show, default=True),
        pystray.MenuItem("종료", on_quit)
    )
    tray_icon = pystray.Icon("AutoEng", ICON_UNKNOWN, _app_tray_title(), menu)

def timer_thread():
    global timer_triggered, tray_icon
    while running:
        time.sleep(0.5)
        
        if tray_icon and getattr(tray_icon, '_running', False):
            update_tray_icon()
                
        if app_state["enabled"] and app_state["timer_enabled"] and not timer_triggered:
            if time.time() - last_key_time >= app_state["timer_seconds"]:
                if check_target_window():
                    set_ime_to_english()
                timer_triggered = True

# --- GUI ---
def _apply_ui_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    root.configure(bg=UI_BG)
    style.configure('.', background=UI_BG, foreground=UI_TEXT)
    style.configure('TFrame', background=UI_BG)
    style.configure('TLabel', background=UI_BG, foreground=UI_TEXT)
    style.configure('Muted.TLabel', background=UI_BG, foreground=UI_TEXT_MUTED)
    style.configure('Accent.TLabel', background=UI_BG, foreground=UI_ACCENT_SECONDARY)
    style.configure('TLabelframe', background=UI_BG, bordercolor=UI_BORDER, relief='solid')
    style.configure('TLabelframe.Label', background=UI_BG, foreground=UI_ACCENT, font=('Segoe UI', 9, 'bold'))
    style.configure('TCheckbutton', background=UI_BG, foreground=UI_TEXT)
    style.configure('TRadiobutton', background=UI_BG, foreground=UI_TEXT)
    style.configure('Accent.TCheckbutton', background=UI_BG, foreground=UI_ACCENT, font=('Segoe UI', 10, 'bold'))
    style.configure('TButton', padding=(10, 4))
    style.configure('TEntry', fieldbackground='#ffffff')

class AutoEngApp:
    def __init__(self, root):
        self.root = root
        _apply_ui_theme(root)
        self.root.title(f"자동 영타 전환기 v{APP_VERSION}")
        self.root.geometry("480x720")
        self.root.minsize(420, 520)
        self.root.resizable(True, True)
        
        load_settings()
        apply_hotkeys()

        outer = ttk.Frame(root)
        outer.pack(fill='both', expand=True)

        self._scroll_canvas = tk.Canvas(outer, highlightthickness=0, bg=UI_BG, bd=0)
        vsb = ttk.Scrollbar(outer, orient='vertical', command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._scroll_canvas.pack(side='left', fill='both', expand=True)

        content = ttk.Frame(self._scroll_canvas)
        self._scroll_window = self._scroll_canvas.create_window((0, 0), window=content, anchor='nw')

        def _on_content_configure(event):
            self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox('all'))
        content.bind('<Configure>', _on_content_configure)

        def _on_canvas_configure(event):
            self._scroll_canvas.itemconfig(self._scroll_window, width=event.width)
        self._scroll_canvas.bind('<Configure>', _on_canvas_configure)

        def _on_mousewheel(event):
            self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        self._scroll_canvas.bind_all('<MouseWheel>', _on_mousewheel)
        
        self.var_enabled = tk.BooleanVar(value=app_state["enabled"])
        chk_main = ttk.Checkbutton(content, text="기능 켜기 (전체 활성화)", style='Accent.TCheckbutton', variable=self.var_enabled, command=self.update_settings)
        chk_main.pack(pady=10, padx=15, anchor='w')
        
        frame_enter = ttk.LabelFrame(content, text="엔터(Enter) 키 동작 설정")
        frame_enter.pack(fill='x', pady=5, padx=15)
        self.var_enter_enabled = tk.BooleanVar(value=app_state.get("enter_mode_enabled", True))
        ttk.Checkbutton(frame_enter, text="엔터 키 입력 후 자동으로 언어 변경하기", variable=self.var_enter_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        
        f_en_opts = ttk.Frame(frame_enter)
        f_en_opts.pack(anchor='w', fill='x', padx=25, pady=(0, 10))
        ttk.Label(f_en_opts, text="엔터 후 언어:").pack(side='left')
        self.var_enter_default = tk.StringVar(value=app_state.get("enter_mode_default", "english"))
        ttk.Radiobutton(f_en_opts, text="한글", variable=self.var_enter_default, value="hangul", command=self.update_settings).pack(side='left', padx=(5, 0))
        ttk.Radiobutton(f_en_opts, text="영문", variable=self.var_enter_default, value="english", command=self.update_settings).pack(side='left', padx=5)
        
        frame_timer = ttk.LabelFrame(content, text="타이머 설정")
        frame_timer.pack(fill='x', pady=5, padx=15)
        self.var_timer_enabled = tk.BooleanVar(value=app_state["timer_enabled"])
        ttk.Checkbutton(frame_timer, text="유휴 시간 후 자동으로 언어 변경 켜기", variable=self.var_timer_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        f_t_sec = ttk.Frame(frame_timer)
        f_t_sec.pack(anchor='w', padx=25, pady=(0, 10))
        ttk.Label(f_t_sec, text="키보드 입력 없이").pack(side='left')
        self.entry_sec = ttk.Entry(f_t_sec, width=5)
        self.entry_sec.insert(0, str(app_state["timer_seconds"]))
        self.entry_sec.pack(side='left', padx=5)
        ttk.Label(f_t_sec, text="초 경과 시 '영문'으로 전환").pack(side='left')
        self.entry_sec.bind("<KeyRelease>", self.update_settings_delayed)
        
        frame_haneng = ttk.LabelFrame(content, text="한/영 키 커스텀 더블클릭 설정")
        frame_haneng.pack(fill='x', pady=5, padx=15)
        self.var_smart_mode = tk.BooleanVar(value=app_state.get("smart_mode_enabled", False))
        ttk.Checkbutton(frame_haneng, text="한/영 키 커스텀 동작 사용하기", variable=self.var_smart_mode, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        f_he_opts = ttk.Frame(frame_haneng)
        f_he_opts.pack(anchor='w', fill='x', padx=25, pady=(0, 5))
        ttk.Label(f_he_opts, text="한 번 누를 때 언어:").pack(side='left')
        self.var_default_lang = tk.StringVar(value=app_state.get("smart_mode_default", "hangul"))
        ttk.Radiobutton(f_he_opts, text="한글", variable=self.var_default_lang, value="hangul", command=self.update_lang_label).pack(side='left', padx=(5, 0))
        ttk.Radiobutton(f_he_opts, text="영문", variable=self.var_default_lang, value="english", command=self.update_lang_label).pack(side='left', padx=5)
        
        f_he_double = ttk.Frame(frame_haneng)
        f_he_double.pack(anchor='w', fill='x', padx=25, pady=(0, 5))
        self.var_double_lang = tk.StringVar()
        ttk.Label(f_he_double, textvariable=self.var_double_lang, style='Accent.TLabel').pack(side='left')
        
        f_he_time = ttk.Frame(frame_haneng)
        f_he_time.pack(anchor='w', fill='x', padx=25, pady=(0, 10))
        ttk.Label(f_he_time, text="더블클릭 인식 제한 시간(ms):").pack(side='left')
        self.entry_timeout = ttk.Entry(f_he_time, width=6)
        self.entry_timeout.insert(0, str(app_state.get("smart_mode_timeout", 300)))
        self.entry_timeout.pack(side='left', padx=5)
        self.entry_timeout.bind("<KeyRelease>", self.update_settings_delayed)
        
        frame_overlay = ttk.LabelFrame(content, text="상태 표시 위젯 (플로팅 아이콘)")
        frame_overlay.pack(fill='x', pady=5, padx=15)
        self.var_overlay_enabled = tk.BooleanVar(value=app_state.get("overlay_enabled", False))
        ttk.Checkbutton(frame_overlay, text="커서(마우스) 주변에 한/영 상태 아이콘 띄우기", variable=self.var_overlay_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        ttk.Label(frame_overlay, text="한글: 청록 원 / 영어: 슬레이트 사각형 / 비활성·불명: 회색 삼각형", style='Muted.TLabel').pack(anchor='w', padx=25, pady=(0, 10))

        frame_target = ttk.LabelFrame(content, text="대상 프로그램 설정 (창 제목 기준)")
        frame_target.pack(fill='x', pady=5, padx=15)
        self.var_target_enabled = tk.BooleanVar(value=app_state["target_enabled"])
        ttk.Checkbutton(frame_target, text="특정 창(프로그램)에서 필터링 작동하기", variable=self.var_target_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        
        self.var_target_mode = tk.StringVar(value=app_state.get("target_mode", "whitelist"))
        f_mode = ttk.Frame(frame_target)
        f_mode.pack(anchor='w', fill='x', padx=25, pady=(0, 5))
        ttk.Radiobutton(f_mode, text="화이트리스트", variable=self.var_target_mode, value="whitelist", command=self.update_settings).pack(side='left')
        ttk.Radiobutton(f_mode, text="블랙리스트", variable=self.var_target_mode, value="blacklist", command=self.update_settings).pack(side='left', padx=10)
        
        f_kw = ttk.Frame(frame_target)
        f_kw.pack(fill='x', padx=25, pady=5)
        self.entry_kw = ttk.Entry(f_kw)
        self.entry_kw.pack(side='left', fill='x', expand=True)
        self.entry_kw.bind("<Return>", lambda e: self.add_kw())
        ttk.Button(f_kw, text="추가", command=self.add_kw, width=6).pack(side='left', padx=5)
        self.listbox_kw = tk.Listbox(frame_target, height=5)
        self.listbox_kw.pack(fill='x', padx=25, pady=(0, 5))
        for kw in app_state["target_keywords"]:
            self.listbox_kw.insert(tk.END, kw)
        ttk.Button(frame_target, text="선택 삭제", command=self.del_kw).pack(anchor='e', padx=25, pady=(0, 10))
        
        frame_typo = ttk.LabelFrame(content, text="수동 오타 변환 트리거 설정")
        frame_typo.pack(fill='x', pady=5, padx=15)
        self.var_typo_enabled = tk.BooleanVar(value=app_state.get("typo_enabled", True))
        self.chk_typo = ttk.Checkbutton(frame_typo, text="수동 오타 변환 기능 사용 (마스터 스위치)",
                        variable=self.var_typo_enabled, command=self.update_settings)
        self.chk_typo.pack(anchor='w', pady=5, padx=10)
                        
        self.var_realtime_typo = tk.BooleanVar(value=app_state.get("realtime_typo_enabled", False))
        self.chk_realtime = ttk.Checkbutton(frame_typo, text="↳ 실시간 타이핑 검사 및 자동 변환 (실험적)",
                        variable=self.var_realtime_typo, command=self.update_settings)
        self.chk_realtime.pack(anchor='w', pady=(0,5), padx=25)

        ttk.Separator(frame_typo, orient='horizontal').pack(fill='x', padx=10, pady=5)
        ttk.Label(frame_typo, text="작동 방식 (아래 5가지 중 택 1):").pack(anchor='w', padx=15, pady=2)
        
        self.var_trigger_mode = tk.StringVar(value=app_state.get("trigger_mode", "hotkey"))
        
        # 1. 조합 단축키
        f_hk = ttk.Frame(frame_typo)
        f_hk.pack(fill='x', padx=15, pady=2)
        ttk.Radiobutton(f_hk, text="1. 조합 단축키 (비추천):", variable=self.var_trigger_mode, value="hotkey", command=self.update_settings).pack(side='left')
        self.lbl_hotkey = ttk.Label(f_hk, text=app_state.get("typo_hotkey", "ctrl+shift+space"), width=18, relief="sunken", anchor='center')
        self.lbl_hotkey.pack(side='left', padx=5)
        self.btn_record = ttk.Button(f_hk, text="\U0001f534 녹음", command=self.toggle_hotkey_record)
        self.btn_record.pack(side='left')
        
        # 2. 수식키 연타
        f_mod = ttk.Frame(frame_typo)
        f_mod.pack(fill='x', padx=15, pady=2)
        ttk.Radiobutton(f_mod, text="2. 수식키 연타:", variable=self.var_trigger_mode, value="modifier", command=self.update_settings).pack(side='left')
        self.var_mod_key = tk.StringVar(value=app_state.get("trigger_mod_key", "shift"))
        ttk.Combobox(
            f_mod, textvariable=self.var_mod_key,
            values=[
                "shift", "left shift", "right shift",
                "ctrl", "left ctrl", "right ctrl",
                "alt", "left alt", "right alt",
            ],
            width=12, state="readonly",
        ).pack(side='left', padx=2)
        ttk.Label(f_mod, text="키").pack(side='left')
        self.var_mod_count = tk.StringVar(value=str(app_state.get("trigger_mod_count", 2)))
        ttk.Combobox(f_mod, textvariable=self.var_mod_count, values=["2", "3", "4"], width=3, state="readonly").pack(side='left', padx=2)
        ttk.Label(f_mod, text="회 /").pack(side='left')
        self.var_mod_timeout = tk.StringVar(value=str(app_state.get("trigger_mod_timeout", 600)))
        ttk.Combobox(f_mod, textvariable=self.var_mod_timeout, values=["600", "900"], width=4, state="readonly").pack(side='left', padx=2)
        ttk.Label(f_mod, text="ms").pack(side='left')
        
        # 3. 기호 연타
        f_sym = ttk.Frame(frame_typo)
        f_sym.pack(fill='x', padx=15, pady=2)
        ttk.Radiobutton(f_sym, text="3. 기호 연속치기:", variable=self.var_trigger_mode, value="symbol", command=self.update_settings).pack(side='left')
        self.var_sym_char = tk.StringVar(value=app_state.get("trigger_symbol_char", ";"))
        self.ent_sym = ttk.Entry(f_sym, textvariable=self.var_sym_char, width=3)
        self.ent_sym.pack(side='left', padx=2)
        ttk.Label(f_sym, text="기호").pack(side='left')
        self.var_sym_count = tk.StringVar(value=str(app_state.get("trigger_symbol_count", 3)))
        ttk.Combobox(f_sym, textvariable=self.var_sym_count, values=["2", "3", "4", "5"], width=3, state="readonly").pack(side='left', padx=2)
        ttk.Label(f_sym, text="회 연속 치기").pack(side='left')
        
        # 4. 희귀키 연타
        f_rare = ttk.Frame(frame_typo)
        f_rare.pack(fill='x', padx=15, pady=2)
        ttk.Radiobutton(f_rare, text="4. 희귀키 연타:", variable=self.var_trigger_mode, value="rare", command=self.update_settings).pack(side='left')
        self.var_rare_key = tk.StringVar(value=app_state.get("trigger_rare_key", "scroll lock"))
        ttk.Combobox(f_rare, textvariable=self.var_rare_key, values=["scroll lock", "]", "`", "caps lock"], width=12, state="readonly").pack(side='left', padx=2)
        self.var_rare_count = tk.StringVar(value=str(app_state.get("trigger_rare_count", 2)))
        ttk.Combobox(f_rare, textvariable=self.var_rare_count, values=["2", "3"], width=3, state="readonly").pack(side='left', padx=2)
        ttk.Label(f_rare, text="회").pack(side='left')
        
        # 5. 가운데 클릭
        f_mid = ttk.Frame(frame_typo)
        f_mid.pack(fill='x', padx=15, pady=2)
        ttk.Radiobutton(f_mid, text="5. 마우스 가운데 클릭 (휠 누르기)", variable=self.var_trigger_mode, value="middle_click", command=self.update_settings).pack(side='left')
        
        self.var_mod_key.trace('w', lambda *_: self.update_settings_delayed())
        self.var_mod_count.trace('w', lambda *_: self.update_settings_delayed())
        self.var_mod_timeout.trace('w', lambda *_: self.update_settings_delayed())
        self.var_sym_char.trace('w', lambda *_: self.update_settings_delayed())
        self.var_sym_count.trace('w', lambda *_: self.update_settings_delayed())
        self.var_rare_key.trace('w', lambda *_: self.update_settings_delayed())
        self.var_rare_count.trace('w', lambda *_: self.update_settings_delayed())

        self.recording_hotkey = False
        self.recording_hook = None
        self.recorded_keys = set()
        ttk.Label(
            frame_typo,
            text="기호 연타: 드래그 선택 후에는\n제대로 작동하지 않을 수 있습니다.\n드래그 변환은 가운데 클릭을 권장합니다.",
        ).pack(anchor='w', padx=25, pady=(5, 0))
        ttk.Label(frame_typo, text="희귀키 연타: 키 입력이 화면에 남지 않습니다.",
                  foreground="gray").pack(anchor='w', padx=25, pady=(0, 0))
        ttk.Label(frame_typo, text="수식키: Windows 고정 키(설정>접근성>키보드)를 끄면 Shift 연타 팝업 방지.",
                  foreground="gray").pack(anchor='w', padx=25, pady=(0, 0))
        ttk.Label(frame_typo, text="가운데 클릭: 일부 터미널에서 붙여넣기로 동작할 수 있음.",
                  foreground="gray").pack(anchor='w', padx=25, pady=(0, 10))

        self.save_job = None
        self.update_lang_label()
        
        self.overlay_widget = OverlayWidget(self.root)
        
    def update_lang_label(self):
        if self.var_default_lang.get() == "hangul":
            self.var_double_lang.set("▶ 두 번 연속 누를 때 언어: 영문")
        else:
            self.var_double_lang.set("▶ 두 번 연속 누를 때 언어: 한글")
        self.update_settings()
        
    def add_kw(self):
        kw = self.entry_kw.get().strip()
        if kw and kw not in app_state["target_keywords"]:
            app_state["target_keywords"].append(kw)
            self.listbox_kw.insert(tk.END, kw)
            self.entry_kw.delete(0, tk.END)
            self.update_settings()
            
    def del_kw(self):
        sel = self.listbox_kw.curselection()
        if sel:
            idx = sel[0]
            kw = self.listbox_kw.get(idx)
            self.listbox_kw.delete(idx)
            app_state["target_keywords"].remove(kw)
            self.update_settings()
            
    def update_settings_delayed(self, event=None):
        if self.save_job:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(500, self.update_settings)

    def update_settings(self, event=None):
        app_state["enabled"] = self.var_enabled.get()
        app_state["enter_mode_enabled"] = self.var_enter_enabled.get()
        app_state["enter_mode_default"] = self.var_enter_default.get()
        app_state["timer_enabled"] = self.var_timer_enabled.get()
        try:
            val = int(self.entry_sec.get())
            if val > 0:
                app_state["timer_seconds"] = val
        except:
            pass
        app_state["smart_mode_enabled"] = self.var_smart_mode.get()
        app_state["smart_mode_default"] = self.var_default_lang.get()
        try:
            val = int(self.entry_timeout.get())
            if val > 0:
                app_state["smart_mode_timeout"] = val
        except:
            pass
        app_state["overlay_enabled"] = self.var_overlay_enabled.get()
        app_state["target_enabled"] = self.var_target_enabled.get()
        app_state["target_mode"] = self.var_target_mode.get()
        app_state["typo_enabled"] = self.var_typo_enabled.get()
        app_state["realtime_typo_enabled"] = self.var_realtime_typo.get()
        
        app_state["trigger_mode"] = self.var_trigger_mode.get()
        app_state["trigger_mod_key"] = self.var_mod_key.get()
        try:
            app_state["trigger_mod_count"] = int(self.var_mod_count.get())
        except:
            pass
        app_state["trigger_symbol_char"] = self.var_sym_char.get()
        try:
            app_state["trigger_symbol_count"] = int(self.var_sym_count.get())
        except:
            pass
        app_state["trigger_rare_key"] = self.var_rare_key.get()
        try:
            app_state["trigger_rare_count"] = int(self.var_rare_count.get())
        except:
            pass
        try:
            app_state["trigger_mod_timeout"] = int(self.var_mod_timeout.get())
        except:
            pass
        
        # UI 동기화
        if not app_state["typo_enabled"]:
            self.chk_realtime.state(['disabled'])
        else:
            self.chk_realtime.state(['!disabled'])
            
        apply_hotkeys()
        update_tray_icon()
        save_settings()

    def toggle_hotkey_record(self):
        if self.recording_hotkey:
            self.cancel_hotkey_record()
        else:
            self.start_hotkey_record()

    def start_hotkey_record(self):
        self.recording_hotkey = True
        self.recorded_keys = set()
        self.btn_record.config(text="\u23f9 중지")
        self.lbl_hotkey.config(text="키를 누르세요...")
        keyboard.unhook_all_hotkeys()
        self.recording_hook = keyboard.hook(self._on_record_key)

    def _on_record_key(self, event):
        if event.event_type == 'down':
            name = event.name.lower().replace('left ', '').replace('right ', '')
            if name == 'escape':
                self.root.after(0, self.cancel_hotkey_record)
                return
            self.recorded_keys.add(name)
            display = self._format_hotkey(self.recorded_keys)
            self.root.after(0, lambda d=display: self.lbl_hotkey.config(text=d))
        elif event.event_type == 'up':
            modifiers = {'ctrl', 'shift', 'alt'}
            non_mod = self.recorded_keys - modifiers
            if non_mod:
                self.root.after(0, self.finish_hotkey_record)

    def finish_hotkey_record(self):
        if not self.recording_hotkey:
            return
        hotkey = self._format_hotkey(self.recorded_keys)
        app_state["typo_hotkey"] = hotkey
        self.stop_hotkey_record()
        self.lbl_hotkey.config(text=hotkey)
        apply_hotkeys()
        save_settings()

    def cancel_hotkey_record(self):
        self.stop_hotkey_record()
        self.lbl_hotkey.config(text=app_state.get("typo_hotkey", "ctrl+shift+space"))

    def stop_hotkey_record(self):
        self.recording_hotkey = False
        self.btn_record.config(text="\U0001f534 녹음")
        if self.recording_hook:
            keyboard.unhook(self.recording_hook)
            self.recording_hook = None
        apply_hotkeys()

    @staticmethod
    def _format_hotkey(keys):
        modifier_order = {'ctrl': 0, 'shift': 1, 'alt': 2}
        mods = sorted([k for k in keys if k in modifier_order], key=lambda x: modifier_order[x])
        others = sorted([k for k in keys if k not in modifier_order])
        return '+'.join(mods + others)

def start_background():
    keyboard.hook(on_key_event)
    apply_hotkeys()
    t = threading.Thread(target=timer_thread, daemon=True)
    t.start()

def main():
    load_settings()
    start_background()
    root = tk.Tk()
    root.attributes("-alpha", 0.0)  # 시작 시 창 숨김
    app = AutoEngApp(root)
    
    def minimize_to_tray():
        save_settings()
        root.withdraw()
        
        global tray_icon
        if tray_icon is None or not getattr(tray_icon, '_running', False):
            setup_tray(root)
            threading.Thread(target=tray_icon.run, daemon=True).start()
        
    root.protocol("WM_DELETE_WINDOW", minimize_to_tray)
    minimize_to_tray()  # 즉시 트레이로
    root.mainloop()

if __name__ == '__main__':
    main()
