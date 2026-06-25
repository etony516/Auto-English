"""트리거 관련 단위 검증 (GUI/훅 없이 실행 가능)."""
import converter

RARE_KEY_VK = {
    'scroll lock': 0x91,
    ']': 0xDD,
    '`': 0xC0,
    'caps lock': 0x14,
}


def _normalize_mod_base(name):
    return name.lower().replace('left ', '').replace('right ', '')


def _mod_trigger_match_event(event_name, trigger_key):
    en = event_name.lower()
    tk = trigger_key.lower()
    if tk.startswith('left ') or tk.startswith('right '):
        return en == tk
    return _normalize_mod_base(en) == tk


def test_mod_trigger_match():
    assert _mod_trigger_match_event('left shift', 'shift')
    assert _mod_trigger_match_event('right shift', 'shift')
    assert _mod_trigger_match_event('shift', 'shift')
    assert _mod_trigger_match_event('left ctrl', 'ctrl')
    assert _mod_trigger_match_event('right ctrl', 'ctrl')
    assert not _mod_trigger_match_event('left shift', 'right shift')
    assert not _mod_trigger_match_event('right shift', 'left shift')
    assert _mod_trigger_match_event('right shift', 'right shift')
    assert not _mod_trigger_match_event('shift', 'right shift')
    assert not _mod_trigger_match_event('left ctrl', 'right ctrl')


def test_converter_roundtrip():
    eng, _ = converter.auto_convert('xptmxm')
    assert eng == '테스트'
    kor, _ = converter.auto_convert('테스트')
    assert kor == 'xptmxm'


def test_rare_key_map():
    assert len(RARE_KEY_VK) == 4
    assert RARE_KEY_VK['scroll lock'] == 0x91


def _smooth_ime_for_display(samples):
    """테스트용 — 최근 샘플 다수결 (간소화)."""
    n = len(samples)
    hangul_votes = sum(samples)
    if hangul_votes >= n * 0.7:
        return True
    if hangul_votes <= n * 0.3:
        return False
    return samples[-1]


def test_ime_smooth():
    assert _smooth_ime_for_display([True] * 7 + [False] * 3) is True
    assert _smooth_ime_for_display([False] * 8 + [True] * 2) is False
    assert _smooth_ime_for_display([True, False]) is False


if __name__ == '__main__':
    test_mod_trigger_match()
    test_converter_roundtrip()
    test_rare_key_map()
    test_ime_smooth()
    print('All trigger unit tests passed.')
