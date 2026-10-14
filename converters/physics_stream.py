# -*- coding: utf-8 -*-
"""
MMD Tools for Maya - リアルタイム3D物理ビューア同期ストリーミングモジュール

新3D物理ビューア (MmdPhysicsViewer.exe) とプロセス間通信 (標準入出力 JSON Lines) を行い、
物理演算結果の揺れもの回転モーションをMayaへリアルタイムに同期・ベイクします。
"""

import os
import sys
import json
import math
import time
import subprocess
import maya.cmds as mc
import maya.OpenMaya as om

try:
    from PySide6.QtCore import QProcess, QProcessEnvironment, QObject, Signal, Qt
    from PySide6.QtWidgets import QApplication
except ImportError:
    from PySide2.QtCore import QProcess, QProcessEnvironment, QObject, Signal, Qt
    from PySide2.QtWidgets import QApplication

try:
    from . import vmdpaimaya
except Exception:
    import vmdpaimaya


def get_viewer_executable_path():
    """新3D物理ビューアの実行ファイルパスを取得"""
    plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(plugin_dir, "physics_bake_cs", "bin", "Release", "net8.0-windows", "MmdPhysicsViewer.exe"),
        os.path.join(plugin_dir, "physics_bake_cs", "bin", "Debug", "net8.0-windows", "MmdPhysicsViewer.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return candidates[0]


class PhysicsStreamingBaker(QObject):
    """
    3D物理ビューアとリアルタイム同期しながらMayaにキーフレームを書き込むクラス
    """
    def __init__(self, pmx_path, vmd_path, target_model=None, scale=8.0, lookahead=16, warmup=0.0, out_vmd=None, frame_offset=0, start_frame=None, end_frame=None, log_dialog=None):
        super(PhysicsStreamingBaker, self).__init__()
        self.pmx_path = pmx_path
        self.vmd_path = vmd_path
        self.target_model = target_model
        self.scale = scale
        self.lookahead = max(1, lookahead)
        self.warmup = max(0.0, float(warmup))
        self.out_vmd = out_vmd
        self.frame_offset = int(frame_offset)
        self.start_frame = int(start_frame) if start_frame is not None else None
        self.end_frame = int(end_frame) if end_frame is not None else None
        self.log_dialog = log_dialog

        self.process = None
        self.is_aborted = False
        self.is_finished = False

        self.joint_map = {}
        self.valid_joints = {}
        self.joint_rot_props = {}
        self.prev_joint_eulers = {}

        self.total_frames = 0
        self.max_frame = 0
        self.processed_frames = 0

    def run(self):
        """ストリーミングベイク処理の実行"""
        exe_path = get_viewer_executable_path()
        if not os.path.isfile(exe_path):
            msg = f"物理ビューアの実行ファイルが見つかりません:\n{exe_path}\n\n先に physics_bake_cs をビルドしてください。"
            if self.log_dialog:
                self.log_dialog.append_log(f"[エラー] {msg}\n")
            raise FileNotFoundError(msg)

        if not self.target_model:
            models = vmdpaimaya.get_available_mmd_models()
            if models:
                self.target_model = models[0][0]

        # ボーン構造マップの解決
        resolved_model, bone_map, _ = vmdpaimaya.resolve_model_structure(self.target_model)
        self.joint_map = bone_map if bone_map else vmdpaimaya._find_scene_joints(self.target_model)
        if resolved_model:
            self.target_model = resolved_model

        # Maya再生環境を30fps (ntsc) に同期
        try:
            mc.currentUnit(time='ntsc')
        except Exception:
            pass

        if self.log_dialog:
            self.log_dialog.append_log("--- リアルタイム物理ベイク (新3D物理ビューア連携) 開始 ---\n")
            self.log_dialog.append_log(f"PMXファイル: {self.pmx_path}\n")
            self.log_dialog.append_log(f"VMDファイル: {self.vmd_path}\n")
            self.log_dialog.append_log(f"対象モデル: {self.target_model or 'シーン内全域'}\n")
            self.log_dialog.append_log(f"先行フレーム数: {self.lookahead}\n")
            self.log_dialog.append_log(f"初期安定化時間: {self.warmup} 秒\n")
            if self.frame_offset != 0:
                self.log_dialog.append_log(f"フレームオフセット: {self.frame_offset} フレーム\n")
            if self.out_vmd and str(self.out_vmd).lower() != "none":
                self.log_dialog.append_log(f"出力VMDパス: {self.out_vmd}\n")
            self.log_dialog.append_log("\n")

        # 大量キーフレーム書き込みによるメモリ圧迫防止のためUndoを一時停止
        undo_state = mc.undoInfo(query=True, state=True)
        mc.undoInfo(stateWithoutFlush=False)

        try:
            return self._execute_stream(exe_path)
        finally:
            mc.undoInfo(stateWithoutFlush=undo_state)

    def _execute_stream(self, exe_path):
        """プロセス起動および通信イベントループ"""
        self.process = QProcess()
        env = QProcessEnvironment.systemEnvironment()
        self.process.setProcessEnvironment(env)

        args = [
            "--pmx", self.pmx_path,
            "--vmd", self.vmd_path,
            "--lookahead", str(self.lookahead),
            "--warmup", str(self.warmup)
        ]
        if self.start_frame is not None:
            args.extend(["--start-frame", str(self.start_frame)])
        if self.end_frame is not None:
            args.extend(["--end-frame", str(self.end_frame)])
        if self.out_vmd:
            args.extend(["--out-vmd", str(self.out_vmd)])

        if self.log_dialog:
            self.log_dialog.append_log("新3D物理ビューアを起動中...\n")

        self.process.start(exe_path, args)
        if not self.process.waitForStarted(8000):
            err = self.process.errorString()
            if self.log_dialog:
                self.log_dialog.append_log(f"[エラー] ビューアの起動に失敗しました: {err}\n")
            return False

        if self.log_dialog:
            self.log_dialog.append_log("新3D物理ビューアが起動しました。物理ストリーミング受信中...\n\n")

        # イベントループで標準出力を取得
        line_buffer = ""
        while self.process.state() == QProcess.Running or self.process.bytesAvailable() > 0:
            if self.log_dialog and self.log_dialog.check_cancelled():
                self._cancel_and_terminate()
                return False

            has_data = False
            while self.process.bytesAvailable() > 0:
                has_data = True
                data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
                line_buffer += data
                while "\n" in line_buffer:
                    line, line_buffer = line_buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_message(line)

            if self.is_finished:
                break

            if not has_data and self.process.state() == QProcess.Running:
                self.process.waitForReadyRead(20)

            QApplication.processEvents()

        # 残りのバッファを処理
        if line_buffer.strip():
            self._handle_message(line_buffer.strip())

        # アニメーションカーブの補間をスプラインに設定
        for j_node in self.valid_joints.values():
            try:
                mc.keyTangent(j_node, edit=True, inTangentType='spline', outTangentType='spline')
            except Exception:
                pass

        if self.log_dialog:
            self.log_dialog.append_log("\nリアルタイム物理ベイクが正常に完了しました。\n")

        return True

    def _handle_message(self, line):
        """ビューアから受信したJSONメッセージを処理"""
        try:
            msg = json.loads(line)
        except Exception:
            return

        msg_type = msg.get("type", "")

        if msg_type == "hello":
            self.total_frames = msg.get("total_frames", 0)
            self.max_frame = msg.get("max_frame", 0)
            target_bones = msg.get("physics_bones", [])

            if self.log_dialog:
                self.log_dialog.append_log(f"接続確立: 総 {self.total_frames} フレーム (最大フレーム: {self.max_frame})\n")
                self.log_dialog.append_log(f"揺れもの対象ボーン数: {len(target_bones)} 本\n\n")

            self._prepare_joints(target_bones)

        elif msg_type == "frame":
            f = msg.get("frame", 0)
            bones_data = msg.get("bones", {})
            self._apply_frame_bones(f, bones_data)
            self._send_ack(f)

            self.processed_frames = f + 1
            if self.log_dialog:
                self.log_dialog.update_progress(
                    self.processed_frames,
                    self.total_frames,
                    step_idx=self.processed_frames,
                    total_steps=self.total_frames,
                    label_prefix="ベイク進捗",
                    unit="フレーム"
                )

        elif msg_type == "done":
            vmd_path = msg.get("vmd_path", "")
            if self.log_dialog:
                self.log_dialog.append_log(f"\n物理ベイクVMDファイルを保存しました:\n{vmd_path}\n")
            self.is_finished = True

        elif msg_type == "error":
            err_msg = msg.get("message", "不明なエラー")
            if self.log_dialog:
                self.log_dialog.append_log(f"[ビューアエラー] {err_msg}\n")
            self.is_finished = True

    def _prepare_joints(self, target_bones):
        """対象ジョイントを探索し、既存の回転キーフレームをクリーンアップ"""
        self.valid_joints.clear()
        self.joint_rot_props.clear()
        self.prev_joint_eulers.clear()

        for bone_name in target_bones:
            candidate = vmdpaimaya._match_bone_to_joint(bone_name, self.joint_map)
            if candidate:
                resolved = vmdpaimaya._resolve_full_joint_path(candidate, self.target_model)
                if resolved and mc.objExists(resolved):
                    self.valid_joints[bone_name] = resolved

                    try:
                        jo = mc.getAttr(f"{resolved}.jointOrient")[0]
                        jo_e = om.MEulerRotation(math.radians(jo[0]), math.radians(jo[1]), math.radians(jo[2]), om.MEulerRotation.kXYZ)
                        inv_jo_q = jo_e.asQuaternion().inverse()

                        ra = mc.getAttr(f"{resolved}.rotateAxis")[0]
                        ra_e = om.MEulerRotation(math.radians(ra[0]), math.radians(ra[1]), math.radians(ra[2]), om.MEulerRotation.kXYZ)
                        inv_ra_q = ra_e.asQuaternion().inverse()

                        ro = mc.getAttr(f"{resolved}.rotateOrder")
                        self.joint_rot_props[resolved] = (inv_jo_q, inv_ra_q, ro)
                    except Exception:
                        self.joint_rot_props[resolved] = (om.MQuaternion(), om.MQuaternion(), 0)

                    # 既存の回転キーフレームを削除（範囲指定がある場合はその範囲のみクリア）
                    try:
                        if self.start_frame is not None and self.end_frame is not None:
                            mc.cutKey(resolved, attribute=['rotateX', 'rotateY', 'rotateZ'], time=(self.start_frame, self.end_frame), clear=True)
                        else:
                            mc.cutKey(resolved, attribute=['rotateX', 'rotateY', 'rotateZ'], clear=True)
                    except Exception:
                        pass

        # ジョイント照合ログを出力
        if self.log_dialog:
            matched_count = len(self.valid_joints)
            total_count = len(target_bones)
            self.log_dialog.append_log(f"ジョイント照合結果: {total_count} 本中 {matched_count} 本のMayaジョイントに接続成功\n")
            unmatched = [b for b in target_bones if b not in self.valid_joints]
            if unmatched:
                sample_unmatched = ", ".join(unmatched[:10])
                if len(unmatched) > 10:
                    sample_unmatched += f" 他 {len(unmatched)-10} 本"
                self.log_dialog.append_log(f"  ※シーン未検出ジョイント: {sample_unmatched}\n")
            if self.start_frame is not None and self.end_frame is not None:
                self.log_dialog.append_log(f"ベイク範囲指定: {self.start_frame} ～ {self.end_frame} フレーム\n")
            self.log_dialog.append_log("\n")

    def _apply_frame_bones(self, frame_num, bones_data):
        """各ボーンのクォータニオン回転をMayaのオイラー角に変換してキー設定"""
        target_frame = frame_num + self.frame_offset

        # 指定フレーム範囲外の場合はキー打鍵をスキップ
        in_range = True
        if self.start_frame is not None and target_frame < self.start_frame:
            in_range = False
        if self.end_frame is not None and target_frame > self.end_frame:
            in_range = False

        if in_range:
            for bone_name, q in bones_data.items():
                if bone_name not in self.valid_joints:
                    continue

                j_node = self.valid_joints[bone_name]
                inv_jo_q, inv_ra_q, ro = self.joint_rot_props.get(j_node, (om.MQuaternion(), om.MQuaternion(), 0))

                try:
                    # MMD左手系からMaya右手系への変換 (Z軸反転)
                    qx, qy, qz, qw = q
                    q_maya = om.MQuaternion(-qx, -qy, qz, qw)

                    local_rot_q = inv_jo_q * q_maya * inv_ra_q

                    euler = local_rot_q.asEulerRotation()
                    euler.reorderIt(ro)

                    # 最短オイラー角解決（フリップ防止）
                    if j_node in self.prev_joint_eulers:
                        euler = euler.closestSolution(self.prev_joint_eulers[j_node])
                    self.prev_joint_eulers[j_node] = euler

                    rx = math.degrees(euler.x)
                    ry = math.degrees(euler.y)
                    rz = math.degrees(euler.z)

                    mc.setKeyframe(j_node, attribute='rotateX', time=target_frame, value=rx)
                    mc.setKeyframe(j_node, attribute='rotateY', time=target_frame, value=ry)
                    mc.setKeyframe(j_node, attribute='rotateZ', time=target_frame, value=rz)
                except Exception:
                    pass

        # Mayaのタイムスライダーを進め、ビューポートを同期描画
        try:
            mc.currentTime(target_frame, update=True)
            mc.refresh()
        except Exception:
            pass

    def _send_ack(self, frame_num):
        """ビューアへACKを送信"""
        if self.process and self.process.state() == QProcess.Running:
            ack_msg = json.dumps({"type": "ack", "frame": frame_num}) + "\n"
            self.process.write(ack_msg.encode("utf-8"))
            self.process.waitForBytesWritten(100)

    def _cancel_and_terminate(self):
        """中断処理"""
        self.is_aborted = True
        if self.process and self.process.state() == QProcess.Running:
            cancel_msg = json.dumps({"type": "cancel"}) + "\n"
            try:
                self.process.write(cancel_msg.encode("utf-8"))
                self.process.waitForBytesWritten(500)
            except Exception:
                pass
            self.process.terminate()
            self.process.waitForFinished(1000)
            if self.process.state() == QProcess.Running:
                self.process.kill()


def stream_bake_physics(pmx_path, vmd_path, target_model=None, scale=8.0, lookahead=16, warmup=0.0, out_vmd=None, frame_offset=0, start_frame=None, end_frame=None, log_dialog=None):
    """
    外部から呼び出し可能なエントリーポイント関数
    """
    baker = PhysicsStreamingBaker(
        pmx_path=pmx_path,
        vmd_path=vmd_path,
        target_model=target_model,
        scale=scale,
        lookahead=lookahead,
        warmup=warmup,
        out_vmd=out_vmd,
        frame_offset=frame_offset,
        start_frame=start_frame,
        end_frame=end_frame,
        log_dialog=log_dialog
    )
    return baker.run()
