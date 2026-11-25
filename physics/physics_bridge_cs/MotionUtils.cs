using System;
using System.IO;
using System.Collections.Generic;
using System.Text.Json;

namespace MmdPhysicsBridge
{
    // モーション処理ユーティリティ
    public static class MotionUtils
    {
        // JSON読み込みとベイク出力処理
        public static void GenerateBakeJson(string inputPath, string outputPath)
        {
            if (!File.Exists(inputPath)) return;

            string jsonText = File.ReadAllText(inputPath);
            var motionData = JsonSerializer.Deserialize<MayaMotionData>(jsonText);
            if (motionData == null || motionData.Bones.Count == 0) return;

            var bakeResult = new PhysicsBakeResult
            {
                StartFrame = motionData.StartFrame,
                EndFrame = motionData.EndFrame
            };

            int totalFrames = motionData.EndFrame - motionData.StartFrame + 1;

            foreach (var kvp in motionData.Bones)
            {
                string boneName = kvp.Key;
                var sourceBone = kvp.Value;

                var bakeEntry = new BoneBakeEntry
                {
                    MayaNode = sourceBone.MayaNode
                };

                for (int i = 0; i < totalFrames; i++)
                {
                    double rx = (sourceBone.LocalRotations.Count > i) ? sourceBone.LocalRotations[i][0] : 0.0;
                    double ry = (sourceBone.LocalRotations.Count > i) ? sourceBone.LocalRotations[i][1] : 0.0;
                    double rz = (sourceBone.LocalRotations.Count > i) ? sourceBone.LocalRotations[i][2] : 0.0;

                    bakeEntry.LocalRotations.Add(new List<double> { rx, ry, rz });

                    if (sourceBone.LocalTranslations.Count > i)
                    {
                        bakeEntry.LocalTranslations.Add(new List<double>
                        {
                            sourceBone.LocalTranslations[i][0],
                            sourceBone.LocalTranslations[i][1],
                            sourceBone.LocalTranslations[i][2]
                        });
                    }
                }

                bakeResult.Bones[boneName] = bakeEntry;
            }

            var options = new JsonSerializerOptions
            {
                WriteIndented = true,
                Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            };

            string outputJsonText = JsonSerializer.Serialize(bakeResult, options);
            File.WriteAllText(outputPath, outputJsonText);
        }
    }
}
