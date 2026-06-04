import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
import keyboard
import threading
import time
import json
import os
import pystray
from PIL import Image, ImageDraw

# --- Win32 API ---
user32 = ctypes.WinDLL('user32', use_last_error=True)
imm32 = ctypes.WinDLL('imm32', use_last_error=True)

WM_IME_CONTROL = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
IMC_SETCONVERSIONMODE = 0x0002
IME_CMODE_HANGUL = 0x0001

def get_active_window_title():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value

def set_ime_to_english():
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd: return
        hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime_wnd: return
        current_mode = user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        if current_mode & IME_CMODE_HANGUL:
            new_mode = current_mode & ~IME_CMODE_HANGUL
            user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_SETCONVERSIONMODE, new_mode)
    except Exception as e:
        pass

def set_ime_to_hangul():
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd: return
        hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime_wnd: return
        current_mode = user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        if not (current_mode & IME_CMODE_HANGUL):
            new_mode = current_mode | IME_CMODE_HANGUL
            user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_SETCONVERSIONMODE, new_mode)
    except Exception as e:
        pass

# --- Core App State ---
SETTINGS_FILE = "settings.json"
app_state = {
    "enabled": True,
    "enter_mode_enabled": True,
    "enter_mode_default": "english",
    "timer_enabled": False,
    "timer_seconds": 3,
    "target_enabled": False,
    "target_keywords": [],
    "smart_mode_enabled": False,
    "smart_mode_default": "hangul",
    "smart_mode_timeout": 300
}

last_key_time = time.time()
timer_triggered = False

last_haneng_down_time = 0
is_double_click = False

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
        return False
    title = get_active_window_title().lower()
    for kw in app_state["target_keywords"]:
        if kw.lower() in title:
            return True
    return False

def on_key_event(e):
    global last_key_time, timer_triggered, last_haneng_down_time, is_double_click
    
    if e.event_type == 'down':
        last_key_time = time.time()
        timer_triggered = False
        
    if not app_state["enabled"]:
        return
        
    is_haneng_key = e.name in ['한/영', 'hangul', 'right alt', 'alt gr']
    
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
                
            elif e.event_type == 'up':
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
                return 
            
    if e.name == 'enter' and e.event_type == 'down':
        if app_state.get("enter_mode_enabled", True) and check_target_window():
            if app_state.get("enter_mode_default", "english") == "english":
                set_ime_to_english()
            else:
                set_ime_to_hangul()

# --- Tray Icon ---
def create_image(color):
    image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=color, outline="white")
    return image

ICON_ACTIVE = create_image("#2196F3") # Active (Blue)
ICON_INACTIVE = create_image("#9E9E9E")  # Inactive (Gray)

def setup_tray(root):
    global tray_icon
    def on_show(icon, item):
        icon.stop()
        root.after(0, root.deiconify)
        
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
    
    tray_icon = pystray.Icon("AutoEng", ICON_INACTIVE, "자동 영타 전환기", menu)

def timer_thread():
    global timer_triggered, tray_icon
    while running:
        time.sleep(0.5)
        
        # Update Tray Icon dynamically
        if tray_icon and getattr(tray_icon, '_running', False):
            if app_state["enabled"] and check_target_window():
                tray_icon.icon = ICON_ACTIVE
            else:
                tray_icon.icon = ICON_INACTIVE
                
        # Handle timer functionality
        if app_state["enabled"] and app_state["timer_enabled"] and not timer_triggered:
            if time.time() - last_key_time >= app_state["timer_seconds"]:
                if check_target_window():
                    set_ime_to_english()
                timer_triggered = True

# --- GUI ---
class AutoEngApp:
    def __init__(self, root):
        self.root = root
        self.root.title("자동 영타 전환기 (Auto English)")
        self.root.geometry("450x800")
        self.root.resizable(False, False)
        
        load_settings()
        
        # 1. Main Toggle
        self.var_enabled = tk.BooleanVar(value=app_state["enabled"])
        chk_main = ttk.Checkbutton(root, text="기능 켜기 (전체 활성화)", variable=self.var_enabled, command=self.update_settings)
        chk_main.pack(pady=10, padx=15, anchor='w')
        
        # 2. Enter Key Settings
        frame_enter = ttk.LabelFrame(root, text="엔터(Enter) 키 동작 설정")
        frame_enter.pack(fill='x', pady=5, padx=15)
        
        self.var_enter_enabled = tk.BooleanVar(value=app_state.get("enter_mode_enabled", True))
        ttk.Checkbutton(frame_enter, text="엔터 키 입력 후 자동으로 언어 변경하기", variable=self.var_enter_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        
        f_en_opts = ttk.Frame(frame_enter)
        f_en_opts.pack(anchor='w', fill='x', padx=25, pady=(0, 10))
        ttk.Label(f_en_opts, text="엔터 후 언어:").pack(side='left')
        self.var_enter_default = tk.StringVar(value=app_state.get("enter_mode_default", "english"))
        ttk.Radiobutton(f_en_opts, text="한글", variable=self.var_enter_default, value="hangul", command=self.update_settings).pack(side='left', padx=(5, 0))
        ttk.Radiobutton(f_en_opts, text="영문", variable=self.var_enter_default, value="english", command=self.update_settings).pack(side='left', padx=5)
        
        # 3. Timer Settings
        frame_timer = ttk.LabelFrame(root, text="타이머 설정")
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
        
        # 4. Han/Eng Smart Mode
        frame_haneng = ttk.LabelFrame(root, text="한/영 키 커스텀 더블클릭 설정")
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
        ttk.Label(f_he_double, textvariable=self.var_double_lang, foreground="blue").pack(side='left')
        
        f_he_time = ttk.Frame(frame_haneng)
        f_he_time.pack(anchor='w', fill='x', padx=25, pady=(0, 10))
        ttk.Label(f_he_time, text="더블클릭 인식 제한 시간(ms):").pack(side='left')
        self.entry_timeout = ttk.Entry(f_he_time, width=6)
        self.entry_timeout.insert(0, str(app_state.get("smart_mode_timeout", 300)))
        self.entry_timeout.pack(side='left', padx=5)
        self.entry_timeout.bind("<KeyRelease>", self.update_settings_delayed)
        
        help_text2 = "제한 시간 안에 한/영 키를 연속으로 두 번 누르면\n파란색 글씨에 표시된 언어로 바뀝니다."
        ttk.Label(frame_haneng, text=help_text2, foreground="gray").pack(anchor='w', padx=25, pady=(0, 10))

        # 5. Target Apps
        frame_target = ttk.LabelFrame(root, text="대상 프로그램 설정 (창 제목 기준)")
        frame_target.pack(fill='both', expand=True, pady=5, padx=15)
        
        self.var_target_enabled = tk.BooleanVar(value=app_state["target_enabled"])
        ttk.Checkbutton(frame_target, text="특정 창(프로그램)에서만 작동하기", variable=self.var_target_enabled, command=self.update_settings).pack(anchor='w', pady=5, padx=10)
        
        help_text = "작업 표시줄 프로그램 아이콘에 마우스를 올렸을 때\n표시되는 이름의 '일부'를 추가해 주세요. (예: Visual Studio Code)"
        ttk.Label(frame_target, text=help_text, foreground="gray").pack(anchor='w', padx=25)
        
        f_kw = ttk.Frame(frame_target)
        f_kw.pack(fill='x', padx=25, pady=5)
        self.entry_kw = ttk.Entry(f_kw)
        self.entry_kw.pack(side='left', fill='x', expand=True)
        self.entry_kw.bind("<Return>", lambda e: self.add_kw())
        ttk.Button(f_kw, text="추가", command=self.add_kw, width=6).pack(side='left', padx=5)
        
        self.listbox_kw = tk.Listbox(frame_target, height=5)
        self.listbox_kw.pack(fill='both', expand=True, padx=25, pady=(0, 5))
        for kw in app_state["target_keywords"]:
            self.listbox_kw.insert(tk.END, kw)
            
        ttk.Button(frame_target, text="선택 삭제", command=self.del_kw).pack(anchor='e', padx=25, pady=(0, 10))
        
        self.save_job = None
        self.update_lang_label()
        
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
            
        app_state["target_enabled"] = self.var_target_enabled.get()
        save_settings()

def start_background():
    keyboard.hook(on_key_event)
    t = threading.Thread(target=timer_thread, daemon=True)
    t.start()

def main():
    start_background()
    root = tk.Tk()
    app = AutoEngApp(root)
    
    def on_closing():
        save_settings()
        root.withdraw() # 창 숨기기
        global tray_icon
        setup_tray(root)
        # 트레이 아이콘을 별도 스레드에서 실행 (tkinter 루프 유지)
        threading.Thread(target=tray_icon.run, daemon=True).start()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == '__main__':
    main()
