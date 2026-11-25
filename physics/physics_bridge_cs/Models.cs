using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace MmdPhysicsBridge
{
    // Mayaから出力されたモーションデータ全体
    public class MayaMotionData
    {
        [JsonPropertyName("fps")]
        public double Fps { get; set; } = 30.0;

        [JsonPropertyName("start_frame")]
        public int StartFrame { get; set; }

        [JsonPropertyName("end_frame")]
        public int EndFrame { get; set; }

        [JsonPropertyName("coordinate_system")]
        public string CoordinateSystem { get; set; } = "Maya_RightHand_YUp";

        [JsonPropertyName("pmx_model")]
        public string PmxModel { get; set; } = "";

        [JsonPropertyName("bones")]
        public Dictionary<string, BoneMotionEntry> Bones { get; set; } = new();
    }

    // ボーンごとの各フレームデータ
    public class BoneMotionEntry
    {
        [JsonPropertyName("maya_node")]
        public string MayaNode { get; set; } = "";

        [JsonPropertyName("world_translations")]
        public List<List<double>> WorldTranslations { get; set; } = new();

        [JsonPropertyName("world_rotations")]
        public List<List<double>> WorldRotations { get; set; } = new();

        [JsonPropertyName("local_translations")]
        public List<List<double>> LocalTranslations { get; set; } = new();

        [JsonPropertyName("local_rotations")]
        public List<List<double>> LocalRotations { get; set; } = new();
    }

    // Mayaへ戻すベイク結果データ全体
    public class PhysicsBakeResult
    {
        [JsonPropertyName("start_frame")]
        public int StartFrame { get; set; }

        [JsonPropertyName("end_frame")]
        public int EndFrame { get; set; }

        [JsonPropertyName("bones")]
        public Dictionary<string, BoneBakeEntry> Bones { get; set; } = new();
    }

    // ベイク対象ボーンの姿勢データ
    public class BoneBakeEntry
    {
        [JsonPropertyName("maya_node")]
        public string MayaNode { get; set; } = "";

        [JsonPropertyName("local_rotations")]
        public List<List<double>> LocalRotations { get; set; } = new();

        [JsonPropertyName("local_translations")]
        public List<List<double>> LocalTranslations { get; set; } = new();
    }
}
