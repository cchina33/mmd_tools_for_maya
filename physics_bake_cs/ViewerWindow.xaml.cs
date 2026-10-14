using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Media3D;
using System.Windows.Threading;
using BulletSharp.Math;
using Matrix = BulletSharp.Math.Matrix;
using MmdPhysicsBridge;

namespace MmdPhysicsViewer
{
    public partial class ViewerWindow : Window
    {
        private readonly string _pmxPath;
        private readonly string _vmdPath;
        private readonly string _outVmdPath;
        private readonly int _lookahead;

        private PmxModelData? _pmx;
        private VmdMotionData? _vmd;
        private readonly PhysicsSimulationEngine _physics = new();
        private PoseEvaluator? _evaluator;

        // カメラ制御
        private System.Windows.Point _lastMousePos;
        private double _cameraDistance = 45.0;
        private double _cameraTheta = 180.0;
        private double _cameraPhi = 10.0;
        private Point3D _cameraTarget = new Point3D(0, 10, 0);
        private int _trackingBoneIndex = -1;
        private Vector3? _lastTrackedBonePos = null;

        // 3D描画用
        private readonly List<GeometryModel3D> _rigidbodyVisuals = new();
        private readonly List<TranslateTransform3D> _boneJointTransforms = new();
        private Model3DGroup? _boneLineGroup;
        private ModelVisual3D? _meshVisual;
        private readonly TranslateTransform3D _meshTransform = new();

        private class SubMeshData
        {
            public MeshGeometry3D Mesh { get; set; } = null!;
            public List<int> GlobalVertexIndices { get; set; } = new();
        }
        private readonly List<SubMeshData> _subMeshes = new();

        // 通信同期フラグ
        private int _lastAckedFrame = -1;
        private volatile bool _isCancelled = false;
        private readonly CancellationTokenSource _cts = new();
        private readonly double _warmupSeconds;
        private readonly int? _startFrame;
        private readonly int? _endFrame;

        public ViewerWindow(string pmxPath, string vmdPath, string? outVmdPath, int lookahead, double warmupSeconds = 2.0, int? startFrame = null, int? endFrame = null)
        {
            InitializeComponent();
            Topmost = true;
            _pmxPath = pmxPath;
            _vmdPath = vmdPath;
            _lookahead = Math.Max(1, lookahead);
            _warmupSeconds = Math.Max(0.0, warmupSeconds);
            _startFrame = startFrame;
            _endFrame = endFrame;

            if (string.Equals(outVmdPath, "none", StringComparison.OrdinalIgnoreCase))
            {
                _outVmdPath = "none";
            }
            else
            {
                string vmdDir = Path.GetDirectoryName(vmdPath) ?? Directory.GetCurrentDirectory();
                string vmdBase = Path.GetFileNameWithoutExtension(vmdPath);
                _outVmdPath = string.IsNullOrWhiteSpace(outVmdPath)
                    ? Path.Combine(vmdDir, $"{vmdBase}_physics_baked.vmd")
                    : outVmdPath;
            }

            _update_camera();
            GridContainer.Children.Add(GeometryHelper.CreateGrid(40.0, 2.0));

            Loaded += OnLoaded;
            Closing += OnClosing;
        }

        private void OnClosing(object? sender, System.ComponentModel.CancelEventArgs e)
        {
            _isCancelled = true;
            _cts.Cancel();
        }

        protected override void OnClosed(EventArgs e)
        {
            base.OnClosed(e);
            _isCancelled = true;
            _cts.Cancel();
            try
            {
                Application.Current.Shutdown(0);
            }
            catch
            {
                // すでに終了中の場合は無視
            }
        }

        private void BtnStopBake_Click(object sender, RoutedEventArgs e)
        {
            _isCancelled = true;
            _cts.Cancel();
            TxtProgress.Text = "ベイクを終了中...";
            Close();
        }

        private async void OnLoaded(object sender, RoutedEventArgs e)
        {
            try
            {
                // PMX と VMD の読み込み
                _pmx = PmxLoader.Load(_pmxPath);
                if (!string.IsNullOrWhiteSpace(_vmdPath) && File.Exists(_vmdPath))
                {
                    _vmd = VmdLoader.Load(_vmdPath);
                }
                else
                {
                    _vmd = new VmdMotionData { ModelName = _pmx.ModelName, MaxFrame = 0 };
                }

                _physics.InitializeWorld();
                _physics.BuildPhysicsFromPmx(_pmx);
                _evaluator = new PoseEvaluator(_pmx, _vmd, _physics);

                _setup_scene_visuals();
                _init_camera_tracking();

                // stdin リスナーを開始
                _ = Task.Run(ListenStdinAsync);

                int actualStart = _startFrame ?? 0;
                int actualEnd = _endFrame ?? _vmd.MaxFrame;
                actualStart = Math.Clamp(actualStart, 0, _vmd.MaxFrame);
                actualEnd = Math.Clamp(actualEnd, actualStart, _vmd.MaxFrame);
                int totalBakeFrames = actualEnd - actualStart + 1;

                // 初期メッセージ（hello）を stdout へ出力
                var targetBones = _evaluator.PhysicsBoneIndices.Select(i => _pmx.Bones[i].Name).ToList();
                var helloMsg = new
                {
                    type = "hello",
                    model_name = _pmx.ModelName,
                    start_frame = actualStart,
                    end_frame = actualEnd,
                    max_frame = _vmd.MaxFrame,
                    total_frames = totalBakeFrames,
                    physics_bones = targetBones,
                    out_vmd = _outVmdPath
                };
                Console.WriteLine(JsonSerializer.Serialize(helloMsg));
                Console.Out.Flush();

                // 物理シミュレーションとストリーミング実行
                await RunStreamingBakeAsync();
            }
            catch (Exception ex)
            {
                var errMsg = new { type = "error", message = ex.Message, stack = ex.StackTrace };
                Console.WriteLine(JsonSerializer.Serialize(errMsg));
                Console.Out.Flush();
                MessageBox.Show($"ビューア実行エラー:\n{ex.Message}", "エラー", MessageBoxButton.OK, MessageBoxImage.Error);
                Close();
            }
        }

        private async Task ListenStdinAsync()
        {
            try
            {
                string? line;
                while (!_isCancelled && (line = await Console.In.ReadLineAsync()) != null)
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    try
                    {
                        using var doc = JsonDocument.Parse(line);
                        var root = doc.RootElement;
                        if (root.TryGetProperty("type", out var typeProp))
                        {
                            string t = typeProp.GetString() ?? "";
                            if (t == "ack" && root.TryGetProperty("frame", out var fProp))
                            {
                                int ackFrame = fProp.GetInt32();
                                Interlocked.Exchange(ref _lastAckedFrame, ackFrame);
                            }
                            else if (t == "cancel")
                            {
                                _isCancelled = true;
                                _cts.Cancel();
                                break;
                            }
                        }
                    }
                    catch
                    {
                        // 不正なJSONはスキップ
                    }
                }
            }
            catch
            {
                // パイプ切断時は終了
                _isCancelled = true;
            }
        }

        private async Task RunStreamingBakeAsync()
        {
            if (_pmx == null || _vmd == null || _evaluator == null) return;

            int actualStart = Math.Clamp(_startFrame ?? 0, 0, _vmd.MaxFrame);
            int actualEnd = Math.Clamp(_endFrame ?? _vmd.MaxFrame, actualStart, _vmd.MaxFrame);
            int totalFramesToProcess = actualEnd - actualStart + 1;
            var bones = _pmx.Bones;
            var sw = System.Diagnostics.Stopwatch.StartNew();

            // VMD出力用のデータコンテナ
            var bakedVmd = new VmdMotionData
            {
                ModelName = !string.IsNullOrEmpty(_pmx.ModelName) ? _pmx.ModelName : _vmd.ModelName,
                MaxFrame = _vmd.MaxFrame
            };

            var physicsBoneNames = new HashSet<string>(_evaluator.PhysicsBoneIndices.Select(idx => bones[idx].Name));
            foreach (var (bName, track) in _vmd.BoneTracks)
            {
                if (!physicsBoneNames.Contains(bName))
                {
                    bakedVmd.BoneTracks[bName] = new List<VmdBoneKeyframe>(track);
                }
            }
            foreach (var (mName, track) in _vmd.MorphTracks)
            {
                bakedVmd.MorphTracks[mName] = new List<VmdMorphKeyframe>(track);
            }
            foreach (var (ikName, track) in _vmd.IkTracks)
            {
                bakedVmd.IkTracks[ikName] = new List<(int, bool)>(track);
            }
            foreach (int idx in _evaluator.PhysicsBoneIndices)
            {
                bakedVmd.BoneTracks[bones[idx].Name] = new List<VmdBoneKeyframe>();
            }

            // 初期フレームの姿勢へ剛体をスナップ
            _evaluator.EvaluateFkAndSyncBodies(actualStart, resetAllBodies: true);

            // ベイク開始前の初期姿勢安定化 (ウォームアップ: 指定開始フレーム姿勢で数秒間物理演算を先行実行し、スカートや髪の垂れ下がりを落ち着かせる)
            if (_warmupSeconds > 0.05)
            {
                TxtProgress.Text = "初期姿勢・物理安定化中...";
                ProgressBar.Value = 0;
                int warmupSteps = (int)Math.Round(_warmupSeconds * 30.0);
                for (int w = 0; w < warmupSteps; w++)
                {
                    if (_isCancelled) break;
                    _evaluator.EvaluateFkAndSyncBodies(actualStart, resetAllBodies: false);
                    _physics.StepSimulation(1.0f / 30.0f, 10, 1.0f / 60.0f);
                    _evaluator.ApplyPhysicsToBones();
                    _update_viewport_display(actualStart);

                    double remainingSec = (_warmupSeconds * (warmupSteps - w - 1)) / (double)warmupSteps;
                    TxtEta.Text = $"開始前の姿勢安定化中: 残り {remainingSec:F1} 秒";
                    ProgressBar.Value = (double)(w + 1) / warmupSteps * 100.0;
                    await Task.Delay(16, _cts.Token);
                }

                // ウォームアップ終了時に残留慣性（速度・角速度・外力）をクリアし、静止姿勢から開始
                foreach (var body in _physics.RigidBodies)
                {
                    body.LinearVelocity = Vector3.Zero;
                    body.AngularVelocity = Vector3.Zero;
                    body.ClearForces();
                }
            }

            // 姿勢が安定した状態でベイク計測用ストップウォッチをリセット
            sw.Restart();

            for (int f = actualStart; f <= actualEnd; f++)
            {
                if (_isCancelled) break;

                // ACK による先行フレーム数制御 (通信遅延時も自律復帰する保護付き)
                int waitTimeoutMs = 0;
                while (f > _lastAckedFrame + _lookahead && !_isCancelled)
                {
                    await Task.Delay(3, _cts.Token);
                    waitTimeoutMs += 3;
                    if (waitTimeoutMs >= 3000)
                    {
                        break;
                    }
                }
                if (_isCancelled) break;

                // FK計算と剛体追従
                _evaluator.EvaluateFkAndSyncBodies(f, resetAllBodies: false);

                // 物理シミュレーション (1/30秒をサブステップで進行)
                _physics.StepSimulation(1.0f / 30.0f, 10, 1.0f / 60.0f);

                // 物理結果をボーンへ反映
                _evaluator.ApplyPhysicsToBones();

                // 揺れものボーンの回転クォータニオンを抽出
                var rotDict = _evaluator.ExtractPhysicsBoneRotations();

                // VMDキーフレームを蓄積
                foreach (int bIdx in _evaluator.PhysicsBoneIndices)
                {
                    var bone = bones[bIdx];
                    if (rotDict.TryGetValue(bone.Name, out var q))
                    {
                        bakedVmd.BoneTracks[bone.Name].Add(new VmdBoneKeyframe
                        {
                            Frame = f,
                            Tx = 0,
                            Ty = 0,
                            Tz = 0,
                            Qx = q[0],
                            Qy = q[1],
                            Qz = q[2],
                            Qw = q[3]
                        });
                    }
                }

                // Mayaへ1行JSONで送信
                var framePayload = new
                {
                    type = "frame",
                    frame = f,
                    bones = rotDict
                };
                Console.WriteLine(JsonSerializer.Serialize(framePayload));
                Console.Out.Flush();

                // 3Dビューポートおよび進捗オーバーレイの更新
                _update_viewport_display(f);

                int processed = f - actualStart + 1;
                int remaining = totalFramesToProcess - processed;
                double msPerFrame = sw.Elapsed.TotalMilliseconds / processed;
                var estRemaining = TimeSpan.FromMilliseconds(msPerFrame * remaining);
                float percent = (float)processed / totalFramesToProcess * 100.0f;

                TxtProgress.Text = $"フレーム: {f} / {actualEnd} ({percent:F1}%)";
                TxtEta.Text = $"推定残り時間: {estRemaining:mm\\:ss} (経過: {sw.Elapsed:mm\\:ss})";
                ProgressBar.Value = percent;

                // 描画イベントを処理
                await Dispatcher.Yield(DispatcherPriority.Background);
            }

            if (!_isCancelled)
            {
                // VMDファイルを保存 (出力指定が none でない場合)
                if (!string.Equals(_outVmdPath, "none", StringComparison.OrdinalIgnoreCase))
                {
                    VmdLoader.SaveVmd(_outVmdPath, bakedVmd);
                }

                var doneMsg = new
                {
                    type = "done",
                    vmd_path = string.Equals(_outVmdPath, "none", StringComparison.OrdinalIgnoreCase) ? "" : _outVmdPath,
                    start_frame = actualStart,
                    end_frame = actualEnd,
                    total_frames = totalFramesToProcess,
                    elapsed_seconds = sw.Elapsed.TotalSeconds
                };
                Console.WriteLine(JsonSerializer.Serialize(doneMsg));
                Console.Out.Flush();

                TxtProgress.Text = $"ベイク終了！ {actualStart} ～ {actualEnd} ({totalFramesToProcess}フレーム)";
                TxtEta.Text = string.Equals(_outVmdPath, "none", StringComparison.OrdinalIgnoreCase)
                    ? "Mayaへのベイク終了 (VMD出力なし)"
                    : $"出力先: {Path.GetFileName(_outVmdPath)}";
                ProgressBar.Value = 100;

                await Task.Delay(1200);
                Close();
            }
        }

        private void _setup_scene_visuals()
        {
            if (_pmx == null) return;

            MeshContainer.Children.Clear();
            BoneContainer.Children.Clear();
            RigidbodyContainer.Children.Clear();
            JointContainer.Children.Clear();
            _rigidbodyVisuals.Clear();
            _boneJointTransforms.Clear();

            var mirrorTransform = new ScaleTransform3D(-1, 1, 1);
            MeshContainer.Transform = mirrorTransform;
            BoneContainer.Transform = mirrorTransform;
            RigidbodyContainer.Transform = mirrorTransform;
            JointContainer.Transform = mirrorTransform;

            // メッシュ
            _subMeshes.Clear();
            if (_pmx.VertexPositions.Count > 0 && _pmx.Indices.Count > 0)
            {
                var meshGroup = new Model3DGroup();
                int indexOffset = 0;

                foreach (var mat in _pmx.Materials)
                {
                    if (mat.SurfaceCount <= 0) continue;
                    int count = Math.Min(mat.SurfaceCount, _pmx.Indices.Count - indexOffset);
                    if (count <= 0) break;

                    var mesh = new MeshGeometry3D();
                    var localMap = new Dictionary<int, int>();
                    var subMesh = new SubMeshData { Mesh = mesh };

                    for (int i = 0; i < count; i += 3)
                    {
                        if (i + 2 >= count) break;
                        int g0 = _pmx.Indices[indexOffset + i];
                        int g1 = _pmx.Indices[indexOffset + i + 1];
                        int g2 = _pmx.Indices[indexOffset + i + 2];

                        int GetOrAddLocal(int globalIdx)
                        {
                            if (!localMap.TryGetValue(globalIdx, out int localIdx))
                            {
                                localIdx = mesh.Positions.Count;
                                localMap[globalIdx] = localIdx;
                                subMesh.GlobalVertexIndices.Add(globalIdx);
                                var v = _pmx.VertexPositions[globalIdx];
                                mesh.Positions.Add(new Point3D(v[0], v[1], v[2]));
                            }
                            return localIdx;
                        }

                        int l0 = GetOrAddLocal(g0);
                        int l1 = GetOrAddLocal(g1);
                        int l2 = GetOrAddLocal(g2);

                        mesh.TriangleIndices.Add(l0);
                        mesh.TriangleIndices.Add(l1);
                        mesh.TriangleIndices.Add(l2);
                    }
                    indexOffset += count;
                    _subMeshes.Add(subMesh);

                    var matColor = Color.FromArgb(
                        220,
                        (byte)Math.Clamp((int)(mat.Diffuse[0] * 255), 40, 255),
                        (byte)Math.Clamp((int)(mat.Diffuse[1] * 255), 40, 255),
                        (byte)Math.Clamp((int)(mat.Diffuse[2] * 255), 40, 255)
                    );
                    var material = new DiffuseMaterial(new SolidColorBrush(matColor));
                    var geom = new GeometryModel3D(mesh, material) { BackMaterial = material };
                    meshGroup.Children.Add(geom);
                }

                _meshTransform.OffsetX = 0;
                _meshTransform.OffsetY = 0;
                _meshTransform.OffsetZ = 0;
                _meshVisual = new ModelVisual3D { Content = meshGroup, Transform = _meshTransform };
                MeshContainer.Children.Add(_meshVisual);
            }

            // ボーン関節球とライン
            var boneGroup = new Model3DGroup();
            Color boneColor = Color.FromArgb(180, 100, 200, 255);
            Color jointColor = Color.FromArgb(220, 255, 200, 50);

            _boneLineGroup = new Model3DGroup();
            for (int i = 0; i < _pmx.Bones.Count; i++)
            {
                var sphere = GeometryHelper.CreateSphere(new Point3D(0, 0, 0), 0.18, jointColor, 6, 4);
                var tt = new TranslateTransform3D();
                _boneJointTransforms.Add(tt);
                if (sphere.Content is GeometryModel3D g)
                {
                    g.Transform = tt;
                    boneGroup.Children.Add(g);
                }
            }
            boneGroup.Children.Add(_boneLineGroup);
            BoneContainer.Children.Add(new ModelVisual3D { Content = boneGroup });

            // 剛体
            var rbGroup = new Model3DGroup();
            for (int i = 0; i < _pmx.Rigidbodies.Count; i++)
            {
                var rb = _pmx.Rigidbodies[i];
                Color rbColor = rb.PhysicsMode switch
                {
                    PmxPhysicsMode.FollowBone => Color.FromArgb(90, 46, 204, 113),
                    PmxPhysicsMode.Physics => Color.FromArgb(120, 231, 76, 60),
                    _ => Color.FromArgb(110, 241, 196, 15)
                };

                ModelVisual3D? shapeVisual = null;
                if (rb.Shape == PmxColliderShape.Sphere)
                {
                    shapeVisual = GeometryHelper.CreateSphere(new Point3D(0, 0, 0), rb.Size[0], rbColor, 8, 6);
                }
                else if (rb.Shape == PmxColliderShape.Box)
                {
                    shapeVisual = GeometryHelper.CreateBox(new Point3D(0, 0, 0), new Vector3D(rb.Size[0] * 2, rb.Size[1] * 2, rb.Size[2] * 2), rbColor);
                }
                else if (rb.Shape == PmxColliderShape.Capsule)
                {
                    shapeVisual = GeometryHelper.CreateCapsule(new Point3D(0, 0, 0), rb.Size[0], rb.Size[1], rbColor);
                }

                if (shapeVisual?.Content is GeometryModel3D geom)
                {
                    _rigidbodyVisuals.Add(geom);
                    rbGroup.Children.Add(geom);
                }
            }
            RigidbodyContainer.Children.Add(new ModelVisual3D { Content = rbGroup });
        }

        private void _update_viewport_display(float frame)
        {
            if (_pmx == null || _evaluator == null) return;

            var matrices = _evaluator.BoneWorldMatrices;

            // モデル移動にカメラを自動追従
            _update_camera_tracking(matrices);

            // ボーン球
            for (int i = 0; i < _pmx.Bones.Count && i < _boneJointTransforms.Count && i < matrices.Count; i++)
            {
                var wp = matrices[i].Origin;
                _boneJointTransforms[i].OffsetX = wp.X;
                _boneJointTransforms[i].OffsetY = wp.Y;
                _boneJointTransforms[i].OffsetZ = wp.Z;
            }

            // ボーン連結ライン
            if (_boneLineGroup != null)
            {
                _boneLineGroup.Children.Clear();
                Color boneColor = Color.FromArgb(180, 100, 200, 255);
                for (int i = 0; i < _pmx.Bones.Count && i < matrices.Count; i++)
                {
                    var bone = _pmx.Bones[i];
                    if (bone.ParentIndex >= 0 && bone.ParentIndex < matrices.Count)
                    {
                        var mCurrent = matrices[i];
                        var mParent = matrices[bone.ParentIndex];
                        Point3D pCurrent = new Point3D(mCurrent.Origin.X, mCurrent.Origin.Y, mCurrent.Origin.Z);
                        Point3D pParent = new Point3D(mParent.Origin.X, mParent.Origin.Y, mParent.Origin.Z);
                        var line = GeometryHelper.CreateBoneLine(pParent, pCurrent, 0.1, boneColor);
                        if (line.Content != null)
                        {
                            _boneLineGroup.Children.Add(line.Content);
                        }
                    }
                }
            }

            // 剛体
            for (int i = 0; i < _rigidbodyVisuals.Count && i < _physics.RigidBodies.Count; i++)
            {
                var geom = _rigidbodyVisuals[i];
                var t = _physics.GetBodyTransform(i);
                var m = new Matrix3D(
                    t.M11, t.M12, t.M13, 0,
                    t.M21, t.M22, t.M23, 0,
                    t.M31, t.M32, t.M33, 0,
                    t.Origin.X, t.Origin.Y, t.Origin.Z, 1
                );
                geom.Transform = new MatrixTransform3D(m);
            }

            // CPUスキニング
            _update_mesh_skinning(matrices);
        }

        private void _update_mesh_skinning(IReadOnlyList<Matrix> boneMatrices)
        {
            if (_pmx == null || _subMeshes.Count == 0) return;
            int boneCount = _pmx.Bones.Count;
            if (boneMatrices.Count < boneCount) return;

            var skinningMatrices = new Matrix[boneCount];
            for (int b = 0; b < boneCount; b++)
            {
                var bone = _pmx.Bones[b];
                Matrix toOrigin = Matrix.Translation(-bone.Position[0], -bone.Position[1], -bone.Position[2]);
                skinningMatrices[b] = toOrigin * boneMatrices[b];
            }

            var origVertices = _pmx.VertexPositions;
            var skinnings = _pmx.VertexSkinnings;
            int vertexCount = origVertices.Count;

            var globalPositions = new Point3D[vertexCount];
            Parallel.For(0, vertexCount, i =>
            {
                var v = origVertices[i];
                if (i >= skinnings.Count || skinnings[i].BoneIndices.Length == 0)
                {
                    globalPositions[i] = new Point3D(v[0], v[1], v[2]);
                    return;
                }

                var skin = skinnings[i];
                float outX = 0, outY = 0, outZ = 0;
                for (int k = 0; k < skin.BoneIndices.Length; k++)
                {
                    int bIdx = skin.BoneIndices[k];
                    float w = skin.Weights[k];
                    if (w <= 0.0001f || bIdx < 0 || bIdx >= boneCount) continue;

                    var mat = skinningMatrices[bIdx];
                    outX += ((v[0] * mat.M11) + (v[1] * mat.M21) + (v[2] * mat.M31) + mat.M41) * w;
                    outY += ((v[0] * mat.M12) + (v[1] * mat.M22) + (v[2] * mat.M32) + mat.M42) * w;
                    outZ += ((v[0] * mat.M13) + (v[1] * mat.M23) + (v[2] * mat.M33) + mat.M43) * w;
                }
                globalPositions[i] = new Point3D(outX, outY, outZ);
            });

            foreach (var subMesh in _subMeshes)
            {
                int count = subMesh.GlobalVertexIndices.Count;
                var pts = new Point3D[count];
                for (int i = 0; i < count; i++)
                {
                    pts[i] = globalPositions[subMesh.GlobalVertexIndices[i]];
                }
                subMesh.Mesh.Positions = new Point3DCollection(pts);
            }
        }

        private void _init_camera_tracking()
        {
            if (_pmx == null) return;

            _trackingBoneIndex = -1;
            _lastTrackedBonePos = null;

            // 追従対象ボーンの探索 (センター > 全ての親 > 先頭ボーン)
            for (int i = 0; i < _pmx.Bones.Count; i++)
            {
                if (_pmx.Bones[i].Name == "センター")
                {
                    _trackingBoneIndex = i;
                    break;
                }
            }
            if (_trackingBoneIndex < 0)
            {
                for (int i = 0; i < _pmx.Bones.Count; i++)
                {
                    if (_pmx.Bones[i].Name == "全ての親")
                    {
                        _trackingBoneIndex = i;
                        break;
                    }
                }
            }
            if (_trackingBoneIndex < 0 && _pmx.Bones.Count > 0)
            {
                _trackingBoneIndex = 0;
            }

            if (_trackingBoneIndex >= 0 && _trackingBoneIndex < _pmx.Bones.Count)
            {
                var bPos = _pmx.Bones[_trackingBoneIndex].Position;
                _lastTrackedBonePos = new Vector3(bPos[0], bPos[1], bPos[2]);
                // モデル初期位置にカメラターゲットを配置 (WPF座標系反転: -X)
                _cameraTarget = new Point3D(-bPos[0], bPos[1] + 1.0, bPos[2]);
                _update_camera();
            }
        }

        private void _update_camera_tracking(IReadOnlyList<Matrix> matrices)
        {
            if (_trackingBoneIndex < 0 || _trackingBoneIndex >= matrices.Count) return;

            var currentPos = matrices[_trackingBoneIndex].Origin;
            if (_lastTrackedBonePos.HasValue)
            {
                var delta = currentPos - _lastTrackedBonePos.Value;
                if (MathF.Abs(delta.X) > 1e-4f || MathF.Abs(delta.Y) > 1e-4f || MathF.Abs(delta.Z) > 1e-4f)
                {
                    // WPFのミラー反転にあわせて追従ターゲットを更新
                    _cameraTarget = new Point3D(
                        _cameraTarget.X - delta.X,
                        _cameraTarget.Y + delta.Y,
                        _cameraTarget.Z + delta.Z
                    );
                    _update_camera();
                }
            }
            _lastTrackedBonePos = currentPos;
        }

        private void _update_camera()
        {
            double radTheta = _cameraTheta * Math.PI / 180.0;
            double radPhi = _cameraPhi * Math.PI / 180.0;

            double x = _cameraTarget.X + _cameraDistance * Math.Cos(radPhi) * Math.Sin(radTheta);
            double y = _cameraTarget.Y + _cameraDistance * Math.Sin(radPhi);
            double z = _cameraTarget.Z + _cameraDistance * Math.Cos(radPhi) * Math.Cos(radTheta);

            ViewportCamera.Position = new Point3D(x, y, z);
            ViewportCamera.LookDirection = new Vector3D(_cameraTarget.X - x, _cameraTarget.Y - y, _cameraTarget.Z - z);
        }

        private void Viewport_MouseDown(object sender, MouseButtonEventArgs e)
        {
            _lastMousePos = e.GetPosition(ViewportContainer);
            ViewportContainer.CaptureMouse();
        }

        private void Viewport_MouseMove(object sender, MouseEventArgs e)
        {
            if (!ViewportContainer.IsMouseCaptured) return;

            System.Windows.Point currentPos = e.GetPosition(ViewportContainer);
            System.Windows.Vector delta = currentPos - _lastMousePos;
            _lastMousePos = currentPos;

            if (e.LeftButton == MouseButtonState.Pressed)
            {
                _cameraTheta -= delta.X * 0.4;
                _cameraPhi = Math.Clamp(_cameraPhi + delta.Y * 0.4, -85.0, 85.0);
                _update_camera();
            }
            else if (e.RightButton == MouseButtonState.Pressed)
            {
                double radTheta = _cameraTheta * Math.PI / 180.0;
                Vector3D right = new Vector3D(Math.Cos(radTheta), 0, -Math.Sin(radTheta));
                Vector3D up = new Vector3D(0, 1, 0);

                _cameraTarget -= right * (delta.X * 0.05);
                _cameraTarget += up * (delta.Y * 0.05);
                _update_camera();
            }
        }

        private void Viewport_MouseUp(object sender, MouseButtonEventArgs e)
        {
            if (ViewportContainer.IsMouseCaptured)
            {
                ViewportContainer.ReleaseMouseCapture();
            }
        }

        private void Viewport_MouseLeave(object sender, MouseEventArgs e)
        {
            if (ViewportContainer.IsMouseCaptured)
            {
                ViewportContainer.ReleaseMouseCapture();
            }
        }

        private void Viewport_MouseWheel(object sender, MouseWheelEventArgs e)
        {
            _cameraDistance = Math.Clamp(_cameraDistance - e.Delta * 0.03, 2.0, 200.0);
            _update_camera();
        }
    }
}

