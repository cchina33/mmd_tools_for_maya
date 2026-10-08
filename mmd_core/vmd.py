# -*- coding: utf-8 -*-
"""
mmd_core.vmd - MMD モーションデータ (VMD: Vocaloid Motion Data) バイナリパーサー

外部ライブラリ非依存、Python標準の struct モジュールのみで
ボーンキーフレーム、表情（モーフ）、カメラ、照明、表示・IK切り替えを
完全解析します。
"""

import struct
import os

def _decode_sjis(raw_bytes):
    """VMD文字列（Shift_JIS、0x00または0xFDパディング）を安全にデコードします。"""
    trimmed = raw_bytes.split(b'\x00')[0].split(b'\xfd')[0]
    for enc in ['cp932', 'shift_jis', 'utf-8', 'gbk']:
        try:
            return trimmed.decode(enc)
        except Exception:
            pass
    return trimmed.decode('latin1', errors='replace')

class VmdBoneFrame:
    """ボーンキーフレーム要素データ (111バイト/個)"""
    def __init__(self):
        self.name = ""
        self.frame = 0
        self.position = [0.0, 0.0, 0.0]
        self.rotation = [0.0, 0.0, 0.0, 1.0] # クォータニオン (qx, qy, qz, qw)
        self.interpolation = b"" # 64バイトの補間ベジェパラメータ

    def __repr__(self):
        return f"<VmdBoneFrame {self.name} f={self.frame} pos={self.position} rot={self.rotation}>"

class VmdMorphFrame:
    """表情（モーフ）キーフレーム要素データ (23バイト/個)"""
    def __init__(self):
        self.name = ""
        self.frame = 0
        self.weight = 0.0 # 0.0 〜 1.0

    def __repr__(self):
        return f"<VmdMorphFrame {self.name} f={self.frame} weight={self.weight}>"

class VmdCameraFrame:
    """カメラキーフレーム要素データ (61バイト/個)"""
    def __init__(self):
        self.frame = 0
        self.distance = 0.0
        self.position = [0.0, 0.0, 0.0] # 目標点（注視点）位置
        self.rotation = [0.0, 0.0, 0.0] # カメラ回転 (ラジアン: rx, ry, rz)
        self.interpolation = b"" # 24バイトの補間パラメータ
        self.fov = 30 # 視野角 (度)
        self.perspective = True # True: パースペクティブ, False: 正射投影

    def __repr__(self):
        return f"<VmdCameraFrame f={self.frame} dist={self.distance} pos={self.position} rot={self.rotation} fov={self.fov}>"

class VmdLightFrame:
    """照明キーフレーム要素データ (28バイト/個)"""
    def __init__(self):
        self.frame = 0
        self.color = [1.0, 1.0, 1.0] # RGB (0.0 〜 1.0)
        self.position = [0.0, 0.0, 0.0] # 照明ベクトル

    def __repr__(self):
        return f"<VmdLightFrame f={self.frame} color={self.color} pos={self.position}>"

class VmdShadowFrame:
    """セルフ影キーフレーム要素データ (9バイト/個)"""
    def __init__(self):
        self.frame = 0
        self.mode = 0 # 0: OFF, 1: mode1, 2: mode2
        self.distance = 0.0

class VmdIkInfo:
    """個別のIK on/off情報 (21バイト/個)"""
    def __init__(self, name="", enabled=True):
        self.name = name
        self.enabled = enabled

class VmdShowIkFrame:
    """モデル表示・IK on/offキーフレーム要素データ"""
    def __init__(self):
        self.frame = 0
        self.show = True
        self.ik_list = [] # [VmdIkInfo, ...]

class VmdMotion:
    """VMDモーション全体を格納するコンテナクラス"""
    def __init__(self):
        self.version = 2 # 1: v1 (MMD ver2以前), 2: v2 (MMD ver3以降)
        self.model_name = ""
        self.bone_frames = {} # ボーン名: [VmdBoneFrame, ...] (フレーム順ソート済み)
        self.morph_frames = {} # モーフ名: [VmdMorphFrame, ...] (フレーム順ソート済み)
        self.camera_frames = [] # [VmdCameraFrame, ...]
        self.light_frames = [] # [VmdLightFrame, ...]
        self.shadow_frames = [] # [VmdShadowFrame, ...]
        self.ik_frames = [] # [VmdShowIkFrame, ...]
        self.max_frame = 0

    @property
    def is_camera_motion(self):
        """カメラ・照明用のモーションかどうかを判定します。"""
        return "カメラ" in self.model_name or len(self.camera_frames) > 0

    def get_bone_names(self):
        """アニメーションが含まれる全ボーン名の一覧を返します。"""
        return list(self.bone_frames.keys())

    def get_morph_names(self):
        """アニメーションが含まれる全モーフ名の一覧を返します。"""
        return list(self.morph_frames.keys())

def load(file_path):
    """
    VMDモーションファイルを読み込み、VmdMotion オブジェクトを返します。

    引数:
        file_path (str): .vmd ファイルの絶対パス
    戻り値:
        VmdMotion: 解析されたモーションデータ
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"VMDファイルが見つかりません: {file_path}")

    motion = VmdMotion()
    max_frame = 0

    with open(file_path, 'rb') as f:
        # ヘッダー (30バイト)
        header_raw = f.read(30)
        if len(header_raw) < 30:
            raise ValueError("無効なVMDファイルです（ヘッダーが短すぎます）")

        header_str = header_raw.split(b'\x00')[0].decode('latin1', errors='replace')
        if header_str.startswith("Vocaloid Motion Data 0002"):
            motion.version = 2
            model_name_raw = f.read(20)
        elif header_str.startswith("Vocaloid Motion Data"):
            motion.version = 1
            model_name_raw = f.read(10)
        else:
            raise ValueError(f"未対応のVMDヘッダーです: {header_str}")

        motion.model_name = _decode_sjis(model_name_raw)

        # ボーンキーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            bone_count = struct.unpack('<I', buf)[0]
            for _ in range(bone_count):
                record = f.read(111)
                if len(record) < 111:
                    break
                b_name_raw = record[0:15]
                b_name = _decode_sjis(b_name_raw)
                frame = struct.unpack('<I', record[15:19])[0]
                px, py, pz = struct.unpack('<3f', record[19:31])
                qx, qy, qz, qw = struct.unpack('<4f', record[31:47])
                bezier = record[47:111]

                bf = VmdBoneFrame()
                bf.name = b_name
                bf.frame = frame
                bf.position = [px, py, pz]
                bf.rotation = [qx, qy, qz, qw]
                bf.interpolation = bezier

                if b_name not in motion.bone_frames:
                    motion.bone_frames[b_name] = []
                motion.bone_frames[b_name].append(bf)

                if frame > max_frame:
                    max_frame = frame

        # 各ボーンのキーフレームをフレーム順に整列
        for b_name in motion.bone_frames:
            motion.bone_frames[b_name].sort(key=lambda x: x.frame)

        # 表情（モーフ）キーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            morph_count = struct.unpack('<I', buf)[0]
            for _ in range(morph_count):
                record = f.read(23)
                if len(record) < 23:
                    break
                m_name_raw = record[0:15]
                m_name = _decode_sjis(m_name_raw)
                frame = struct.unpack('<I', record[15:19])[0]
                weight = struct.unpack('<f', record[19:23])[0]

                mf = VmdMorphFrame()
                mf.name = m_name
                mf.frame = frame
                mf.weight = weight

                if m_name not in motion.morph_frames:
                    motion.morph_frames[m_name] = []
                motion.morph_frames[m_name].append(mf)

                if frame > max_frame:
                    max_frame = frame

        # 各モーフのキーフレームをフレーム順に整列
        for m_name in motion.morph_frames:
            motion.morph_frames[m_name].sort(key=lambda x: x.frame)

        # カメラキーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            cam_count = struct.unpack('<I', buf)[0]
            for _ in range(cam_count):
                record = f.read(61)
                if len(record) < 61:
                    break
                frame = struct.unpack('<I', record[0:4])[0]
                dist = struct.unpack('<f', record[4:8])[0]
                px, py, pz = struct.unpack('<3f', record[8:20])
                rx, ry, rz = struct.unpack('<3f', record[20:32])
                bezier = record[32:56]
                fov = struct.unpack('<I', record[56:60])[0]
                perspective = (record[60] == 0)

                cf = VmdCameraFrame()
                cf.frame = frame
                cf.distance = dist
                cf.position = [px, py, pz]
                cf.rotation = [rx, ry, rz]
                cf.interpolation = bezier
                cf.fov = fov
                cf.perspective = perspective
                motion.camera_frames.append(cf)

                if frame > max_frame:
                    max_frame = frame

            motion.camera_frames.sort(key=lambda x: x.frame)

        # 照明キーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            light_count = struct.unpack('<I', buf)[0]
            for _ in range(light_count):
                record = f.read(28)
                if len(record) < 28:
                    break
                frame = struct.unpack('<I', record[0:4])[0]
                r, g, b = struct.unpack('<3f', record[4:16])
                lx, ly, lz = struct.unpack('<3f', record[16:28])

                lf = VmdLightFrame()
                lf.frame = frame
                lf.color = [r, g, b]
                lf.position = [lx, ly, lz]
                motion.light_frames.append(lf)

                if frame > max_frame:
                    max_frame = frame

            motion.light_frames.sort(key=lambda x: x.frame)

        # セルフ影キーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            shadow_count = struct.unpack('<I', buf)[0]
            for _ in range(shadow_count):
                record = f.read(9)
                if len(record) < 9:
                    break
                frame = struct.unpack('<I', record[0:4])[0]
                mode = record[4]
                dist = struct.unpack('<f', record[5:9])[0]

                sf = VmdShadowFrame()
                sf.frame = frame
                sf.mode = mode
                sf.distance = dist
                motion.shadow_frames.append(sf)

            motion.shadow_frames.sort(key=lambda x: x.frame)

        # モデル表示・IK on/offキーフレーム読み取り
        buf = f.read(4)
        if len(buf) == 4:
            ik_count_frames = struct.unpack('<I', buf)[0]
            for _ in range(ik_count_frames):
                frame_buf = f.read(5)
                if len(frame_buf) < 5:
                    break
                frame = struct.unpack('<I', frame_buf[0:4])[0]
                show = (frame_buf[4] != 0)

                sub_buf = f.read(4)
                if len(sub_buf) < 4:
                    break
                num_ik = struct.unpack('<I', sub_buf)[0]

                s_frame = VmdShowIkFrame()
                s_frame.frame = frame
                s_frame.show = show

                for _ in range(num_ik):
                    ik_rec = f.read(21)
                    if len(ik_rec) < 21:
                        break
                    ik_name = _decode_sjis(ik_rec[0:20])
                    ik_on = (ik_rec[20] != 0)
                    s_frame.ik_list.append(VmdIkInfo(ik_name, ik_on))

                motion.ik_frames.append(s_frame)

                if frame > max_frame:
                    max_frame = frame

            motion.ik_frames.sort(key=lambda x: x.frame)

    motion.max_frame = max_frame
    return motion
