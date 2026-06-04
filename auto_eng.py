import ctypes
import keyboard

# 윈도우 API DLL 로드
user32 = ctypes.WinDLL('user32', use_last_error=True)
imm32 = ctypes.WinDLL('imm32', use_last_error=True)

# IME 제어를 위한 상수
WM_IME_CONTROL = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
IMC_SETCONVERSIONMODE = 0x0002

IME_CMODE_HANGUL = 0x0001

def set_ime_to_english():
    try:
        # 현재 활성화된 창의 핸들을 가져옵니다.
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return

        # 해당 창의 기본 IME 윈도우 핸들을 가져옵니다.
        hime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
        if not hime_wnd:
            return

        # 현재 IME 상태(변환 모드)를 가져옵니다.
        current_mode = user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        
        # 만약 현재 모드가 한글(IME_CMODE_HANGUL)이라면
        if current_mode & IME_CMODE_HANGUL:
            # 한글 모드 비트를 0으로 만들어 영문으로 전환합니다.
            new_mode = current_mode & ~IME_CMODE_HANGUL
            user32.SendMessageW(hime_wnd, WM_IME_CONTROL, IMC_SETCONVERSIONMODE, new_mode)
    except Exception as e:
        print(f"상태 변경 중 오류 발생: {e}")

def on_key_event(e):
    # 엔터(Enter) 키가 눌릴 때(down) 실행
    if e.name == 'enter' and e.event_type == 'down':
        set_ime_to_english()

def main():
    print("==================================================")
    print("자동 영타 전환 프로그램이 시작되었습니다.")
    print("이제 '엔터(Enter)' 키를 누르면 자동으로 영문 모드로 전환됩니다.")
    print("종료하려면 이 창에서 Ctrl+C를 누르세요.")
    print("==================================================")
    
    # 키보드 이벤트 후킹 (백그라운드에서 키 입력 감지)
    keyboard.hook(on_key_event)

    # 프로그램이 종료되지 않고 계속 실행되도록 무한 대기
    keyboard.wait()

if __name__ == '__main__':
    main()
