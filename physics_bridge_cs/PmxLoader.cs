using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

namespace MmdPhysicsBridge
{
    // PMX剛体形状
    public enum PmxColliderShape
    {
        Sphere = 0,     // 球
        Box = 1,        // ボックス
        Capsule = 2     // カプセル
    }

    // PMX剛体物理モード
    public enum PmxPhysicsMode
    {
        FollowBone = 0,         // ボーン追従 (Kinematic)
        Physics = 1,            // 物理演算 (Dynamic)
        PhysicsWithBone = 2     // 物理演算 + 位置合わせ
    }

    // PMXマテリアルデータ
    public class PmxMaterial
    {
        public string Name { get; set; } = "";
        public string NameEnglish { get; set; } = "";
        public float[] Diffuse { get; set; } = new float[4] { 0.8f, 0.8f, 0.8f, 1.0f }; // RGBA
        public float[] Specular { get; set; } = new float[3] { 0.0f, 0.0f, 0.0f };       // RGB
        public float Specularity { get; set; } = 0.0f;
        public float[] Ambient { get; set; } = new float[3] { 0.5f, 0.5f, 0.5f };        // RGB
        public byte Flags { get; set; } // 0x01:両面描画, 0x02:地面影, 0x04:セルフ影マップ, 0x08:セルフ影, 0x10:輪郭線
        public float[] EdgeColor { get; set; } = new float[4] { 0, 0, 0, 1 };
        public float EdgeSize { get; set; } = 1.0f;

        // 各テクスチャ参照 (単一フィールドにまとめず明確に分離)
        public int TextureIndex { get; set; } = -1;           // 通常テクスチャインデックス
        public int SphereTextureIndex { get; set; } = -1;     // 環境マップ (スフィアマップ) インデックス
        public byte SphereMode { get; set; } = 0;             // スフィアモード (0:無効, 1:乗算, 2:加算, 3:サブテクスチャ)
        public byte SharedToonFlag { get; set; } = 0;         // 共有トゥーンフラグ (0:個別, 1:共有)
        public int ToonTextureIndex { get; set; } = -1;       // トゥーン参照 (個別時はテクスチャ一覧参照、共有時は0〜9)

        public string Memo { get; set; } = "";
        public int SurfaceCount { get; set; }
    }

    // PMX頂点モーフオフセットデータ
    public class PmxVertexMorphOffset
    {
        public int VertexIndex { get; set; }
        public float[] Offset { get; set; } = new float[3];
    }

    // PMXグループモーフオフセットデータ
    public class PmxGroupMorphOffset
    {
        public int MorphIndex { get; set; }
        public float Rate { get; set; }
    }

    // PMXモーフデータ
    public class PmxMorph
    {
        public string Name { get; set; } = "";
        public string NameEnglish { get; set; } = "";
        public byte Panel { get; set; }
        public byte MorphType { get; set; }
        public List<PmxVertexMorphOffset> VertexOffsets { get; set; } = new();
        public List<PmxGroupMorphOffset> GroupOffsets { get; set; } = new();
    }

    // PMXボーンIKリンクデータ
    public class PmxIkLink
    {
        public int BoneIndex { get; set; }
        public bool HasLimit { get; set; }
        public float[] MinAngle { get; set; } = new float[3];
        public float[] MaxAngle { get; set; } = new float[3];
    }

    // PMXボーンIKデータ
    public class PmxIkData
    {
        public int TargetBoneIndex { get; set; }
        public int LoopCount { get; set; }
        public float LimitAngle { get; set; }
        public List<PmxIkLink> Links { get; set; } = new();
    }

    // PMXボーンデータ
    public class PmxBone
    {
        public string Name { get; set; } = "";
        public string NameEnglish { get; set; } = "";
        public float[] Position { get; set; } = new float[3];
        public int ParentIndex { get; set; } = -1;
        public int Layer { get; set; }
        public ushort Flags { get; set; }
        public int InheritBoneIndex { get; set; } = -1;
        public float InheritRate { get; set; } = 0.0f;
        public PmxIkData? IkData { get; set; }
    }

    // PMX剛体データ
    public class PmxRigidbody
    {
        public string Name { get; set; } = "";
        public string NameEnglish { get; set; } = "";
        public int BoneIndex { get; set; } = -1;
        public byte Group { get; set; }
        public ushort NonCollisionGroup { get; set; }
        public PmxColliderShape Shape { get; set; }
        public float[] Size { get; set; } = new float[3]; // 球: R, 箱: W,H,D, カプセル: R, H
        public float[] Position { get; set; } = new float[3];
        public float[] Rotation { get; set; } = new float[3]; // ラジアン
        public float Mass { get; set; }
        public float PositionDamping { get; set; }
        public float RotationDamping { get; set; }
        public float Restitution { get; set; }
        public float Friction { get; set; }
        public PmxPhysicsMode PhysicsMode { get; set; }
    }

    // PMX Joint (拘束) データ
    public class PmxJoint
    {
        public string Name { get; set; } = "";
        public string NameEnglish { get; set; } = "";
        public byte JointType { get; set; }
        public int RigidbodyAIndex { get; set; } = -1;
        public int RigidbodyBIndex { get; set; } = -1;
        public float[] Position { get; set; } = new float[3];
        public float[] Rotation { get; set; } = new float[3]; // ラジアン
        public float[] PositionLimitMin { get; set; } = new float[3];
        public float[] PositionLimitMax { get; set; } = new float[3];
        public float[] RotationLimitMin { get; set; } = new float[3];
        public float[] RotationLimitMax { get; set; } = new float[3];
        public float[] SpringPosition { get; set; } = new float[3];
        public float[] SpringRotation { get; set; } = new float[3];
    }

    // PMX頂点スキンウェイトデータ
    public class PmxVertexSkinning
    {
        public int[] BoneIndices { get; set; } = Array.Empty<int>();
        public float[] Weights { get; set; } = Array.Empty<float>();
    }

    // PMXモデルデータ
    public class PmxModelData
    {
        public string ModelName { get; set; } = "";
        public string Comment { get; set; } = "";
        public List<float[]> VertexPositions { get; set; } = new();
        public List<float[]> VertexUVs { get; set; } = new();
        public List<PmxVertexSkinning> VertexSkinnings { get; set; } = new();
        public List<int> Indices { get; set; } = new();
        public List<string> Textures { get; set; } = new();
        public List<PmxMaterial> Materials { get; set; } = new();
        public List<PmxBone> Bones { get; set; } = new();
        public List<PmxMorph> Morphs { get; set; } = new();
        public List<PmxRigidbody> Rigidbodies { get; set; } = new();
        public List<PmxJoint> Joints { get; set; } = new();
    }

    // PMXローダークラス
    public static class PmxLoader
    {
        public static PmxModelData Load(string filePath)
        {
            if (!File.Exists(filePath))
            {
                throw new FileNotFoundException($"PMXファイルが見つかりません: {filePath}");
            }

            using var stream = File.OpenRead(filePath);
            using var reader = new BinaryReader(stream);

            // ヘッダー確認 ("PMX ")
            byte[] magic = reader.ReadBytes(4);
            string magicStr = Encoding.ASCII.GetString(magic);
            if (magicStr != "PMX ")
            {
                throw new InvalidDataException("有効なPMXファイルではありません。");
            }

            float version = reader.ReadSingle();
            byte globalCount = reader.ReadByte();
            byte[] globals = reader.ReadBytes(globalCount);

            Encoding textEncoding = globals[0] == 0 ? Encoding.Unicode : Encoding.UTF8;
            byte additionalUvCount = globals[1];
            int vertexIndexSize = globals[2];
            int textureIndexSize = globals[3];
            int materialIndexSize = globals[4];
            int boneIndexSize = globals[5];
            int morphIndexSize = globals[6];
            int rigidbodyIndexSize = globals[7];

            var model = new PmxModelData();
            model.ModelName = ReadString(reader, textEncoding);
            ReadString(reader, textEncoding); // 英語モデル名スキップ
            model.Comment = ReadString(reader, textEncoding);
            ReadString(reader, textEncoding); // 英語コメントスキップ

            // 頂点読み込み
            try
            {
                int vertexCount = reader.ReadInt32();
                for (int i = 0; i < vertexCount; i++)
                {
                    float vx = reader.ReadSingle();
                    float vy = reader.ReadSingle();
                    float vz = reader.ReadSingle();
                    model.VertexPositions.Add(new float[] { vx, vy, vz });

                    // 法線(12バイト)をスキップ
                    reader.BaseStream.Seek(12, SeekOrigin.Current);

                    // テクスチャUV(8バイト: float u, float v)
                    float u = reader.ReadSingle();
                    float v = reader.ReadSingle();
                    model.VertexUVs.Add(new float[] { u, v });

                    // 追加UV
                    if (additionalUvCount > 0)
                    {
                        reader.BaseStream.Seek(additionalUvCount * 16, SeekOrigin.Current);
                    }

                    byte weightType = reader.ReadByte();
                    var skinning = new PmxVertexSkinning();
                    switch (weightType)
                    {
                        case 0: // BDEF1
                            skinning.BoneIndices = new int[] { ReadIndex(reader, boneIndexSize) };
                            skinning.Weights = new float[] { 1.0f };
                            break;
                        case 1: // BDEF2
                            int b1 = ReadIndex(reader, boneIndexSize);
                            int b2 = ReadIndex(reader, boneIndexSize);
                            float w1 = reader.ReadSingle();
                            skinning.BoneIndices = new int[] { b1, b2 };
                            skinning.Weights = new float[] { w1, 1.0f - w1 };
                            break;
                        case 2: // BDEF4
                            int b1_4 = ReadIndex(reader, boneIndexSize);
                            int b2_4 = ReadIndex(reader, boneIndexSize);
                            int b3_4 = ReadIndex(reader, boneIndexSize);
                            int b4_4 = ReadIndex(reader, boneIndexSize);
                            float w1_4 = reader.ReadSingle();
                            float w2_4 = reader.ReadSingle();
                            float w3_4 = reader.ReadSingle();
                            float w4_4 = reader.ReadSingle();
                            skinning.BoneIndices = new int[] { b1_4, b2_4, b3_4, b4_4 };
                            skinning.Weights = new float[] { w1_4, w2_4, w3_4, w4_4 };
                            break;
                        case 3: // SDEF
                            int sb1 = ReadIndex(reader, boneIndexSize);
                            int sb2 = ReadIndex(reader, boneIndexSize);
                            float sw1 = reader.ReadSingle();
                            reader.BaseStream.Seek(36, SeekOrigin.Current); // SDEFパラメータスキップ
                            skinning.BoneIndices = new int[] { sb1, sb2 };
                            skinning.Weights = new float[] { sw1, 1.0f - sw1 };
                            break;
                        default:
                            skinning.BoneIndices = new int[] { ReadIndex(reader, boneIndexSize) };
                            skinning.Weights = new float[] { 1.0f };
                            if (weightType == 4) reader.BaseStream.Seek((boneIndexSize * 3) + 16, SeekOrigin.Current);
                            break;
                    }
                    model.VertexSkinnings.Add(skinning);
                    reader.BaseStream.Seek(4, SeekOrigin.Current); // エッジ倍率
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"頂点データの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // 面（インデックス）読み込み
            try
            {
                int surfaceCount = reader.ReadInt32();
                for (int i = 0; i < surfaceCount; i++)
                {
                    model.Indices.Add(ReadVertexIndex(reader, vertexIndexSize));
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"面データの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // テクスチャテーブル読み込み
            try
            {
                int textureCount = reader.ReadInt32();
                for (int i = 0; i < textureCount; i++)
                {
                    string texPath = ReadString(reader, textEncoding);
                    model.Textures.Add(texPath);
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"テクスチャデータの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // マテリアル読み込み
            try
            {
                int materialCount = reader.ReadInt32();
                for (int i = 0; i < materialCount; i++)
                {
                    var mat = new PmxMaterial();
                    mat.Name = ReadString(reader, textEncoding); // 和名
                    mat.NameEnglish = ReadString(reader, textEncoding); // 英名

                    mat.Diffuse = new float[]
                    {
                        reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()
                    };

                    mat.Specular = new float[]
                    {
                        reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()
                    };
                    mat.Specularity = reader.ReadSingle();

                    mat.Ambient = new float[]
                    {
                        reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()
                    };

                    mat.Flags = reader.ReadByte();

                    mat.EdgeColor = new float[]
                    {
                        reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle()
                    };
                    mat.EdgeSize = reader.ReadSingle();

                    // 通常テクスチャインデックス
                    mat.TextureIndex = ReadIndex(reader, textureIndexSize);

                    // スフィアテクスチャインデックスおよびモード
                    mat.SphereTextureIndex = ReadIndex(reader, textureIndexSize);
                    mat.SphereMode = reader.ReadByte();

                    // トゥーンテクスチャ
                    mat.SharedToonFlag = reader.ReadByte();
                    if (mat.SharedToonFlag == 0)
                    {
                        mat.ToonTextureIndex = ReadIndex(reader, textureIndexSize);
                    }
                    else
                    {
                        mat.ToonTextureIndex = reader.ReadByte();
                    }

                    mat.Memo = ReadString(reader, textEncoding);
                    mat.SurfaceCount = reader.ReadInt32(); // 面数 (該当マテリアルの頂点インデックス数)
                    model.Materials.Add(mat);
                }

                // 材質の面数（頂点インデックス数）の合計と全体の面インデックス総数の整合性を検証
                int totalMatSurfaces = 0;
                foreach (var m in model.Materials)
                {
                    totalMatSurfaces += m.SurfaceCount;
                }
                if (totalMatSurfaces != model.Indices.Count)
                {
                    System.Diagnostics.Debug.WriteLine($"[警告] 材質の面数合計 ({totalMatSurfaces}) が全体の面インデックス数 ({model.Indices.Count}) と一致しません。");
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"マテリアルデータの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // ボーン読み込み
            try
            {
                int boneCount = reader.ReadInt32();
                for (int i = 0; i < boneCount; i++)
                {
                    var bone = new PmxBone();
                    bone.Name = ReadString(reader, textEncoding);
                    bone.NameEnglish = ReadString(reader, textEncoding);
                    bone.Position = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                    bone.ParentIndex = ReadIndex(reader, boneIndexSize);
                    bone.Layer = reader.ReadInt32();
                    bone.Flags = reader.ReadUInt16();

                    // 接続先
                    if ((bone.Flags & 0x0001) != 0)
                    {
                        ReadIndex(reader, boneIndexSize);
                    }
                    else
                    {
                        reader.BaseStream.Seek(12, SeekOrigin.Current); // オフセット座標
                    }

                    // 付与親 (回転または移動)
                    if ((bone.Flags & 0x0100) != 0 || (bone.Flags & 0x0200) != 0)
                    {
                        bone.InheritBoneIndex = ReadIndex(reader, boneIndexSize);
                        bone.InheritRate = reader.ReadSingle();
                    }

                    // 軸固定
                    if ((bone.Flags & 0x0400) != 0)
                    {
                        reader.BaseStream.Seek(12, SeekOrigin.Current);
                    }

                    // ローカル軸
                    if ((bone.Flags & 0x0800) != 0)
                    {
                        reader.BaseStream.Seek(24, SeekOrigin.Current);
                    }

                    // 外部親変形
                    if ((bone.Flags & 0x2000) != 0)
                    {
                        reader.BaseStream.Seek(4, SeekOrigin.Current);
                    }

                    // IK
                    if ((bone.Flags & 0x0020) != 0)
                    {
                        var ik = new PmxIkData
                        {
                            TargetBoneIndex = ReadIndex(reader, boneIndexSize),
                            LoopCount = reader.ReadInt32(),
                            LimitAngle = reader.ReadSingle()
                        };
                        int linkCount = reader.ReadInt32();
                        for (int l = 0; l < linkCount; l++)
                        {
                            var link = new PmxIkLink
                            {
                                BoneIndex = ReadIndex(reader, boneIndexSize),
                                HasLimit = reader.ReadByte() != 0
                            };
                            if (link.HasLimit)
                            {
                                link.MinAngle = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                                link.MaxAngle = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                            }
                            ik.Links.Add(link);
                        }
                        bone.IkData = ik;
                    }

                    model.Bones.Add(bone);
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"ボーンデータの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // モーフ読み込み
            try
            {
                int morphCount = reader.ReadInt32();
                for (int i = 0; i < morphCount; i++)
                {
                    var morph = new PmxMorph();
                    morph.Name = ReadString(reader, textEncoding);
                    morph.NameEnglish = ReadString(reader, textEncoding);
                    morph.Panel = reader.ReadByte();
                    morph.MorphType = reader.ReadByte();
                    int offsetCount = reader.ReadInt32();

                    for (int o = 0; o < offsetCount; o++)
                    {
                        switch (morph.MorphType)
                        {
                            case 0: // グループ
                                morph.GroupOffsets.Add(new PmxGroupMorphOffset
                                {
                                    MorphIndex = ReadIndex(reader, morphIndexSize),
                                    Rate = reader.ReadSingle()
                                });
                                break;
                            case 1: // 頂点
                                morph.VertexOffsets.Add(new PmxVertexMorphOffset
                                {
                                    VertexIndex = ReadVertexIndex(reader, vertexIndexSize),
                                    Offset = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() }
                                });
                                break;
                            case 2: // ボーン
                                reader.BaseStream.Seek(boneIndexSize + 28, SeekOrigin.Current);
                                break;
                            case 3: // UV
                            case 4: // 追加UV1
                            case 5: // 追加UV2
                            case 6: // 追加UV3
                            case 7: // 追加UV4
                                reader.BaseStream.Seek(vertexIndexSize + 16, SeekOrigin.Current);
                                break;
                            case 8: // マテリアル
                                // 演算(1) + Diffuse(16) + Specular(12) + Specular係数(4) + Ambient(12) + EdgeColor(16) + EdgeSize(4) + Tex(16) + Sphere(16) + Toon(16) = 113バイト
                                reader.BaseStream.Seek(materialIndexSize + 113, SeekOrigin.Current);
                                break;
                            case 9: // フリップ
                                reader.BaseStream.Seek(morphIndexSize + 4, SeekOrigin.Current);
                                break;
                            case 10: // インパルス
                                reader.BaseStream.Seek(rigidbodyIndexSize + 1 + 12 + 12, SeekOrigin.Current);
                                break;
                            default:
                                break;
                        }
                    }

                    model.Morphs.Add(morph);
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"モーフデータの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // 表示枠スキップ
            try
            {
                int frameCount = reader.ReadInt32();
                for (int i = 0; i < frameCount; i++)
                {
                    ReadString(reader, textEncoding);
                    ReadString(reader, textEncoding);
                    reader.BaseStream.Seek(1, SeekOrigin.Current); // 特殊枠フラグ
                    int elementCount = reader.ReadInt32();
                    for (int e = 0; e < elementCount; e++)
                    {
                        byte targetType = reader.ReadByte();
                        if (targetType == 0) ReadIndex(reader, boneIndexSize);
                        else ReadIndex(reader, morphIndexSize);
                    }
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"表示枠データの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // 剛体読み込み
            try
            {
                if (reader.BaseStream.Position < reader.BaseStream.Length)
                {
                    int rbCount = reader.ReadInt32();
                    for (int i = 0; i < rbCount; i++)
                    {
                        var rb = new PmxRigidbody();
                        rb.Name = ReadString(reader, textEncoding);
                        rb.NameEnglish = ReadString(reader, textEncoding);
                        rb.BoneIndex = ReadIndex(reader, boneIndexSize);
                        rb.Group = reader.ReadByte();
                        rb.NonCollisionGroup = reader.ReadUInt16();
                        rb.Shape = (PmxColliderShape)reader.ReadByte();
                        rb.Size = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        rb.Position = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        rb.Rotation = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        rb.Mass = reader.ReadSingle();
                        rb.PositionDamping = reader.ReadSingle();
                        rb.RotationDamping = reader.ReadSingle();
                        rb.Restitution = reader.ReadSingle();
                        rb.Friction = reader.ReadSingle();
                        rb.PhysicsMode = (PmxPhysicsMode)reader.ReadByte();

                        model.Rigidbodies.Add(rb);
                    }
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"剛体データの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            // Joint (拘束) 読み込み
            try
            {
                if (reader.BaseStream.Position < reader.BaseStream.Length)
                {
                    int jointCount = reader.ReadInt32();
                    for (int i = 0; i < jointCount; i++)
                    {
                        var joint = new PmxJoint();
                        joint.Name = ReadString(reader, textEncoding);
                        joint.NameEnglish = ReadString(reader, textEncoding);
                        joint.JointType = reader.ReadByte();
                        joint.RigidbodyAIndex = ReadIndex(reader, rigidbodyIndexSize);
                        joint.RigidbodyBIndex = ReadIndex(reader, rigidbodyIndexSize);
                        joint.Position = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.Rotation = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.PositionLimitMin = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.PositionLimitMax = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.RotationLimitMin = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.RotationLimitMax = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.SpringPosition = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };
                        joint.SpringRotation = new float[] { reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle() };

                        model.Joints.Add(joint);
                    }
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"Jointデータの解析中にエラーが発生しました: {ex.Message}", ex);
            }

            return model;
        }

        private static string ReadString(BinaryReader reader, Encoding encoding)
        {
            int length = reader.ReadInt32();
            if (length <= 0) return "";
            byte[] bytes = reader.ReadBytes(length);
            return encoding.GetString(bytes);
        }

        private static int ReadIndex(BinaryReader reader, int size)
        {
            switch (size)
            {
                case 1:
                    byte b = reader.ReadByte();
                    return b == 255 ? -1 : (int)b;
                case 2:
                    ushort u = reader.ReadUInt16();
                    return u == 65535 ? -1 : (int)u;
                case 4:
                    return reader.ReadInt32();
                default:
                    return -1;
            }
        }

        private static int ReadVertexIndex(BinaryReader reader, int size)
        {
            return size switch
            {
                1 => reader.ReadByte(),
                2 => reader.ReadUInt16(),
                4 => reader.ReadInt32(),
                _ => 0
            };
        }
    }
}
