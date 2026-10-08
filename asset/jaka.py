# -*- coding: utf-8 -*-
"""
日本語（漢字・ひらがな・カタカナ）をMayaノード名として安全なローマ字・英数字に変換するモジュール。
外部ライブラリ（pykakasi, jaconvなど）に依存せず、Python標準ライブラリのみで動作します。
"""

import re
import unicodedata

# 漢数字の読み対応テーブル
KANJI_NUM_MAP = {
    '〇': 'rei', '一': 'ichi', '二': 'ni', '三': 'san', '四': 'yon',
    '五': 'go', '六': 'roku', '七': 'nana', '八': 'hachi', '九': 'kyuu',
    '十': 'juu', '百': 'hyaku', '千': 'sen', '万': 'man'
}

# 先頭が数字の場合の読みフォールバックテーブル
DIGIT_START_MAP = {
    '0': 'zero', '1': 'ichi', '2': 'ni', '3': 'san', '4': 'yon',
    '5': 'go', '6': 'roku', '7': 'nana', '8': 'hachi', '9': 'kyuu'
}

# MMDボーン・モーフ・材質・人体部位などの頻出単語・漢字辞書
MMD_KANJI_DICT = {
    # 主要階層・特殊ボーン
    '全ての親': 'subetenoya',
    'すべての親': 'subetenoya',
    '操作中心': 'sousachuushin',
    'センター': 'center',
    'グルーブ': 'groove',
    '腰': 'koshi',
    '上半身': 'jouhanshin',
    '下半身': 'kahanshin',
    '首': 'kubi',
    '頭': 'atama',
    'あたま': 'atama',
    '顔': 'kao',

    # 左右・方向・位置
    '右': 'migi',
    '左': 'hidari',
    '前': 'mae',
    '後': 'ushiro',
    '上': 'ue',
    '下': 'shita',
    '中': 'naka',
    '内': 'uchi',
    '外': 'soto',
    '横': 'yoko',
    '裏': 'ura',
    '表': 'omote',
    '親': 'oya',
    '子': 'ko',
    '先': 'saki',
    '根': 'moto',
    '元': 'moto',
    '端': 'hashi',
    '頂点': 'chouten',

    # 腕・手
    '肩': 'kata',
    '腕': 'ude',
    'ひじ': 'hiji',
    '肘': 'hiji',
    '手首': 'tekubi',
    '手': 'te',
    '指': 'yubi',
    '親指': 'oyayubi',
    '人差指': 'hitosashiyubi',
    '人指': 'hitosashi',
    '中指': 'nakayubi',
    '薬指': 'kusuriyubi',
    '小指': 'koyubi',
    '爪': 'tsume',
    '掌': 'tenohira',
    '手のひら': 'tenohira',
    '捩': 'nejiri',
    '捩り': 'nejiri',

    # 足・脚
    '足': 'ashi',
    '脚': 'ashi',
    'ひざ': 'hiza',
    '膝': 'hiza',
    '足首': 'ashikubi',
    '足首Ｄ': 'ashikubid',
    '足先': 'ashisaki',
    'つま先': 'tsumasaki',
    '爪先': 'tsumasaki',
    '踵': 'kakato',
    'かかと': 'kakato',
    '太もも': 'futomomo',
    '腿': 'futomomo',
    '脛': 'sune',
    'すね': 'sune',

    # 顔・表情・モーフ
    '目': 'me',
    '瞳': 'hitomi',
    '両目': 'ryoume',
    '眉': 'mayu',
    '口': 'kuchi',
    '歯': 'ha',
    '舌': 'shita',
    '鼻': 'hana',
    '耳': 'mimi',
    '頬': 'hoho',
    '涙': 'namida',
    '汗': 'ase',
    '怒': 'ikari',
    '笑': 'warai',
    '照': 'terere',
    '困': 'komari',
    '驚': 'odoroki',
    '真面目': 'majime',
    'まばたき': 'mabataki',
    'ウィンク': 'wink',
    'ウインク': 'wink',
    'なごみ': 'nagomi',
    'じと目': 'jitome',
    '瞳小': 'hitomishou',
    '光': 'hikari',
    'ハイライト': 'highlight',

    # 髪・装飾・衣装
    '髪': 'kami',
    '前髪': 'maegami',
    '後髪': 'ushirogami',
    '後ろ髪': 'ushirogami',
    '横髪': 'yokogami',
    'サイド': 'side',
    'ツインテ': 'twinte',
    'ポニー': 'pony',
    'アホ毛': 'ahoge',
    '毛': 'ke',
    '服': 'fuku',
    '衣装': 'ishou',
    'スカート': 'skirt',
    'リボン': 'ribbon',
    'ネクタイ': 'necktie',
    'ベルト': 'belt',
    '靴': 'kutsu',
    '帽子': 'boushi',
    'メガネ': 'megane',
    '眼鏡': 'megane',
    '袖': 'sode',
    '裾': 'suso',
    '胸': 'mune',
    '背中': 'senaka',
    '腹': 'hara',
    '尻': 'shiri',
    '肌': 'hada',
    '素肌': 'suhada',
    '体': 'karada',
    '身体': 'shintai',

    # 機構・IK・補助
    'ＩＫ': 'ik',
    'IK': 'ik',
    '補助': 'hojo',
    '連動': 'rendou',
    '追従': 'tsuijuu',
    '回転': 'kaiten',
    '移動': 'idou',
    '制限': 'seigen',
    'ダミー': 'dummy',
    'ボーン': 'bone',
    '剛体': 'goutai',
    'ジョイント': 'joint',
    'マテリアル': 'material',
    '材質': 'mat',
    'テクスチャ': 'tex',
    '影': 'kage',
    '輪郭': 'rinkaku',
    'スフィア': 'sphere',
    '加算': 'kasan',
    '乗算': 'jousan',

    # よくある単語・形容詞
    '大': 'dai',
    '小': 'shou',
    '太': 'futo',
    '細': 'hoso',
    '長': 'naga',
    '短': 'miji',
    '新': 'shin',
    '旧': 'kyuu',
    '本': 'hon',
    '線': 'sen',
    '丸': 'maru',
    '角': 'kaku',
    '赤': 'aka',
    '青': 'ao',
    '白': 'shiro',
    '黒': 'kuro',
    '緑': 'midori',
    '黄': 'kiiro',
    '金': 'kin',
    '銀': 'gin',
    '色': 'iro'
}

# 拗音・促音等を含む2文字のかなマッピング（ヘボン式）
KANA_COMBO_MAP = {
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo',
    'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho',
    'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo',
    'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo',
    'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': 'ja',  'じゅ': 'ju',  'じょ': 'jo',
    'ぢゃ': 'ja',  'ぢゅ': 'ju',  'ぢょ': 'jo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo',
    'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'ふぁ': 'fa',  'ふぃ': 'fi',  'ふぇ': 'fe',  'ふぉ': 'fo',
    'ゔぁ': 'va',  'ゔぃ': 'vi',  'ゔ': 'vu',   'ゔぇ': 've',  'ゔぉ': 'vo',
    'てぃ': 'ti',  'でぃ': 'di',  'とぅ': 'tu',  'どぅ': 'du',
    'しぇ': 'she', 'じぇ': 'je',  'ちぇ': 'che',
    'うぃ': 'wi',  'うぇ': 'we',  'うぉ': 'wo'
}

# 1文字のかなマッピング（五十音・濁音・半濁音）
KANA_SINGLE_MAP = {
    'あ': 'a',   'い': 'i',   'う': 'u',   'え': 'e',   'お': 'o',
    'か': 'ka',  'き': 'ki',  'く': 'ku',  'け': 'ke',  'こ': 'ko',
    'さ': 'sa',  'し': 'shi', 'す': 'su',  'せ': 'se',  'そ': 'so',
    'た': 'ta',  'ち': 'chi', 'つ': 'tsu', 'て': 'te',  'と': 'to',
    'な': 'na',  'に': 'ni',  'ぬ': 'nu',  'ね': 'ne',  'の': 'no',
    'は': 'ha',  'ひ': 'hi',  'ふ': 'fu',  'へ': 'he',  'ほ': 'ho',
    'ま': 'ma',  'み': 'mi',  'む': 'mu',  'め': 'me',  'も': 'mo',
    'や': 'ya',               'ゆ': 'yu',               'よ': 'yo',
    'ら': 'ra',  'り': 'ri',  'る': 'ru',  'れ': 're',  'ろ': 'ro',
    'わ': 'wa',  'ゐ': 'wi',               'ゑ': 'we',  'を': 'wo',
    'ん': 'n',

    'が': 'ga',  'ぎ': 'gi',  'ぐ': 'gu',  'げ': 'ge',  'ご': 'go',
    'ざ': 'za',  'じ': 'ji',  'ず': 'zu',  'ぜ': 'ze',  'ぞ': 'zo',
    'だ': 'da',  'ぢ': 'ji',  'づ': 'zu',  'で': 'de',  'ど': 'do',
    'ば': 'ba',  'び': 'bi',  'ぶ': 'bu',  'べ': 'be',  'ぼ': 'bo',
    'ぱ': 'pa',  'ぴ': 'pi',  'ぷ': 'pu',  'ぺ': 'pe',  'ぽ': 'po',

    # 小文字単体フォールバック
    'ぁ': 'a',   'ぃ': 'i',   'ぅ': 'u',   'ぇ': 'e',   'ぉ': 'o',
    'ゃ': 'ya',  'ゅ': 'yu',  'ょ': 'yo',  'ゎ': 'wa'
}

def _katakana_to_hiragana(text):
    """カタカナをひらがなに変換します。"""
    res = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:  # ァ 〜 ヶ
            res.append(chr(code - 0x60))
        elif ch == 'ヴ':
            res.append('ゔ')
        else:
            res.append(ch)
    return ''.join(res)

def _kana_to_romaji(text):
    """
    ひらがな文字列をローマ字に変換します。
    促音（っ）や長音（ー）も処理します。
    """
    res = []
    i = 0
    length = len(text)

    while i < length:
        # 促音「っ」の処理（次の子音を重ねる）
        if text[i] == 'っ':
            if i + 1 < length:
                next_part = text[i + 1:i + 3]
                next_romaji = KANA_COMBO_MAP.get(next_part)
                if not next_romaji and i + 1 < length:
                    next_romaji = KANA_SINGLE_MAP.get(text[i + 1], '')
                
                if next_romaji:
                    # 子音を取得（chの場合はtchにするヘボン式慣例、またはcc）
                    consonant = next_romaji[0]
                    if next_romaji.startswith('ch'):
                        res.append('t')
                    else:
                        res.append(consonant)
                else:
                    res.append('')
            i += 1
            continue

        # 長音記号「ー」の処理（直前の母音を重ねる）
        if text[i] == 'ー':
            if res and res[-1]:
                last_char = res[-1][-1]
                if last_char in 'aiueo':
                    res.append(last_char)
            i += 1
            continue

        # 2文字の拗音チェック
        if i + 1 < length:
            two_chars = text[i:i + 2]
            if two_chars in KANA_COMBO_MAP:
                res.append(KANA_COMBO_MAP[two_chars])
                i += 2
                continue

        # 1文字のかなチェック
        one_char = text[i]
        if one_char in KANA_SINGLE_MAP:
            res.append(KANA_SINGLE_MAP[one_char])
            i += 1
            continue

        # かな以外の文字はそのまま保持
        res.append(one_char)
        i += 1

    return ''.join(res)

def romaji(x):
    """
    任意の文字列（日本語、記号混じり）を、Mayaノード名として安全なローマ字・英数字文字列に変換します。
    外部ライブラリ（pykakasi, jaconv）を使用しません。

    引数:
        x (str): 変換対象の文字列（モデル名、ボーン名、マテリアル名等）

    戻り値:
        str: Mayaノード名として有効な英数字・アンダースコア文字列
    """
    if x is None:
        return 'node'
    x = str(x).strip()
    if not x:
        return 'node'

    # Unicode正規化 (NFKC: 全角英数→半角、半角カナ→全角カナ等)
    x = unicodedata.normalize('NFKC', x)

    # 頻出MMD用語・漢字の置換（長い語句から順にマッチさせて置換）
    # ソートして長い語句優先にする
    sorted_kanji_keys = sorted(MMD_KANJI_DICT.keys(), key=len, reverse=True)
    for k in sorted_kanji_keys:
        if k in x:
            x = x.replace(k, f"_{MMD_KANJI_DICT[k]}_")

    # 漢数字の置換
    for k, v in KANJI_NUM_MAP.items():
        if k in x:
            x = x.replace(k, f"_{v}_")

    # カタカナをひらがなに統一
    x = _katakana_to_hiragana(x)

    # かなをローマ字に変換
    x = _kana_to_romaji(x)

    # 未知の漢字・非ASCII文字・記号の置換
    # 漢字（CJK統合漢字）の残りがある場合はアンダースコアに置換
    x = re.sub(r'[\u4E00-\u9FFF]', '_', x)
    # タイ文字等のその他非ラテン文字も置換
    x = re.sub(r'[\u0E00-\u0E7F]', '_', x)
    # 英数字とアンダースコア以外（記号・空白など）をアンダースコアに置換
    x = re.sub(r'[^a-zA-Z0-9_]', '_', x)

    # 連続するアンダースコアの圧縮と両端のトリム
    x = re.sub(r'_+', '_', x)
    x = x.strip('_')

    # 空文字になってしまった場合のフォールバック
    if not x:
        x = 'node'

    # Mayaノード名の仕様: 先頭が数字の場合は英字プレフィックスを付加
    if x[0] in '0123456789':
        digit_name = DIGIT_START_MAP.get(x[0], 'n')
        x = f"{digit_name}_{x[1:]}" if len(x) > 1 else digit_name

    return x

def safe_node_name(name, name_e=None, prefix="node", index=None):
    """
    日本語・中国語（簡体字/繁体字）・英語など多言語の文字列から、
    Mayaのノード名として完全に安全かつ衝突しにくい識別子を生成します。

    引数:
        name (str): 元の名称（日本語または中国語など）
        name_e (str, optional): 英語名称（PMXのname_eなど）
        prefix (str, optional): 名前の種別（'model', 'bone', 'mat', 'morph' など）
        index (int, optional): 要素のインデックス番号（一意性保証用）

    戻り値:
        str: Mayaノード名として有効な英数字・アンダースコア文字列
    """
    # 1. 英名（name_e）が有効に定義されている場合は最優先で検討
    if name_e:
        clean_e = str(name_e).strip()
        # 英数字とアンダースコアに正規化
        clean_e = re.sub(r'[^a-zA-Z0-9_]', '_', clean_e)
        clean_e = re.sub(r'_+', '_', clean_e).strip('_')
        # 有効な文字列が得られた場合
        if clean_e and not set(clean_e).issubset({'_'}):
            if clean_e[0] in '0123456789':
                clean_e = f"{prefix}_{clean_e}"
            if index is not None:
                return f"{clean_e}_{index:03d}" if len(clean_e) <= 3 else clean_e
            return clean_e

    # 日本語辞書および仮名によるローマ字変換
    candidate = romaji(name)

    # 辞書にない中国語漢字などですべて '_' または 'node' になってしまった場合のフォールバック
    if not candidate or candidate == 'node' or set(candidate).issubset({'_'}):
        # インデックスがある場合は明確な識別名（例: bone_001）を生成
        if index is not None:
            return f"{prefix}_{index:03d}"
        # 文字列のハッシュから安全な短い識別子を作成
        name_hash = abs(hash(str(name))) % 100000
        return f"{prefix}_{name_hash}"

    # インデックスが指定されており、候補名が極端に短い場合はインデックスを添える
    if index is not None and len(candidate) <= 2:
        return f"{candidate}_{index:03d}"

    return candidate
