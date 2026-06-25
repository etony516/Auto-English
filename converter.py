# converter.py - 한/영 오타 변환 모듈

# ===== 한글 유니코드 상수 =====
HANGUL_BASE = 0xAC00  # '가'
HANGUL_END = 0xD7A3    # '힣'

CHOSUNG_LIST = [
    'ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ',
    'ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'
]

JUNGSUNG_LIST = [
    'ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ',
    'ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ'
]

JONGSUNG_LIST = [
    '','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ',
    'ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ',
    'ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'
]

# ===== 영문 키 → 자모 매핑 =====
EN_TO_JAMO = {
    'q': 'ㅂ', 'w': 'ㅈ', 'e': 'ㄷ', 'r': 'ㄱ', 't': 'ㅅ',
    'y': 'ㅛ', 'u': 'ㅕ', 'i': 'ㅑ', 'o': 'ㅐ', 'p': 'ㅔ',
    'a': 'ㅁ', 's': 'ㄴ', 'd': 'ㅇ', 'f': 'ㄹ', 'g': 'ㅎ',
    'h': 'ㅗ', 'j': 'ㅓ', 'k': 'ㅏ', 'l': 'ㅣ',
    'z': 'ㅋ', 'x': 'ㅌ', 'c': 'ㅊ', 'v': 'ㅍ',
    'b': 'ㅠ', 'n': 'ㅜ', 'm': 'ㅡ',
    # 쌍자음 / 특수모음 (Shift 조합)
    'Q': 'ㅃ', 'W': 'ㅉ', 'E': 'ㄸ', 'R': 'ㄲ', 'T': 'ㅆ',
    'O': 'ㅒ', 'P': 'ㅖ',
    # 나머지 대문자 (소문자와 동일한 자모)
    'A': 'ㅁ', 'S': 'ㄴ', 'D': 'ㅇ', 'F': 'ㄹ', 'G': 'ㅎ',
    'H': 'ㅗ', 'J': 'ㅓ', 'K': 'ㅏ', 'L': 'ㅣ',
    'Z': 'ㅋ', 'X': 'ㅌ', 'C': 'ㅊ', 'V': 'ㅍ',
    'B': 'ㅠ', 'N': 'ㅜ', 'M': 'ㅡ',
    'Y': 'ㅛ', 'U': 'ㅕ', 'I': 'ㅑ',
}

# ===== 자모 → 영문 키 매핑 =====
JAMO_TO_EN = {
    'ㄱ': 'r', 'ㄲ': 'R', 'ㄴ': 's', 'ㄷ': 'e', 'ㄸ': 'E',
    'ㄹ': 'f', 'ㅁ': 'a', 'ㅂ': 'q', 'ㅃ': 'Q', 'ㅅ': 't',
    'ㅆ': 'T', 'ㅇ': 'd', 'ㅈ': 'w', 'ㅉ': 'W', 'ㅊ': 'c',
    'ㅋ': 'z', 'ㅌ': 'x', 'ㅍ': 'v', 'ㅎ': 'g',
    'ㅏ': 'k', 'ㅐ': 'o', 'ㅑ': 'i', 'ㅒ': 'O', 'ㅓ': 'j',
    'ㅔ': 'p', 'ㅕ': 'u', 'ㅖ': 'P', 'ㅗ': 'h', 'ㅛ': 'y',
    'ㅜ': 'n', 'ㅠ': 'b', 'ㅡ': 'm', 'ㅣ': 'l',
}

# 복합 모음 → 영문 키 시퀀스
COMPOUND_VOWEL_TO_EN = {
    'ㅘ': 'hk', 'ㅙ': 'ho', 'ㅚ': 'hl',
    'ㅝ': 'nj', 'ㅞ': 'np', 'ㅟ': 'nl', 'ㅢ': 'ml',
}

# 복합 종성 → 영문 키 시퀀스
COMPOUND_JONG_TO_EN = {
    'ㄳ': 'rt', 'ㄵ': 'sw', 'ㄶ': 'sg',
    'ㄺ': 'fr', 'ㄻ': 'fa', 'ㄼ': 'fq',
    'ㄽ': 'ft', 'ㄾ': 'fx', 'ㄿ': 'fv', 'ㅀ': 'fg',
    'ㅄ': 'qt',
}

# ===== 복합 조합 테이블 =====
COMPOUND_VOWEL = {
    ('ㅗ','ㅏ'): 'ㅘ', ('ㅗ','ㅐ'): 'ㅙ', ('ㅗ','ㅣ'): 'ㅚ',
    ('ㅜ','ㅓ'): 'ㅝ', ('ㅜ','ㅔ'): 'ㅞ', ('ㅜ','ㅣ'): 'ㅟ',
    ('ㅡ','ㅣ'): 'ㅢ',
}

COMPOUND_JONG = {
    ('ㄱ','ㅅ'): 'ㄳ', ('ㄴ','ㅈ'): 'ㄵ', ('ㄴ','ㅎ'): 'ㄶ',
    ('ㄹ','ㄱ'): 'ㄺ', ('ㄹ','ㅁ'): 'ㄻ', ('ㄹ','ㅂ'): 'ㄼ',
    ('ㄹ','ㅅ'): 'ㄽ', ('ㄹ','ㅌ'): 'ㄾ', ('ㄹ','ㅍ'): 'ㄿ', ('ㄹ','ㅎ'): 'ㅀ',
    ('ㅂ','ㅅ'): 'ㅄ',
}

COMPOUND_JONG_SPLIT = {v: k for k, v in COMPOUND_JONG.items()}

# ===== 자모 분류 =====
CONSONANTS = set(CHOSUNG_LIST)
VOWELS = set(JUNGSUNG_LIST)
SINGLE_JONGSUNG = {'ㄱ','ㄲ','ㄴ','ㄷ','ㄹ','ㅁ','ㅂ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'}


def is_consonant(ch):
    return ch in CONSONANTS

def is_vowel(ch):
    return ch in VOWELS

def compose_syllable(cho, jung, jong=''):
    cho_idx = CHOSUNG_LIST.index(cho)
    jung_idx = JUNGSUNG_LIST.index(jung)
    jong_idx = JONGSUNG_LIST.index(jong) if jong in JONGSUNG_LIST else 0
    return chr(HANGUL_BASE + (cho_idx * 21 + jung_idx) * 28 + jong_idx)

def decompose_syllable(ch):
    code = ord(ch) - HANGUL_BASE
    jong_idx = code % 28
    code = code // 28
    jung_idx = code % 21
    cho_idx = code // 21
    return CHOSUNG_LIST[cho_idx], JUNGSUNG_LIST[jung_idx], JONGSUNG_LIST[jong_idx]

def is_hangul_syllable(ch):
    return HANGUL_BASE <= ord(ch) <= HANGUL_END

def is_hangul_jamo(ch):
    return 0x3131 <= ord(ch) <= 0x3163


def english_to_korean(text):
    """영문 키 시퀀스 → 한글 조합"""
    jamo_list = []
    for ch in text:
        jamo_list.append(EN_TO_JAMO.get(ch, ch))

    result = []
    cho = None
    jung = None
    jong = None

    def emit():
        nonlocal cho, jung, jong
        if cho is not None and jung is not None:
            result.append(compose_syllable(cho, jung, jong or ''))
        elif cho is not None:
            result.append(cho)
        elif jung is not None:
            result.append(jung)
        cho = jung = jong = None

    for jamo in jamo_list:
        if not (is_consonant(jamo) or is_vowel(jamo)):
            emit()
            result.append(jamo)
            continue

        if is_consonant(jamo):
            if cho is None:
                if jung is not None:
                    emit()
                cho = jamo
            elif jung is None:
                emit()
                cho = jamo
            elif jong is None:
                if jamo in SINGLE_JONGSUNG:
                    jong = jamo
                else:
                    emit()
                    cho = jamo
            else:
                compound = COMPOUND_JONG.get((jong, jamo))
                if compound:
                    jong = compound
                else:
                    emit()
                    cho = jamo

        elif is_vowel(jamo):
            if cho is None:
                if jung is None:
                    jung = jamo
                else:
                    compound = COMPOUND_VOWEL.get((jung, jamo))
                    if compound:
                        jung = compound
                    else:
                        emit()
                        jung = jamo
            elif jung is None:
                jung = jamo
            elif jong is None:
                compound = COMPOUND_VOWEL.get((jung, jamo))
                if compound:
                    jung = compound
                else:
                    emit()
                    cho = None
                    jung = jamo
            else:
                if jong in COMPOUND_JONG_SPLIT:
                    first, second = COMPOUND_JONG_SPLIT[jong]
                    jong = first
                    emit()
                    cho = second
                    jung = jamo
                else:
                    last_jong = jong
                    jong = None
                    emit()
                    cho = last_jong
                    jung = jamo

    emit()
    return ''.join(result)


def korean_to_english(text):
    """한글 → 영문 키 시퀀스"""
    result = []
    for ch in text:
        if is_hangul_syllable(ch):
            cho, jung, jong = decompose_syllable(ch)
            result.append(JAMO_TO_EN.get(cho, cho))
            if jung in COMPOUND_VOWEL_TO_EN:
                result.append(COMPOUND_VOWEL_TO_EN[jung])
            else:
                result.append(JAMO_TO_EN.get(jung, jung))
            if jong:
                if jong in COMPOUND_JONG_TO_EN:
                    result.append(COMPOUND_JONG_TO_EN[jong])
                else:
                    result.append(JAMO_TO_EN.get(jong, jong))
        elif is_hangul_jamo(ch):
            if ch in COMPOUND_VOWEL_TO_EN:
                result.append(COMPOUND_VOWEL_TO_EN[ch])
            elif ch in COMPOUND_JONG_TO_EN:
                result.append(COMPOUND_JONG_TO_EN[ch])
            else:
                result.append(JAMO_TO_EN.get(ch, ch))
        else:
            result.append(ch)
    return ''.join(result)


def detect_language(text):
    """텍스트의 주 언어 감지"""
    korean_count = 0
    english_count = 0
    for ch in text:
        if is_hangul_syllable(ch) or is_hangul_jamo(ch):
            korean_count += 1
        elif ch.isascii() and ch.isalpha():
            english_count += 1
    return "korean" if korean_count > english_count else "english"


def auto_convert(text):
    """자동 감지 후 변환. (변환된_텍스트, 대상_언어) 반환"""
    lang = detect_language(text)
    if lang == "english":
        return english_to_korean(text), "hangul"
    else:
        return korean_to_english(text), "english"

def check_realtime_typo(buffer_text, is_hangul_mode):
    """
    실시간 타자 버퍼(영어 키스트로크)와 현재 IME 상태를 기반으로 오타 여부를 판별합니다.
    반환값: (is_typo, target_lang, chars_to_delete)
    """
    if len(buffer_text) < 2:
        return False, None, 0
        
    converted_kor = english_to_korean(buffer_text)
    syllables = sum(1 for c in converted_kor if is_hangul_syllable(c))
    jamos = sum(1 for c in converted_kor if is_hangul_jamo(c))
    
    # 한국어 형태인지 확인 (조합된 음절이 있고 잉여 자음/모음이 거의 없는 경우)
    is_perfect_korean = False
    if syllables > 0 and jamos == 0:
        is_perfect_korean = True
    elif syllables > 1 and jamos <= 1:
        is_perfect_korean = True
        
    # 고의적인 한국어 슬랭 (ㅋㅋ, ㅎㅎ, ㅠㅠ 등) 확인
    unique_chars = set(converted_kor)
    is_korean_slang = False
    if all(is_hangul_jamo(c) for c in unique_chars) and len(unique_chars) <= 2:
        is_korean_slang = True
        
    looks_like_korean = is_perfect_korean or is_korean_slang
    
    if is_hangul_mode:
        # 현재 한글 모드
        if looks_like_korean:
            # 한글 모드에서 한국어를 성공적으로 쳤음 -> 정상
            return False, None, 0
        else:
            # 한글 모드인데 엉망진창인 한글이 나옴 (예: ㅁㅔㅔㅣㄷ)
            # 즉, 영어를 치려다 실수한 것! -> 영어로 변환
            # 화면에는 converted_kor 길이만큼 한글이 조합되어 있음
            return True, "english", len(converted_kor)
    else:
        # 현재 영문 모드
        if looks_like_korean:
            # 영문 모드인데 완벽한 한국어 패턴이 나옴 (예: dkssud) -> 한글로 변환
            # 화면에는 영문자 그대로 출력되어 있음
            return True, "hangul", len(buffer_text)
        else:
            # 영문 모드에서 영어를 성공적으로 쳤음 -> 정상
            return False, None, 0
