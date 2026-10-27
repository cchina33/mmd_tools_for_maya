using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

namespace MmdPhysicsBridge
{
    // VMDボーンキーフレーム
    public class VmdBoneKeyframe
    {
        public int Frame { get; set; }
        public float Tx { get; set; }
        public float Ty { get; set; }
        public float Tz { get; set; }
        public float Qx { get; set; }
        public float Qy { get; set; }
        public float Qz { get; set; }
        public float Qw { get; set; } = 1.0f;
        public byte[]? Interpolation { get; set; }
    }

    // VMDモーフキーフレーム
    public class VmdMorphKeyframe
    {
        public int Frame { get; set; }
        public float Weight { get; set; }
    }

    // VMDモーション全体データ
    public class VmdMotionData
    {
        public string ModelName { get; set; } = "";
        public int MaxFrame { get; set; }
        public Dictionary<string, List<VmdBoneKeyframe>> BoneTracks { get; set; } = new();
        public Dictionary<string, List<VmdMorphKeyframe>> MorphTracks { get; set; } = new();

        // 指定フレームにおける特定モーフの適用率 (0.0 〜 1.0) を線形補間取得
        public float SampleMorph(string morphName, float frame)
        {
            if (!MorphTracks.TryGetValue(morphName, out var track) || track.Count == 0)
            {
                return 0.0f;
            }

            if (frame <= track[0].Frame) return track[0].Weight;
            if (frame >= track[^1].Frame) return track[^1].Weight;

            int idx = track.FindIndex(k => k.Frame >= frame);
            if (idx <= 0) return track[0].Weight;

            var k0 = track[idx - 1];
            var k1 = track[idx];

            float factor = (frame - k0.Frame) / (k1.Frame - k0.Frame);
            return k0.Weight + (k1.Weight - k0.Weight) * factor;
        }

        // IKボーンごとのON/OFFキーフレーム (フレーム番号, 有効フラグ) をフレーム昇順で保持
        public Dictionary<string, List<(int Frame, bool Enabled)>> IkTracks { get; set; } = new();

        // 指定フレームでIKが有効かどうかを判定 (キーが無い場合は有効扱い)
        public bool IsIkEnabled(string ikBoneName, float frame)
        {
            if (!IkTracks.TryGetValue(ikBoneName, out var track) || track.Count == 0) return true;

            bool enabled = track[0].Enabled;
            foreach (var k in track)
            {
                if (k.Frame > frame) break;
                enabled = k.Enabled;
            }
            return enabled;
        }

    // VMD 3次ベジェ補間曲線評価クラス
    public static class VmdBezierEvaluator
    {
        // チャンネルごとの進捗率 (0.0 〜 1.0) を算出
        // channelIndex: 0=X移動, 1=Y移動, 2=Z移動, 3=回転
        public static float Evaluate(byte[]? interp, int channelIndex, float t)
        {
            if (t <= 0.0f) return 0.0f;
            if (t >= 1.0f) return 1.0f;
            if (interp == null || interp.Length < 16) return t;

            int c = channelIndex;
            byte x1Byte = interp[c];
            byte y1Byte = interp[4 + c];
            byte x2Byte = interp[8 + c];
            byte y2Byte = interp[12 + c];

            if (x1Byte == y1Byte && x2Byte == y2Byte)
            {
                return t;
            }

            float x1 = x1Byte / 127.0f;
            float y1 = y1Byte / 127.0f;
            float x2 = x2Byte / 127.0f;
            float y2 = y2Byte / 127.0f;

            // ニュートン・ラフソン法による媒介変数 u の求解 (x(u) = t)
            float u = t;
            bool solved = false;
            for (int i = 0; i < 16; i++)
            {
                float oneMinusU = 1.0f - u;
                float u2 = u * u;
                float o2 = oneMinusU * oneMinusU;

                float xu = (3.0f * o2 * u * x1) + (3.0f * oneMinusU * u2 * x2) + (u2 * u);
                float diff = xu - t;
                if (MathF.Abs(diff) < 1e-5f)
                {
                    solved = true;
                    break;
                }

                // 導関数 dx/du
                float dx = (3.0f * o2 * x1) + (6.0f * oneMinusU * u * (x2 - x1)) + (3.0f * u2 * (1.0f - x2));
                if (MathF.Abs(dx) < 1e-6f)
                {
                    break;
                }

                u = Math.Clamp(u - (diff / dx), 0.0f, 1.0f);
            }

            // ニュートン法で収束しなかった場合の二分法フォールバック
            if (!solved)
            {
                float uMin = 0.0f;
                float uMax = 1.0f;
                u = t;
                for (int i = 0; i < 16; i++)
                {
                    float oneMinusU = 1.0f - u;
                    float u2 = u * u;
                    float o2 = oneMinusU * oneMinusU;
                    float xu = (3.0f * o2 * u * x1) + (3.0f * oneMinusU * u2 * x2) + (u2 * u);
                    if (MathF.Abs(xu - t) < 1e-5f)
                    {
                        break;
                    }
                    if (xu < t)
                    {
                        uMin = u;
                    }
                    else
                    {
                        uMax = u;
                    }
                    u = (uMin + uMax) * 0.5f;
                }
            }

            float omU = 1.0f - u;
            return (3.0f * omU * omU * u * y1) + (3.0f * omU * u * u * y2) + (u * u * u);
        }
    }

        // 指定フレームにおける特定ボーンのローカル姿勢（移動・回転）を補間取得
        public (float[] Translation, float[] RotationQuat) SampleBone(string boneName, float frame)
        {
            if (!BoneTracks.TryGetValue(boneName, out var track) || track.Count == 0)
            {
                return (new float[] { 0, 0, 0 }, new float[] { 0, 0, 0, 1 });
            }

            if (frame <= track[0].Frame)
            {
                var k = track[0];
                return (new float[] { k.Tx, k.Ty, k.Tz }, new float[] { k.Qx, k.Qy, k.Qz, k.Qw });
            }

            if (frame >= track[^1].Frame)
            {
                var k = track[^1];
                return (new float[] { k.Tx, k.Ty, k.Tz }, new float[] { k.Qx, k.Qy, k.Qz, k.Qw });
            }

            // 直前・直後のキーフレーム探索
            int idx = track.FindIndex(k => k.Frame >= frame);
            if (idx <= 0)
            {
                var k = track[0];
                return (new float[] { k.Tx, k.Ty, k.Tz }, new float[] { k.Qx, k.Qy, k.Qz, k.Qw });
            }

            var k0 = track[idx - 1];
            var k1 = track[idx];

            float factor = (float)(frame - k0.Frame) / (k1.Frame - k0.Frame);

            // MMD仕様: k0からk1への遷移補間にはk1の補間曲線パラメータを使用
            float factorX = VmdBezierEvaluator.Evaluate(k1.Interpolation, 0, factor);
            float factorY = VmdBezierEvaluator.Evaluate(k1.Interpolation, 1, factor);
            float factorZ = VmdBezierEvaluator.Evaluate(k1.Interpolation, 2, factor);
            float factorR = VmdBezierEvaluator.Evaluate(k1.Interpolation, 3, factor);

            // 並進のベジェ補間
            float tx = k0.Tx + (k1.Tx - k0.Tx) * factorX;
            float ty = k0.Ty + (k1.Ty - k0.Ty) * factorY;
            float tz = k0.Tz + (k1.Tz - k0.Tz) * factorZ;

            // クォータニオンの球面線形補間 (Slerp) に回転進捗率 factorR を適用
            float qx, qy, qz, qw;
            float cosOmega = (k0.Qx * k1.Qx) + (k0.Qy * k1.Qy) + (k0.Qz * k1.Qz) + (k0.Qw * k1.Qw);
            float sign = 1.0f;
            if (cosOmega < 0.0f)
            {
                cosOmega = -cosOmega;
                sign = -1.0f;
            }

            if (cosOmega > 0.9995f)
            {
                qx = k0.Qx + (sign * k1.Qx - k0.Qx) * factorR;
                qy = k0.Qy + (sign * k1.Qy - k0.Qy) * factorR;
                qz = k0.Qz + (sign * k1.Qz - k0.Qz) * factorR;
                qw = k0.Qw + (sign * k1.Qw - k0.Qw) * factorR;
            }
            else
            {
                float omega = MathF.Acos(cosOmega);
                float sinOmega = MathF.Sin(omega);
                float scale0 = MathF.Sin((1.0f - factorR) * omega) / sinOmega;
                float scale1 = MathF.Sin(factorR * omega) / sinOmega * sign;

                qx = (k0.Qx * scale0) + (k1.Qx * scale1);
                qy = (k0.Qy * scale0) + (k1.Qy * scale1);
                qz = (k0.Qz * scale0) + (k1.Qz * scale1);
                qw = (k0.Qw * scale0) + (k1.Qw * scale1);
            }

            // クォータニオンの安全な正規化
            float len = MathF.Sqrt((qx * qx) + (qy * qy) + (qz * qz) + (qw * qw));
            if (float.IsNaN(len) || float.IsInfinity(len) || len < 0.0001f)
            {
                qx = 0.0f; qy = 0.0f; qz = 0.0f; qw = 1.0f;
            }
            else
            {
                float invLen = 1.0f / len;
                qx *= invLen; qy *= invLen; qz *= invLen; qw *= invLen;
            }

            return (new float[] { tx, ty, tz }, new float[] { qx, qy, qz, qw });
        }
    }

    // VMDローダークラス
    public static class VmdLoader
    {
        // 固定長バイナリフィールドからNULL終端文字列を安全に取得するヘルパー
        private static string ReadFixedString(BinaryReader reader, int length, Encoding encoding)
        {
            byte[] bytes = reader.ReadBytes(length);
            int nullIdx = Array.IndexOf(bytes, (byte)0);
            if (nullIdx < 0) nullIdx = bytes.Length;
            return encoding.GetString(bytes, 0, nullIdx);
        }

        public static VmdMotionData Load(string filePath)
        {
            if (!File.Exists(filePath))
            {
                throw new FileNotFoundException($"VMDファイルが見つかりません: {filePath}");
            }

            // Shift-JISプロバイダの登録
            Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
            Encoding sjis = Encoding.GetEncoding("shift_jis");

            using var stream = File.OpenRead(filePath);
            using var reader = new BinaryReader(stream);

            // ヘッダー確認 (30バイト)
            string header = ReadFixedString(reader, 30, Encoding.ASCII);
            if (!header.StartsWith("Vocaloid Motion Data"))
            {
                throw new InvalidDataException("有効なVMDモーションファイルではありません。");
            }

            // モデル名 (20バイト)
            string modelName = ReadFixedString(reader, 20, sjis);

            var vmd = new VmdMotionData
            {
                ModelName = modelName
            };

            // ボーンキーフレーム読み込み
            int keyframeCount = reader.ReadInt32();
            int maxFrame = 0;

            for (int i = 0; i < keyframeCount; i++)
            {
                // ボーン名 (15バイト、NULL終端以降を除去)
                string boneName = ReadFixedString(reader, 15, sjis);

                uint frameNum = reader.ReadUInt32();
                float tx = reader.ReadSingle();
                float ty = reader.ReadSingle();
                float tz = reader.ReadSingle();
                float qx = reader.ReadSingle();
                float qy = reader.ReadSingle();
                float qz = reader.ReadSingle();
                float qw = reader.ReadSingle();

                // クォータニオンの破損データ・ゼロ除算サニタイズと正規化
                float qLenSq = (qx * qx) + (qy * qy) + (qz * qz) + (qw * qw);
                if (float.IsNaN(qLenSq) || float.IsInfinity(qLenSq) || qLenSq < 1e-8f)
                {
                    qx = 0.0f;
                    qy = 0.0f;
                    qz = 0.0f;
                    qw = 1.0f;
                }
                else
                {
                    float invLen = 1.0f / MathF.Sqrt(qLenSq);
                    qx *= invLen;
                    qy *= invLen;
                    qz *= invLen;
                    qw *= invLen;
                }

                // 補間曲線 (64バイト) 取得
                byte[] interp = reader.ReadBytes(64);

                var key = new VmdBoneKeyframe
                {
                    Frame = (int)frameNum,
                    Tx = tx,
                    Ty = ty,
                    Tz = tz,
                    Qx = qx,
                    Qy = qy,
                    Qz = qz,
                    Qw = qw,
                    Interpolation = interp
                };

                if (!vmd.BoneTracks.TryGetValue(boneName, out var track))
                {
                    track = new List<VmdBoneKeyframe>();
                    vmd.BoneTracks[boneName] = track;
                }
                track.Add(key);

                if ((int)frameNum > maxFrame)
                {
                    maxFrame = (int)frameNum;
                }
            }

            // フレーム番号順にソート
            foreach (var track in vmd.BoneTracks.Values)
            {
                track.Sort((a, b) => a.Frame.CompareTo(b.Frame));
            }

            vmd.MaxFrame = maxFrame;

            // 後続セクション (モーフ・カメラ・照明・セルフ影・表示IK) の読み込み
            // 古い形式のVMDでは途中でファイルが終わるため、読み込めた範囲だけ採用する
            try
            {
                int morphCount = reader.ReadInt32();
                for (int i = 0; i < morphCount; i++)
                {
                    string morphName = ReadFixedString(reader, 15, sjis);
                    uint frameNum = reader.ReadUInt32();
                    float weight = reader.ReadSingle();

                    var key = new VmdMorphKeyframe
                    {
                        Frame = (int)frameNum,
                        Weight = weight
                    };

                    if (!vmd.MorphTracks.TryGetValue(morphName, out var track))
                    {
                        track = new List<VmdMorphKeyframe>();
                        vmd.MorphTracks[morphName] = track;
                    }
                    track.Add(key);

                    if ((int)frameNum > vmd.MaxFrame)
                    {
                        vmd.MaxFrame = (int)frameNum;
                    }
                }

                foreach (var track in vmd.MorphTracks.Values)
                {
                    track.Sort((a, b) => a.Frame.CompareTo(b.Frame));
                }

                int cameraCount = reader.ReadInt32();
                stream.Seek((long)cameraCount * 61, SeekOrigin.Current);

                int lightCount = reader.ReadInt32();
                stream.Seek((long)lightCount * 28, SeekOrigin.Current);

                int shadowCount = reader.ReadInt32();
                stream.Seek((long)shadowCount * 9, SeekOrigin.Current);

                int ikFrameCount = reader.ReadInt32();
                for (int i = 0; i < ikFrameCount; i++)
                {
                    int frame = (int)reader.ReadUInt32();
                    reader.ReadByte(); // 表示フラグ
                    int ikCount = reader.ReadInt32();
                    for (int j = 0; j < ikCount; j++)
                    {
                        string ikName = ReadFixedString(reader, 20, sjis);
                        bool enabled = reader.ReadByte() != 0;

                        if (!vmd.IkTracks.TryGetValue(ikName, out var ikTrack))
                        {
                            ikTrack = new List<(int Frame, bool Enabled)>();
                            vmd.IkTracks[ikName] = ikTrack;
                        }
                        ikTrack.Add((frame, enabled));
                    }
                }

                foreach (var ikTrack in vmd.IkTracks.Values)
                {
                    ikTrack.Sort((a, b) => a.Frame.CompareTo(b.Frame));
                }
            }
            catch (EndOfStreamException)
            {
                // 表示・IKセクションが無いVMDはIK常時有効として扱う
            }

            return vmd;
        }

        // VMDモーションデータのバイナリ書き出し (MMM物理書き込み互換)
        public static void SaveVmd(string filePath, VmdMotionData vmd)
        {
            Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
            var sjis = Encoding.GetEncoding("shift_jis");

            using var stream = File.Create(filePath);
            using var writer = new BinaryWriter(stream);

            // ヘッダー (30バイト): "Vocaloid Motion Data 0002\0"
            byte[] headerBytes = new byte[30];
            byte[] rawHeader = Encoding.ASCII.GetBytes("Vocaloid Motion Data 0002");
            Array.Copy(rawHeader, headerBytes, Math.Min(rawHeader.Length, 30));
            writer.Write(headerBytes);

            // モデル名 (20バイト)
            byte[] modelBytes = new byte[20];
            if (!string.IsNullOrEmpty(vmd.ModelName))
            {
                byte[] rawModel = sjis.GetBytes(vmd.ModelName);
                Array.Copy(rawModel, modelBytes, Math.Min(rawModel.Length, 20));
            }
            writer.Write(modelBytes);

            // ボーンキーフレーム数
            int totalBoneKeys = 0;
            foreach (var track in vmd.BoneTracks.Values)
            {
                totalBoneKeys += track.Count;
            }
            writer.Write(totalBoneKeys);

            // デフォルト補間曲線 (64バイト)
            byte[] defaultInterp = new byte[64]
            {
                20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107,
                20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107,
                20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107,
                20, 20, 20, 20, 20, 20, 20, 20, 107, 107, 107, 107, 107, 107, 107, 107
            };

            // ボーンキーフレーム書き込み
            foreach (var (boneName, track) in vmd.BoneTracks)
            {
                byte[] nameBytes = new byte[15];
                byte[] rawName = sjis.GetBytes(boneName);
                Array.Copy(rawName, nameBytes, Math.Min(rawName.Length, 15));

                foreach (var k in track)
                {
                    writer.Write(nameBytes);
                    writer.Write((uint)k.Frame);
                    writer.Write(k.Tx);
                    writer.Write(k.Ty);
                    writer.Write(k.Tz);
                    writer.Write(k.Qx);
                    writer.Write(k.Qy);
                    writer.Write(k.Qz);
                    writer.Write(k.Qw);
                    writer.Write(k.Interpolation != null && k.Interpolation.Length == 64 ? k.Interpolation : defaultInterp);
                }
            }

            // モーフキーフレーム数
            int totalMorphKeys = 0;
            foreach (var track in vmd.MorphTracks.Values)
            {
                totalMorphKeys += track.Count;
            }
            writer.Write(totalMorphKeys);

            // モーフキーフレーム書き込み
            foreach (var (morphName, track) in vmd.MorphTracks)
            {
                byte[] nameBytes = new byte[15];
                byte[] rawName = sjis.GetBytes(morphName);
                Array.Copy(rawName, nameBytes, Math.Min(rawName.Length, 15));

                foreach (var k in track)
                {
                    writer.Write(nameBytes);
                    writer.Write((uint)k.Frame);
                    writer.Write(k.Weight);
                }
            }

            // カメラキーフレーム数 (0)
            writer.Write(0);

            // 照明キーフレーム数 (0)
            writer.Write(0);

            // セルフシャドウキーフレーム数 (0)
            writer.Write(0);

            // IKキーフレーム数
            var ikFrames = new SortedDictionary<int, List<(string Name, bool Enabled)>>();
            foreach (var (ikName, track) in vmd.IkTracks)
            {
                foreach (var (f, en) in track)
                {
                    if (!ikFrames.TryGetValue(f, out var list))
                    {
                        list = new List<(string Name, bool Enabled)>();
                        ikFrames[f] = list;
                    }
                    list.Add((ikName, en));
                }
            }

            writer.Write(ikFrames.Count);
            foreach (var (frame, ikList) in ikFrames)
            {
                writer.Write((uint)frame);
                writer.Write((byte)1); // 表示フラグ
                writer.Write(ikList.Count);
                foreach (var (ikName, en) in ikList)
                {
                    byte[] ikNameBytes = new byte[20];
                    byte[] rawIk = sjis.GetBytes(ikName);
                    Array.Copy(rawIk, ikNameBytes, Math.Min(rawIk.Length, 20));
                    writer.Write(ikNameBytes);
                    writer.Write((byte)(en ? 1 : 0));
                }
            }
        }
    }
}
