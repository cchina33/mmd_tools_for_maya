using System;
using System.IO;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Media3D;
using System.Windows.Threading;
using Microsoft.Win32;
using BulletSharp;
using BulletSharp.Math;
using Matrix = BulletSharp.Math.Matrix;

namespace MmdPhysicsBridge
{
    public partial class MainWindow : Window
    {
        // カメラ制御用パラメータ (正面向き 180度から開始)
        private System.Windows.Point _lastMousePos;
        private double _cameraDistance = 45.0;
        private double _cameraTheta = 180.0;  // 正面からモデルを捉える
        private double _cameraPhi = 10.0;     // 垂直角
        private Point3D _cameraTarget = new Point3D(0, 10, 0);

        // 読み込んだPMXデータとVMDモーション
        private PmxModelData? _currentPmxModel;
        private VmdMotionData? _currentVmdData;

        // 物理シミュレーションエンジン
        private readonly PhysicsSimulationEngine _physicsEngine = new();

        // アニメーション再生タイマー (60fps表示)
        private readonly DispatcherTimer _playTimer = new();
        private int _currentFrame = 0;
        private double _currentFrameTime = 0.0;
        private double _startPlaybackFrame = 0.0;
        private readonly Stopwatch _playbackStopwatch = new();

        // 描画要素の参照保持（トランスフォーム更新用）
        private readonly List<GeometryModel3D> _rigidbodyVisuals = new();
        private readonly List<GeometryModel3D> _jointVisuals = new();
        private readonly List<TranslateTransform3D> _boneJointTransforms = new();
        private Model3DGroup? _boneLineGroup;

        // ボーンのワールド姿勢キャッシュとFKローカル変換行列キャッシュ
        private readonly List<Matrix> _boneWorldMatrices = new();
        private readonly List<Matrix> _cachedLocalMatrices = new();

        // メッシュ描画とルート追従用
        private ModelVisual3D? _meshVisual;
        private readonly TranslateTransform3D _meshTransform = new();
        private Point3D _initialRootPosition = new Point3D(0, 0, 0);
        private string _rootBoneName = "";

        // スキニング用サブメッシュデータ
        private class SubMeshData
        {
            public MeshGeometry3D Mesh { get; set; } = null!;
            public List<int> GlobalVertexIndices { get; set; } = new();
        }
        private readonly List<SubMeshData> _subMeshes = new();
        private readonly Dictionary<string, (ImageBrush Brush, bool HasAlpha)> _textureCache = new();
        private readonly DispatcherTimer _alwaysPhysicsTimer = new();

        public enum PhysicsSimulationMode
        {
            PlayOnly,
            Always,
            Off
        }

        private PhysicsSimulationMode GetPhysicsMode()
        {
            if (RbPhysicsOff?.IsChecked == true) return PhysicsSimulationMode.Off;
            if (RbPhysicsAlways?.IsChecked == true) return PhysicsSimulationMode.Always;
            return PhysicsSimulationMode.PlayOnly;
        }

        public MainWindow()
        {
            InitializeComponent();
            _physicsEngine.InitializeWorld();
            _update_camera();
            _init_scene_grid();

            // タイマー設定 (約16.6ms = 60fps表示)
            _playTimer.Interval = TimeSpan.FromMilliseconds(16.6);
            _playTimer.Tick += PlayTimer_Tick;

            _alwaysPhysicsTimer.Interval = TimeSpan.FromMilliseconds(16.6);
            _alwaysPhysicsTimer.Tick += AlwaysPhysicsTimer_Tick;
        }

        private void _init_scene_grid()
        {
            GridContainer.Children.Clear();
            GridContainer.Children.Add(GeometryHelper.CreateGrid(40.0, 2.0));
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

        private void OnVisibilityChanged(object sender, RoutedEventArgs e)
        {
            if (MainViewport == null || MeshContainer == null || BoneContainer == null || RigidbodyContainer == null || JointContainer == null) return;

            UpdateVisualPresence(MeshContainer, ChkShowMesh.IsChecked == true);
            UpdateVisualPresence(BoneContainer, ChkShowBones.IsChecked == true);
            UpdateVisualPresence(RigidbodyContainer, ChkShowRigidbodies.IsChecked == true);
            UpdateVisualPresence(JointContainer, ChkShowJoints.IsChecked == true);
        }

        private void UpdateVisualPresence(Visual3D visual, bool show)
        {
            if (show)
            {
                if (!MainViewport.Children.Contains(visual))
                {
                    MainViewport.Children.Add(visual);
                }
            }
            else
            {
                if (MainViewport.Children.Contains(visual))
                {
                    MainViewport.Children.Remove(visual);
                }
            }
        }

        private void BtnBrowsePmx_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new OpenFileDialog
            {
                Filter = "PMXモデルファイル (*.pmx)|*.pmx|全てのファイル (*.*)|*.*"
            };
            if (dlg.ShowDialog() == true)
            {
                TxtPmxPath.Text = dlg.FileName;
                _load_and_display_pmx(dlg.FileName);
            }
        }

        private void _load_and_display_pmx(string filePath)
        {
            try
            {
                TxtStatus.Text = "PMXモデル読み込み中...";
                _currentPmxModel = PmxLoader.Load(filePath);

                // 物理エンジンの剛体・Joint構築
                _physicsEngine.BuildPhysicsFromPmx(_currentPmxModel);

                // レイヤーコンテナのクリアとMMD座標系（左右反転）補正
                MeshContainer.Children.Clear();
                BoneContainer.Children.Clear();
                RigidbodyContainer.Children.Clear();
                JointContainer.Children.Clear();
                _rigidbodyVisuals.Clear();
                _jointVisuals.Clear();
                _boneJointTransforms.Clear();
                _boneWorldMatrices.Clear();
                _cachedLocalMatrices.Clear();

                var mirrorTransform = new ScaleTransform3D(-1, 1, 1);
                MeshContainer.Transform = mirrorTransform;
                BoneContainer.Transform = mirrorTransform;
                RigidbodyContainer.Transform = mirrorTransform;
                JointContainer.Transform = mirrorTransform;

                for (int i = 0; i < _currentPmxModel.Bones.Count; i++)
                {
                    _boneWorldMatrices.Add(Matrix.Identity);
                    _cachedLocalMatrices.Add(Matrix.Identity);
                }

                // ポリゴンメッシュの描画
                _subMeshes.Clear();
                _textureCache.Clear();
                if (_currentPmxModel.VertexPositions.Count > 0 && _currentPmxModel.Indices.Count > 0)
                {
                    var meshGroup = new Model3DGroup();
                    int indexOffset = 0;

                    if (_currentPmxModel.Materials.Count > 0)
                    {
                        var opaqueModels = new List<GeometryModel3D>();
                        var transparentModels = new List<GeometryModel3D>();

                        foreach (var mat in _currentPmxModel.Materials)
                        {
                            if (mat.SurfaceCount <= 0) continue;
                            int count = Math.Min(mat.SurfaceCount, _currentPmxModel.Indices.Count - indexOffset);
                            if (count <= 0) break;

                            var mesh = new MeshGeometry3D();
                            var localMap = new Dictionary<int, int>();
                            var subMesh = new SubMeshData { Mesh = mesh };

                            for (int i = 0; i < count; i += 3)
                            {
                                if (i + 2 >= count) break;
                                int g0 = _currentPmxModel.Indices[indexOffset + i];
                                int g1 = _currentPmxModel.Indices[indexOffset + i + 1];
                                int g2 = _currentPmxModel.Indices[indexOffset + i + 2];

                                int GetOrAddLocal(int globalIdx)
                                {
                                    if (!localMap.TryGetValue(globalIdx, out int localIdx))
                                    {
                                        localIdx = mesh.Positions.Count;
                                        localMap[globalIdx] = localIdx;
                                        subMesh.GlobalVertexIndices.Add(globalIdx);
                                        var v = _currentPmxModel.VertexPositions[globalIdx];
                                        mesh.Positions.Add(new Point3D(v[0], v[1], v[2]));

                                        // UV座標の設定
                                        if (globalIdx < _currentPmxModel.VertexUVs.Count)
                                        {
                                            var uv = _currentPmxModel.VertexUVs[globalIdx];
                                            mesh.TextureCoordinates.Add(new System.Windows.Point(uv[0], uv[1]));
                                        }
                                        else
                                        {
                                            mesh.TextureCoordinates.Add(new System.Windows.Point(0, 0));
                                        }
                                    }
                                    return localIdx;
                                }

                                int l0 = GetOrAddLocal(g0);
                                int l1 = GetOrAddLocal(g1);
                                int l2 = GetOrAddLocal(g2);

                                // ScaleX = -1 の反転変換下で表面となるPMX標準順序
                                mesh.TriangleIndices.Add(l0);
                                mesh.TriangleIndices.Add(l1);
                                mesh.TriangleIndices.Add(l2);
                            }
                            indexOffset += count;
                            _subMeshes.Add(subMesh);

                            // 通常テクスチャの読み込み（スフィアやトゥーンとは分離）
                            ImageBrush? texBrush = null;
                            bool hasAlphaTexture = false;
                            if (mat.TextureIndex >= 0 && mat.TextureIndex < _currentPmxModel.Textures.Count)
                            {
                                string texPath = _currentPmxModel.Textures[mat.TextureIndex];
                                texBrush = LoadTexture(filePath, texPath, out hasAlphaTexture);
                            }

                            // 透過判定:
                            // 顔・肌・体・服・ボタン・足などの主要部位は不透明メッシュとして最優先描画
                            string matNameLower = (mat.Name ?? "").ToLowerInvariant();
                            bool isOverlayOrTransparent = (mat.Diffuse[3] < 0.95f)
                                || matNameLower.Contains("透")
                                || matNameLower.Contains("涙")
                                || matNameLower.Contains("shadow")
                                || matNameLower.Contains("影")
                                || matNameLower.Contains("ハイライト")
                                || matNameLower.Contains("チーク")
                                || matNameLower.Contains("照れ");

                            bool isBaseGeometry = matNameLower.Contains("顔")
                                || matNameLower.Contains("肌")
                                || matNameLower.Contains("skin")
                                || matNameLower.Contains("face")
                                || matNameLower.Contains("体")
                                || matNameLower.Contains("body")
                                || matNameLower.Contains("服")
                                || matNameLower.Contains("ボタン")
                                || matNameLower.Contains("button")
                                || matNameLower.Contains("靴")
                                || matNameLower.Contains("足")
                                || matNameLower.Contains("leg")
                                || matNameLower.Contains("腕")
                                || matNameLower.Contains("arm")
                                || matNameLower.Contains("手")
                                || matNameLower.Contains("hand");

                            bool isTransparent = isOverlayOrTransparent && !isBaseGeometry;

                            Material material;
                            if (texBrush != null)
                            {
                                material = new DiffuseMaterial(texBrush);
                            }
                            else
                            {
                                byte alphaByte = isTransparent ? (byte)Math.Clamp((int)(mat.Diffuse[3] * 255), 40, 255) : (byte)255;
                                Color matColor = Color.FromArgb(
                                    alphaByte,
                                    (byte)Math.Clamp((int)(mat.Diffuse[0] * 255), 0, 255),
                                    (byte)Math.Clamp((int)(mat.Diffuse[1] * 255), 0, 255),
                                    (byte)Math.Clamp((int)(mat.Diffuse[2] * 255), 0, 255)
                                );
                                material = new DiffuseMaterial(new SolidColorBrush(matColor));
                            }

                            // 全マテリアルで両面描画を有効化して裏抜けを防止
                            var geomModel = new GeometryModel3D(mesh, material)
                            {
                                BackMaterial = material
                            };

                            if (isTransparent)
                            {
                                transparentModels.Add(geomModel);
                            }
                            else
                            {
                                opaqueModels.Add(geomModel);
                            }
                        }

                        // 不透明メッシュをベースとして先に描画、透過メッシュを手前に後から描画して遮蔽抜けを防止
                        foreach (var m in opaqueModels)
                        {
                            meshGroup.Children.Add(m);
                        }
                        foreach (var m in transparentModels)
                        {
                            meshGroup.Children.Add(m);
                        }
                    }

                    _meshTransform.OffsetX = 0;
                    _meshTransform.OffsetY = 0;
                    _meshTransform.OffsetZ = 0;
                    _meshVisual = new ModelVisual3D { Content = meshGroup, Transform = _meshTransform };
                    MeshContainer.Children.Add(_meshVisual);
                }

                // ルート移動ボーン（全ての親またはセンター）の探索
                _rootBoneName = "";
                _initialRootPosition = new Point3D(0, 0, 0);
                foreach (var b in _currentPmxModel.Bones)
                {
                    if (b.Name == "全ての親" || b.Name == "センター")
                    {
                        _rootBoneName = b.Name;
                        _initialRootPosition = new Point3D(b.Position[0], b.Position[1], b.Position[2]);
                        if (b.Name == "センター") break;
                    }
                }

                // ボーン骨格の描画
                var boneGroup = new Model3DGroup();
                Color boneColor = Color.FromArgb(200, 100, 200, 255);
                Color jointColor = Color.FromArgb(240, 255, 200, 50);

                _boneLineGroup = new Model3DGroup();

                for (int i = 0; i < _currentPmxModel.Bones.Count; i++)
                {
                    var bone = _currentPmxModel.Bones[i];
                    Point3D p = new Point3D(bone.Position[0], bone.Position[1], bone.Position[2]);

                    var sphere = GeometryHelper.CreateSphere(new Point3D(0, 0, 0), 0.25, jointColor, 6, 4);
                    if (sphere.Content is GeometryModel3D geom)
                    {
                        var trans = new TranslateTransform3D(p.X, p.Y, p.Z);
                        geom.Transform = trans;
                        _boneJointTransforms.Add(trans);
                        boneGroup.Children.Add(geom);
                    }
                }

                _update_bone_lines();
                boneGroup.Children.Add(_boneLineGroup);
                BoneContainer.Children.Add(new ModelVisual3D { Content = boneGroup });

                // 剛体コライダーの描画
                var rbGroup = new Model3DGroup();
                foreach (var rb in _currentPmxModel.Rigidbodies)
                {
                    Point3D p = new Point3D(rb.Position[0], rb.Position[1], rb.Position[2]);

                    Color rbColor = rb.PhysicsMode switch
                    {
                        PmxPhysicsMode.FollowBone => Color.FromArgb(130, 46, 204, 113),     // 緑 (追従)
                        PmxPhysicsMode.Physics => Color.FromArgb(130, 52, 152, 219),        // 青 (物理)
                        _ => Color.FromArgb(130, 241, 196, 15)                              // 黄 (位置合わせ)
                    };

                    ModelVisual3D? shapeVisual = null;
                    if (rb.Shape == PmxColliderShape.Sphere)
                    {
                        shapeVisual = GeometryHelper.CreateSphere(new Point3D(0, 0, 0), rb.Size[0], rbColor, 10, 6);
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
                        var group = new Transform3DGroup();
                        group.Children.Add(new TranslateTransform3D(p.X, p.Y, p.Z));
                        geom.Transform = group;

                        _rigidbodyVisuals.Add(geom);
                        rbGroup.Children.Add(geom);
                    }
                }
                RigidbodyContainer.Children.Add(new ModelVisual3D { Content = rbGroup });

                // Joint (物理拘束) の描画
                var jointGroup = new Model3DGroup();
                Color jointCubeColor = Color.FromArgb(200, 235, 77, 190); // 鮮やかなマゼンタ
                foreach (var joint in _currentPmxModel.Joints)
                {
                    Point3D p = new Point3D(joint.Position[0], joint.Position[1], joint.Position[2]);
                    var jointVisual = GeometryHelper.CreateBox(new Point3D(0, 0, 0), new Vector3D(0.35, 0.35, 0.35), jointCubeColor);
                    if (jointVisual.Content is GeometryModel3D jGeom)
                    {
                        var group = new Transform3DGroup();
                        group.Children.Add(new TranslateTransform3D(p.X, p.Y, p.Z));
                        jGeom.Transform = group;

                        _jointVisuals.Add(jGeom);
                        jointGroup.Children.Add(jGeom);
                    }
                }
                JointContainer.Children.Add(new ModelVisual3D { Content = jointGroup });

                // 表示設定の初期反映
                OnVisibilityChanged(this, new RoutedEventArgs());

                // カメラ注視点をモデルの中心付近に調整 (正面)
                _cameraTarget = new Point3D(0, 10, 0);
                _cameraDistance = 35.0;
                _cameraTheta = 180.0;
                _update_camera();

                TxtStatus.Text = $"読み込み成功: {_currentPmxModel.ModelName}\n" +
                                 $"・頂点数: {_currentPmxModel.VertexPositions.Count:N0}\n" +
                                 $"・剛体: {_currentPmxModel.Rigidbodies.Count} 個 (物理構築済)\n" +
                                 $"・Joint: {_currentPmxModel.Joints.Count} 個";
            }
            catch (Exception ex)
            {
                string errMsg = ex.InnerException != null ? $"{ex.Message}\n詳細: {ex.InnerException.Message}" : ex.Message;
                TxtStatus.Text = $"PMX読み込みエラー:\n{errMsg}";
                MessageBox.Show($"モデルの読み込みに失敗しました:\n\n{errMsg}", "読み込みエラー", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private void BtnBrowseVmd_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new OpenFileDialog
            {
                Filter = "VMDモーションファイル (*.vmd)|*.vmd|全てのファイル (*.*)|*.*"
            };
            if (dlg.ShowDialog() == true)
            {
                TxtVmdPath.Text = dlg.FileName;
                _load_vmd_file(dlg.FileName);
            }
        }

        private void _load_vmd_file(string vmdPath)
        {
            try
            {
                TxtStatus.Text = "VMDモーション読み込み中...";
                _currentVmdData = VmdLoader.Load(vmdPath);

                if (_currentVmdData != null)
                {
                    SliderTimeline.Minimum = 0;
                    SliderTimeline.Maximum = Math.Max(1, _currentVmdData.MaxFrame);
                    SliderTimeline.Value = 0;
                    _currentFrame = 0;

                    TxtFrameInfo.Text = $"フレーム: 0 / {_currentVmdData.MaxFrame}";
                    TxtStatus.Text = $"VMD読み込み成功: {Path.GetFileName(vmdPath)}\n" +
                                     $"・総フレーム数: {_currentVmdData.MaxFrame} (約{_currentVmdData.MaxFrame / 30.0:F1}秒)\n" +
                                     $"・アニメーショントラック数: {_currentVmdData.BoneTracks.Count} ボーン";

                    if (_currentPmxModel != null)
                    {
                        // モーションのフレーム0に全剛体を初期配置スナップ
                        _evaluate_fk_and_update(0, resetAllBodies: true);
                        if (GetPhysicsMode() != PhysicsSimulationMode.Off)
                        {
                            _apply_physics_to_bones();
                        }
                        _sync_bone_visuals_after_physics();
                        _update_rigidbody_visuals();
                        _update_joint_visuals();
                        _update_mesh_skinning();
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"VMD読み込みエラー:\n{ex.Message}", "エラー", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private void PhysicsMode_Changed(object sender, RoutedEventArgs e)
        {
            if (_currentPmxModel == null) return;

            var mode = GetPhysicsMode();
            if (mode == PhysicsSimulationMode.Always)
            {
                if (!_alwaysPhysicsTimer.IsEnabled) _alwaysPhysicsTimer.Start();
            }
            else
            {
                _alwaysPhysicsTimer.Stop();
            }

            bool isOff = mode == PhysicsSimulationMode.Off;
            _evaluate_fk_and_update(_currentFrame, resetAllBodies: isOff);
            if (!isOff)
            {
                _apply_physics_to_bones();
            }
            _sync_bone_visuals_after_physics();
            _update_rigidbody_visuals();
            _update_joint_visuals();
            _update_mesh_skinning();
        }

        private void AlwaysPhysicsTimer_Tick(object? sender, EventArgs e)
        {
            if (_currentPmxModel == null) return;
            if (_playTimer.IsEnabled) return; // 再生中はPlayTimerが駆動
            if (GetPhysicsMode() != PhysicsSimulationMode.Always) return;

            // 静止フレームのまま物理シミュレーションを1/60秒進める
            _physicsEngine.StepSimulation(1.0f / 60.0f, 2, 1.0f / 60.0f);
            _apply_physics_to_bones();
            _sync_bone_visuals_after_physics();
            _update_rigidbody_visuals();
            _update_joint_visuals();
            _update_mesh_skinning((float)_currentFrameTime);
        }

        private void BtnPlay_Click(object sender, RoutedEventArgs e)
        {
            if (_currentPmxModel == null)
            {
                MessageBox.Show("PMXモデルを指定してください。", "案内", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }
            if (_currentVmdData == null)
            {
                MessageBox.Show("VMDモーションファイルを指定してください。", "案内", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            _startPlaybackFrame = _currentFrameTime;
            _playbackStopwatch.Restart();
            _playTimer.Start();
            TxtStatus.Text = "シミュレーション再生中 (60fps表示)...";
        }

        private void BtnPause_Click(object sender, RoutedEventArgs e)
        {
            _playTimer.Stop();
            _playbackStopwatch.Stop();
            TxtStatus.Text = "シミュレーション停止";
        }

        private void BtnReset_Click(object sender, RoutedEventArgs e)
        {
            _playTimer.Stop();
            _playbackStopwatch.Reset();
            _currentFrameTime = 0.0;
            _currentFrame = 0;
            SliderTimeline.Value = 0;

            if (_currentPmxModel != null)
            {
                _physicsEngine.ResetWorld(_currentPmxModel);
                _evaluate_fk_and_update(0.0f, resetAllBodies: true);
                if (GetPhysicsMode() != PhysicsSimulationMode.Off)
                {
                    _apply_physics_to_bones();
                }
                _sync_bone_visuals_after_physics();
                _update_rigidbody_visuals();
                _update_joint_visuals();
                _update_mesh_skinning(0.0f);
            }
            TxtStatus.Text = "シミュレーションを初期状態へリセット";
        }

        private void SliderTimeline_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (_currentPmxModel != null && _currentVmdData != null && !_playTimer.IsEnabled)
            {
                _currentFrameTime = SliderTimeline.Value;
                _currentFrame = (int)_currentFrameTime;
                _startPlaybackFrame = _currentFrameTime;
                _playbackStopwatch.Reset();

                if (TxtFrameInfo != null)
                {
                    TxtFrameInfo.Text = $"フレーム: {_currentFrame} / {_currentVmdData.MaxFrame}";
                }

                bool isOff = GetPhysicsMode() == PhysicsSimulationMode.Off;
                _evaluate_fk_and_update((float)_currentFrameTime, resetAllBodies: isOff);
                if (!isOff)
                {
                    if (GetPhysicsMode() == PhysicsSimulationMode.Always)
                    {
                        _physicsEngine.StepSimulation(1.0f / 60.0f, 2, 1.0f / 60.0f);
                    }
                    _apply_physics_to_bones();
                }
                _sync_bone_visuals_after_physics();
                _update_rigidbody_visuals();
                _update_joint_visuals();
                _update_mesh_skinning((float)_currentFrameTime);
            }
        }

        // 60fps表示・実時間30fpsアニメーション再生ループ処理
        private void PlayTimer_Tick(object? sender, EventArgs e)
        {
            if (_currentPmxModel == null || _currentVmdData == null) return;

            // 実時間経過からフレーム時刻を算出 (1秒あたり30フレーム進む)
            double elapsedSec = _playbackStopwatch.Elapsed.TotalSeconds;
            _currentFrameTime = _startPlaybackFrame + (elapsedSec * 30.0);

            if (_currentFrameTime > _currentVmdData.MaxFrame)
            {
                // ループ再生
                _startPlaybackFrame = 0.0;
                _playbackStopwatch.Restart();
                _currentFrameTime = 0.0;
            }

            _currentFrame = (int)_currentFrameTime;
            float fFrame = (float)_currentFrameTime;

            bool isOff = GetPhysicsMode() == PhysicsSimulationMode.Off;

            // VMDからボーンFK姿勢をサブフレーム精度で計算
            _evaluate_fk_and_update(fFrame, resetAllBodies: isOff);

            if (!isOff)
            {
                // 物理シミュレーションを60fpsで1ステップ進める (1/60秒)
                _physicsEngine.StepSimulation(1.0f / 60.0f, 2, 1.0f / 60.0f);

                // 物理剛体（スカート・髪等）の計算結果をボーンへ書き戻し、剛体なし子ボーンへ伝達
                _apply_physics_to_bones();
            }

            // ボーン骨格ライン、剛体、ジョイント表示を更新
            _sync_bone_visuals_after_physics();
            _update_rigidbody_visuals();
            _update_joint_visuals();

            // メッシュのCPUスキニング更新 (サブフレーム補間)
            _update_mesh_skinning(fFrame);

            SliderTimeline.Value = _currentFrame;
            if (TxtFrameInfo != null)
            {
                TxtFrameInfo.Text = $"フレーム: {_currentFrame} / {_currentVmdData.MaxFrame} (30fps / 60fps表示)";
            }
        }

        // 指定フレームにおけるFK階層計算・足IK・付与親計算と物理剛体更新
        private void _evaluate_fk_and_update(float frame, bool resetAllBodies = false)
        {
            if (_currentPmxModel == null) return;

            var bones = _currentPmxModel.Bones;
            int n = bones.Count;
            var boneWorldPositions = new Dictionary<string, float[]>();
            var boneWorldRotations = new Dictionary<string, Matrix>();

            // VMDから得たボーン固有のローカル回転・移動
            var ownRot = new Matrix[n];
            var ownTrans = new Vector3[n];
            // 付与親・IKを反映した最終ローカル回転・移動
            var localRot = new Matrix[n];
            var localTrans = new Vector3[n];
            var ikSolved = new bool[n];
            var localDone = new bool[n];
            var worldDone = new bool[n];

            // 子ボーン一覧 (IK中の部分更新用)
            var children = new List<int>[n];
            for (int i = 0; i < n; i++) children[i] = new List<int>();
            for (int i = 0; i < n; i++)
            {
                int p = bones[i].ParentIndex;
                if (p >= 0 && p < n && p != i) children[p].Add(i);
            }

            for (int i = 0; i < n; i++)
            {
                var (trans, quat) = _currentVmdData != null
                    ? _currentVmdData.SampleBone(bones[i].Name, frame)
                    : (new float[] { 0, 0, 0 }, new float[] { 0, 0, 0, 1 });
                Matrix r = Matrix.RotationQuaternion(new BulletSharp.Math.Quaternion(quat[0], quat[1], quat[2], quat[3]));
                r.Origin = new Vector3(0, 0, 0);
                ownRot[i] = r;
                ownTrans[i] = new Vector3(trans[0], trans[1], trans[2]);
            }

            // 付与親を反映したローカル姿勢の計算 (付与元を先に確定させる)
            void ComputeLocal(int i)
            {
                if (localDone[i]) return;
                localDone[i] = true;
                if (ikSolved[i]) return; // IKで解いた回転はそのまま維持

                var bone = bones[i];
                Matrix rot = ownRot[i];
                Vector3 t = ownTrans[i];
                int src = bone.InheritBoneIndex;
                if (src >= 0 && src < n && src != i && Math.Abs(bone.InheritRate) > 0.0001f)
                {
                    ComputeLocal(src);
                    if ((bone.Flags & 0x0100) != 0)
                    {
                        rot = rot * ScaleRotation(localRot[src], bone.InheritRate);
                    }
                    if ((bone.Flags & 0x0200) != 0)
                    {
                        var st = localTrans[src];
                        t = new Vector3(t.X + st.X * bone.InheritRate, t.Y + st.Y * bone.InheritRate, t.Z + st.Z * bone.InheritRate);
                    }
                }
                localRot[i] = rot;
                localTrans[i] = t;
            }

            // 親からの相対オフセットを含むローカル変換行列
            Matrix LocalMatrix(int i)
            {
                var bone = bones[i];
                Matrix m = localRot[i];
                int p = bone.ParentIndex;
                float ox = bone.Position[0] + localTrans[i].X;
                float oy = bone.Position[1] + localTrans[i].Y;
                float oz = bone.Position[2] + localTrans[i].Z;
                if (p >= 0 && p < n && p != i)
                {
                    ox -= bones[p].Position[0];
                    oy -= bones[p].Position[1];
                    oz -= bones[p].Position[2];
                }
                m.Origin = new Vector3(ox, oy, oz);
                return m;
            }

            void ComputeWorld(int i)
            {
                if (worldDone[i]) return;
                worldDone[i] = true;
                int p = bones[i].ParentIndex;
                if (p >= 0 && p < n && p != i)
                {
                    ComputeWorld(p);
                    _boneWorldMatrices[i] = LocalMatrix(i) * _boneWorldMatrices[p];
                }
                else
                {
                    _boneWorldMatrices[i] = LocalMatrix(i);
                }
            }

            // 指定ボーン以下のワールド行列を更新 (子ボーン本来のローカル回転は維持)
            void UpdateSubtree(int i)
            {
                int p = bones[i].ParentIndex;
                _boneWorldMatrices[i] = (p >= 0 && p < n && p != i)
                    ? LocalMatrix(i) * _boneWorldMatrices[p]
                    : LocalMatrix(i);
                foreach (int c in children[i]) UpdateSubtree(c);
            }

            // FK計算
            for (int i = 0; i < n; i++) ComputeLocal(i);
            for (int i = 0; i < n; i++) ComputeWorld(i);

            // 足IK (主足IKのみ対象、VMD側でIKがOFFの区間はFKのまま)
            if (ChkEnableIk.IsChecked == true)
            {
                for (int i = 0; i < n; i++)
                {
                    var ikBone = bones[i];
                    if (ikBone.Name != "左足ＩＫ" && ikBone.Name != "右足ＩＫ") continue;
                    if (_currentVmdData != null && !_currentVmdData.IsIkEnabled(ikBone.Name, frame)) continue;
                    SolveIk(i);
                }
            }

            // CCD-IKソルバー (リンクを根元側へ順に回してターゲットへ近づける)
            void SolveIk(int ikIdx)
            {
                var ik = bones[ikIdx].IkData;
                if (ik == null || ik.Links.Count == 0) return;
                int targetIdx = ik.TargetBoneIndex;
                if (targetIdx < 0 || targetIdx >= n) return;

                Vector3 targetPos = _boneWorldMatrices[ikIdx].Origin;
                float unitAngle = ik.LimitAngle > 0 ? ik.LimitAngle : MathF.PI;
                int loops = Math.Clamp(ik.LoopCount, 1, 64);

                for (int loop = 0; loop < loops; loop++)
                {
                    foreach (var link in ik.Links)
                    {
                        int li = link.BoneIndex;
                        if (li < 0 || li >= n || li == targetIdx) continue;

                        Vector3 linkPos = _boneWorldMatrices[li].Origin;
                        Vector3 effPos = _boneWorldMatrices[targetIdx].Origin;

                        // リンクのローカル空間での方向ベクトル
                        Vector3 le = ToLocalDir(_boneWorldMatrices[li], effPos - linkPos);
                        Vector3 lt = ToLocalDir(_boneWorldMatrices[li], targetPos - linkPos);
                        if (le.LengthSquared < 1e-8f || lt.LengthSquared < 1e-8f) continue;

                        bool xOnly = link.HasLimit
                            && Math.Abs(link.MinAngle[1]) < 1e-4f && Math.Abs(link.MaxAngle[1]) < 1e-4f
                            && Math.Abs(link.MinAngle[2]) < 1e-4f && Math.Abs(link.MaxAngle[2]) < 1e-4f;

                        if (xOnly)
                        {
                            // ひざ等: X軸まわりの角度だけで解き、PMXの制限角でクランプ
                            float cross = le.Y * lt.Z - le.Z * lt.Y;
                            float dot = le.Y * lt.Y + le.Z * lt.Z;
                            float delta = Math.Clamp(MathF.Atan2(cross, dot), -unitAngle, unitAngle);
                            float cur = MathF.Atan2(localRot[li].M23, localRot[li].M22);
                            float lo = Math.Min(link.MinAngle[0], link.MaxAngle[0]);
                            float hi = Math.Max(link.MinAngle[0], link.MaxAngle[0]);
                            localRot[li] = RotX(Math.Clamp(cur + delta, lo, hi));
                        }
                        else
                        {
                            le.Normalize();
                            lt.Normalize();
                            float dot = Math.Clamp(Vector3.Dot(le, lt), -1.0f, 1.0f);
                            float angle = MathF.Acos(dot);
                            if (angle < 1e-5f) continue;
                            angle = Math.Min(angle, unitAngle);

                            Vector3 axis = Vector3.Cross(le, lt);
                            if (axis.LengthSquared < 1e-10f) continue;
                            axis.Normalize();

                            Matrix newRot = AxisAngle(axis, angle) * localRot[li];
                            if (link.HasLimit)
                            {
                                newRot = ClampEuler(newRot, link.MinAngle, link.MaxAngle);
                            }
                            localRot[li] = newRot;
                        }

                        ikSolved[li] = true;
                        UpdateSubtree(li);
                    }

                    if ((_boneWorldMatrices[targetIdx].Origin - targetPos).LengthSquared < 1e-6f) break;
                }
            }

            // IK結果を付与親 (足D等) へ伝えるため、ローカル姿勢とワールド行列を再計算
            Array.Clear(localDone);
            Array.Clear(worldDone);
            for (int i = 0; i < n; i++) ComputeLocal(i);
            for (int i = 0; i < n; i++) ComputeWorld(i);

            // 物理演算後の剛体なし子ボーン追従用として、各ボーンのローカル変換行列を保持
            _cachedLocalMatrices.Clear();
            for (int i = 0; i < n; i++)
            {
                _cachedLocalMatrices.Add(LocalMatrix(i));
            }

            for (int i = 0; i < bones.Count; i++)
            {
                var bone = bones[i];
                var wp = _boneWorldMatrices[i].Origin;
                boneWorldPositions[bone.Name] = new float[] { wp.X, wp.Y, wp.Z };
                boneWorldRotations[bone.Name] = _boneWorldMatrices[i];

                // 3Dビューポートのボーン関節球位置を更新
                if (i < _boneJointTransforms.Count)
                {
                    _boneJointTransforms[i].OffsetX = wp.X;
                    _boneJointTransforms[i].OffsetY = wp.Y;
                    _boneJointTransforms[i].OffsetZ = wp.Z;
                }
            }

            // ボーン連結ラインの再描画
            _update_bone_lines();

            // 物理エンジンの剛体を更新
            if (resetAllBodies)
            {
                _physicsEngine.ResetBodiesToBones(boneWorldPositions, boneWorldRotations, bones);
            }
            else
            {
                _physicsEngine.UpdateKinematicBodies(boneWorldPositions, boneWorldRotations, bones);
            }
        }

        // ---- 回転行列ヘルパー (行ベクトル規約: v' = v * M) ----

        private static Matrix MakeRot(float m11, float m12, float m13, float m21, float m22, float m23, float m31, float m32, float m33)
        {
            Matrix m = Matrix.Identity;
            m.M11 = m11; m.M12 = m12; m.M13 = m13;
            m.M21 = m21; m.M22 = m22; m.M23 = m23;
            m.M31 = m31; m.M32 = m32; m.M33 = m33;
            return m;
        }

        private static Matrix RotX(float a)
        {
            float c = MathF.Cos(a), s = MathF.Sin(a);
            return MakeRot(1, 0, 0, 0, c, s, 0, -s, c);
        }

        private static Matrix RotY(float a)
        {
            float c = MathF.Cos(a), s = MathF.Sin(a);
            return MakeRot(c, 0, -s, 0, 1, 0, s, 0, c);
        }

        private static Matrix RotZ(float a)
        {
            float c = MathF.Cos(a), s = MathF.Sin(a);
            return MakeRot(c, s, 0, -s, c, 0, 0, 0, 1);
        }

        // 任意軸回転 (軸は正規化済みであること)
        private static Matrix AxisAngle(Vector3 axis, float angle)
        {
            float c = MathF.Cos(angle), s = MathF.Sin(angle), t = 1.0f - c;
            float x = axis.X, y = axis.Y, z = axis.Z;
            return MakeRot(
                c + x * x * t, x * y * t + z * s, x * z * t - y * s,
                x * y * t - z * s, c + y * y * t, y * z * t + x * s,
                x * z * t + y * s, y * z * t - x * s, c + z * z * t);
        }

        // ワールド方向ベクトルをボーンのローカル空間へ変換 (回転部分の転置を掛ける)
        private static Vector3 ToLocalDir(Matrix w, Vector3 v)
        {
            return new Vector3(
                v.X * w.M11 + v.Y * w.M12 + v.Z * w.M13,
                v.X * w.M21 + v.Y * w.M22 + v.Z * w.M23,
                v.X * w.M31 + v.Y * w.M32 + v.Z * w.M33);
        }

        // 回転量を rate 倍した回転行列 (付与親の付与率用)
        private static Matrix ScaleRotation(Matrix r, float rate)
        {
            if (Math.Abs(rate - 1.0f) < 1e-6f)
            {
                Matrix copy = r;
                copy.Origin = new Vector3(0, 0, 0);
                return copy;
            }

            float cosA = Math.Clamp((r.M11 + r.M22 + r.M33 - 1.0f) * 0.5f, -1.0f, 1.0f);
            float angle = MathF.Acos(cosA);
            if (angle < 1e-6f) return Matrix.Identity;

            var axis = new Vector3(r.M23 - r.M32, r.M31 - r.M13, r.M12 - r.M21);
            if (axis.LengthSquared < 1e-12f)
            {
                // 180度付近は軸が不安定なため近い方を採用
                if (rate >= 0.5f)
                {
                    Matrix copy = r;
                    copy.Origin = new Vector3(0, 0, 0);
                    return copy;
                }
                return Matrix.Identity;
            }
            axis.Normalize();
            return AxisAngle(axis, angle * rate);
        }

        // オイラー角 (M = RotX * RotY * RotZ) に分解して各軸を制限角でクランプ
        private static Matrix ClampEuler(Matrix r, float[] min, float[] max)
        {
            float ax = MathF.Atan2(r.M23, r.M33);
            float ay = MathF.Asin(Math.Clamp(-r.M13, -1.0f, 1.0f));
            float az = MathF.Atan2(r.M12, r.M11);

            ax = Math.Clamp(ax, Math.Min(min[0], max[0]), Math.Max(min[0], max[0]));
            ay = Math.Clamp(ay, Math.Min(min[1], max[1]), Math.Max(min[1], max[1]));
            az = Math.Clamp(az, Math.Min(min[2], max[2]), Math.Max(min[2], max[2]));

            return RotX(ax) * RotY(ay) * RotZ(az);
        }

        // ボーン接続ラインの描画更新
        private void _update_bone_lines()
        {
            if (_boneLineGroup == null || _currentPmxModel == null) return;

            _boneLineGroup.Children.Clear();
            Color boneColor = Color.FromArgb(200, 100, 200, 255);

            for (int i = 0; i < _currentPmxModel.Bones.Count; i++)
            {
                var bone = _currentPmxModel.Bones[i];
                if (bone.ParentIndex >= 0 && bone.ParentIndex < _currentPmxModel.Bones.Count)
                {
                    var mCurrent = _boneWorldMatrices[i];
                    var mParent = _boneWorldMatrices[bone.ParentIndex];

                    Point3D pCurrent = new Point3D(mCurrent.Origin.X, mCurrent.Origin.Y, mCurrent.Origin.Z);
                    Point3D pParent = new Point3D(mParent.Origin.X, mParent.Origin.Y, mParent.Origin.Z);

                    var line = GeometryHelper.CreateBoneLine(pParent, pCurrent, 0.12, boneColor);
                    if (line.Content != null)
                    {
                        _boneLineGroup.Children.Add(line.Content);
                    }
                }
            }
        }

        // 剛体3D表示のトランスフォーム更新
        private void _update_rigidbody_visuals()
        {
            for (int i = 0; i < _rigidbodyVisuals.Count && i < _physicsEngine.RigidBodies.Count; i++)
            {
                var geom = _rigidbodyVisuals[i];
                var transform = _physicsEngine.GetBodyTransform(i);

                var m = new Matrix3D(
                    transform.M11, transform.M12, transform.M13, 0,
                    transform.M21, transform.M22, transform.M23, 0,
                    transform.M31, transform.M32, transform.M33, 0,
                    transform.Origin.X, transform.Origin.Y, transform.Origin.Z, 1
                );

                geom.Transform = new MatrixTransform3D(m);
            }
        }

        // Joint (物理拘束) 3D表示のトランスフォーム更新
        private void _update_joint_visuals()
        {
            for (int i = 0; i < _jointVisuals.Count && i < _physicsEngine.JointCount; i++)
            {
                var geom = _jointVisuals[i];
                var transform = _physicsEngine.GetJointTransform(i);

                var m = new Matrix3D(
                    transform.M11, transform.M12, transform.M13, 0,
                    transform.M21, transform.M22, transform.M23, 0,
                    transform.M31, transform.M32, transform.M33, 0,
                    transform.Origin.X, transform.Origin.Y, transform.Origin.Z, 1
                );

                geom.Transform = new MatrixTransform3D(m);
            }
        }

        // 物理計算結果をボーンへ反映し、剛体を持たない子ボーン（髪先など）へ親の姿勢を伝達
        private void _apply_physics_to_bones()
        {
            if (_currentPmxModel == null) return;
            var bones = _currentPmxModel.Bones;
            int n = bones.Count;

            // 物理剛体（スカート・髪など）の計算結果を対応ボーンへ書き戻す
            int[] driveMode = _physicsEngine.SyncPhysicsToBones(_boneWorldMatrices, bones);

            // 物理で動いた親ボーンから、剛体を持たない子ボーン（髪先などの末端ボーン）へ姿勢を再帰伝達
            void PropagateToChildren(int parentIdx)
            {
                for (int c = 0; c < n; c++)
                {
                    if (bones[c].ParentIndex == parentIdx && driveMode[c] == 0)
                    {
                        if (c < _cachedLocalMatrices.Count)
                        {
                            _boneWorldMatrices[c] = _cachedLocalMatrices[c] * _boneWorldMatrices[parentIdx];
                        }
                        PropagateToChildren(c);
                    }
                }
            }

            for (int i = 0; i < n; i++)
            {
                if (driveMode[i] > 0)
                {
                    PropagateToChildren(i);
                }
            }
        }

        // 物理計算後のボーン関節球とボーン連結ラインの表示更新
        private void _sync_bone_visuals_after_physics()
        {
            if (_currentPmxModel == null) return;

            for (int i = 0; i < _currentPmxModel.Bones.Count && i < _boneJointTransforms.Count; i++)
            {
                var wp = _boneWorldMatrices[i].Origin;
                _boneJointTransforms[i].OffsetX = wp.X;
                _boneJointTransforms[i].OffsetY = wp.Y;
                _boneJointTransforms[i].OffsetZ = wp.Z;
            }

            _update_bone_lines();
        }

        // メッシュのCPUスキニング（各頂点をボーン変形行列に基づいて並列計算・更新）
        private void _update_mesh_skinning(float frame = -1.0f)
        {
            if (_currentPmxModel == null || _subMeshes.Count == 0) return;

            int boneCount = _currentPmxModel.Bones.Count;
            if (_boneWorldMatrices.Count < boneCount) return;

            // 各ボーンのスキニング変換行列を作成
            var skinningMatrices = new Matrix[boneCount];
            for (int b = 0; b < boneCount; b++)
            {
                var bone = _currentPmxModel.Bones[b];
                Matrix toOrigin = Matrix.Translation(-bone.Position[0], -bone.Position[1], -bone.Position[2]);
                skinningMatrices[b] = toOrigin * _boneWorldMatrices[b];
            }

            var origVertices = _currentPmxModel.VertexPositions;
            var skinnings = _currentPmxModel.VertexSkinnings;
            int vertexCount = origVertices.Count;

            // 現在フレームのモーフ変形（ブレンドシェイプ）量を算出
            float targetFrame = frame >= 0.0f ? frame : _currentFrame;
            float[]? deltaX = null;
            float[]? deltaY = null;
            float[]? deltaZ = null;

            if (_currentVmdData != null && _currentPmxModel.Morphs.Count > 0)
            {
                var morphWeights = new float[_currentPmxModel.Morphs.Count];
                bool hasActiveMorph = false;

                for (int m = 0; m < _currentPmxModel.Morphs.Count; m++)
                {
                    var morph = _currentPmxModel.Morphs[m];
                    float w = _currentVmdData.SampleMorph(morph.Name, targetFrame);
                    morphWeights[m] = w;
                    if (w > 0.0001f) hasActiveMorph = true;
                }

                if (hasActiveMorph)
                {
                    // グループモーフの展開
                    for (int m = 0; m < _currentPmxModel.Morphs.Count; m++)
                    {
                        var morph = _currentPmxModel.Morphs[m];
                        float w = morphWeights[m];
                        if (morph.MorphType == 0 && w > 0.0001f)
                        {
                            foreach (var g in morph.GroupOffsets)
                            {
                                if (g.MorphIndex >= 0 && g.MorphIndex < morphWeights.Length)
                                {
                                    morphWeights[g.MorphIndex] += w * g.Rate;
                                }
                            }
                        }
                    }

                    deltaX = new float[vertexCount];
                    deltaY = new float[vertexCount];
                    deltaZ = new float[vertexCount];

                    // 頂点モーフの変位量を合算
                    for (int m = 0; m < _currentPmxModel.Morphs.Count; m++)
                    {
                        var morph = _currentPmxModel.Morphs[m];
                        float w = morphWeights[m];
                        if (morph.MorphType == 1 && w > 0.0001f)
                        {
                            foreach (var vo in morph.VertexOffsets)
                            {
                                if (vo.VertexIndex >= 0 && vo.VertexIndex < vertexCount)
                                {
                                    deltaX[vo.VertexIndex] += vo.Offset[0] * w;
                                    deltaY[vo.VertexIndex] += vo.Offset[1] * w;
                                    deltaZ[vo.VertexIndex] += vo.Offset[2] * w;
                                }
                            }
                        }
                    }
                }
            }

            // 全グローバル頂点をマルチコアで並列スキニング計算
            var globalPositions = new Point3D[vertexCount];
            Parallel.For(0, vertexCount, i =>
            {
                var v = origVertices[i];
                float vx = deltaX != null ? v[0] + deltaX[i] : v[0];
                float vy = deltaY != null ? v[1] + deltaY[i] : v[1];
                float vz = deltaZ != null ? v[2] + deltaZ[i] : v[2];

                if (i >= skinnings.Count || skinnings[i].BoneIndices.Length == 0)
                {
                    globalPositions[i] = new Point3D(vx, vy, vz);
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
                    float tx = (vx * mat.M11) + (vy * mat.M21) + (vz * mat.M31) + mat.M41;
                    float ty = (vx * mat.M12) + (vy * mat.M22) + (vz * mat.M32) + mat.M42;
                    float tz = (vx * mat.M13) + (vy * mat.M23) + (vz * mat.M33) + mat.M43;

                    outX += tx * w;
                    outY += ty * w;
                    outZ += tz * w;
                }
                globalPositions[i] = new Point3D(outX, outY, outZ);
            });

            // 各サブメッシュへ一括反映
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

        // 行ベクトル規約の回転行列から四元数(クォータニオン)を算出
        private static (float X, float Y, float Z, float W) MatrixToQuaternion(Matrix m)
        {
            float tr = m.M11 + m.M22 + m.M33;
            float qx, qy, qz, qw;

            if (tr > 0.0f)
            {
                float s = MathF.Sqrt(tr + 1.0f);
                qw = s * 0.5f;
                s = 0.5f / s;
                qx = (m.M23 - m.M32) * s;
                qy = (m.M31 - m.M13) * s;
                qz = (m.M12 - m.M21) * s;
            }
            else if (m.M11 >= m.M22 && m.M11 >= m.M33)
            {
                float s = MathF.Sqrt(1.0f + m.M11 - m.M22 - m.M33);
                qx = s * 0.5f;
                s = 0.5f / s;
                qy = (m.M12 + m.M21) * s;
                qz = (m.M31 + m.M13) * s;
                qw = (m.M23 - m.M32) * s;
            }
            else if (m.M22 > m.M33)
            {
                float s = MathF.Sqrt(1.0f + m.M22 - m.M11 - m.M33);
                qy = s * 0.5f;
                s = 0.5f / s;
                qx = (m.M12 + m.M21) * s;
                qz = (m.M23 + m.M32) * s;
                qw = (m.M31 - m.M13) * s;
            }
            else
            {
                float s = MathF.Sqrt(1.0f + m.M33 - m.M11 - m.M22);
                qz = s * 0.5f;
                s = 0.5f / s;
                qx = (m.M31 + m.M13) * s;
                qy = (m.M23 + m.M32) * s;
                qw = (m.M12 - m.M21) * s;
            }

            float len = MathF.Sqrt(qx * qx + qy * qy + qz * qz + qw * qw);
            if (len > 1e-6f)
            {
                float invLen = 1.0f / len;
                qx *= invLen;
                qy *= invLen;
                qz *= invLen;
                qw *= invLen;
            }
            else
            {
                qx = 0.0f; qy = 0.0f; qz = 0.0f; qw = 1.0f;
            }

            return (qx, qy, qz, qw);
        }

        // シミュレーション結果をベイクしてMaya戻し用VMDを出力 (MMM物理書き込み互換)
        private async void BtnBake_Click(object sender, RoutedEventArgs e)
        {
            if (_currentPmxModel == null)
            {
                MessageBox.Show("PMXモデルを指定してください。", "警告", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            if (_currentVmdData == null)
            {
                MessageBox.Show("VMDモーションファイルを指定してください。", "警告", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            // 二重実行防止
            BtnBake.IsEnabled = false;
            BtnPlay.IsEnabled = false;
            BtnPause.IsEnabled = false;

            try
            {
                TxtStatus.Text = "物理シミュレーションをベイク準備中...";
                _playTimer.Stop();

                // 物理ワールドを初期リセット
                _physicsEngine.ResetWorld(_currentPmxModel);

                // フレーム0のボーン姿勢に剛体を確実にスナップ初期化（初期Tポーズからの跳ねや揺れを防止）
                _evaluate_fk_and_update(0, resetAllBodies: true);

                int totalFrames = _currentVmdData.MaxFrame + 1;
                var bones = _currentPmxModel.Bones;
                int n = bones.Count;

                // 物理演算対象（剛体モードが物理演算または物理＋ボーン位置合わせ）のボーンおよび子ボーンを抽出
                var physicsBoneIndices = new HashSet<int>();
                for (int i = 0; i < _currentPmxModel.Rigidbodies.Count; i++)
                {
                    var rb = _currentPmxModel.Rigidbodies[i];
                    if (rb.PhysicsMode != PmxPhysicsMode.FollowBone && rb.BoneIndex >= 0 && rb.BoneIndex < n)
                    {
                        physicsBoneIndices.Add(rb.BoneIndex);
                    }
                }

                // 物理剛体を持たないが、物理親ボーンに追従する子ボーンも対象に加える
                void AddChildren(int p)
                {
                    for (int c = 0; c < n; c++)
                    {
                        if (bones[c].ParentIndex == p && !physicsBoneIndices.Contains(c))
                        {
                            physicsBoneIndices.Add(c);
                            AddChildren(c);
                        }
                    }
                }
                foreach (int idx in physicsBoneIndices.ToArray())
                {
                    AddChildren(idx);
                }

                // 出力用の新しいVMDモーションデータ
                var bakedVmd = new VmdMotionData
                {
                    ModelName = !string.IsNullOrEmpty(_currentPmxModel.ModelName) ? _currentPmxModel.ModelName : _currentVmdData.ModelName,
                    MaxFrame = _currentVmdData.MaxFrame
                };

                // 非物理ボーンの元トラックをコピー（元キーフレームと補間曲線を維持）
                var physicsBoneNames = new HashSet<string>(physicsBoneIndices.Select(idx => bones[idx].Name));
                foreach (var (boneName, track) in _currentVmdData.BoneTracks)
                {
                    if (!physicsBoneNames.Contains(boneName))
                    {
                        bakedVmd.BoneTracks[boneName] = new List<VmdBoneKeyframe>(track);
                    }
                }

                // 表情モーフおよびIKトラックをそのままコピー
                foreach (var (morphName, track) in _currentVmdData.MorphTracks)
                {
                    bakedVmd.MorphTracks[morphName] = new List<VmdMorphKeyframe>(track);
                }
                foreach (var (ikName, track) in _currentVmdData.IkTracks)
                {
                    bakedVmd.IkTracks[ikName] = new List<(int, bool)>(track);
                }

                // 物理ボーン用の新規トラックを初期化
                foreach (int idx in physicsBoneIndices)
                {
                    string boneName = bones[idx].Name;
                    bakedVmd.BoneTracks[boneName] = new List<VmdBoneKeyframe>();
                }

                var sw = System.Diagnostics.Stopwatch.StartNew();

                // 全フレーム一括シミュレーション実行（画面更新とモーション再生を行いながら進捗を記録）
                for (int f = 0; f < totalFrames; f++)
                {
                    _currentFrame = f;
                    _evaluate_fk_and_update(f);
                    _physicsEngine.StepSimulation(1.0f / 30.0f, 10, 1.0f / 60.0f);
                    _apply_physics_to_bones();

                    // ビューポートの3D表示を同期（モーション再生）
                    _sync_bone_visuals_after_physics();
                    _update_rigidbody_visuals();
                    _update_joint_visuals();
                    _update_mesh_skinning(f);

                    // 各物理ボーンのローカル姿勢（移動・回転）を逆算してキーフレーム生成
                    foreach (int i in physicsBoneIndices)
                    {
                        var bone = bones[i];
                        int p = bone.ParentIndex;
                        Matrix mBone = _boneWorldMatrices[i];
                        Matrix mLocal;

                        if (p >= 0 && p < n && p != i)
                        {
                            Matrix mParent = _boneWorldMatrices[p];
                            Matrix invParent = Matrix.Invert(mParent);
                            mLocal = mBone * invParent;
                        }
                        else
                        {
                            mLocal = mBone;
                        }

                        // クォータニオン回転の算出
                        var (qx, qy, qz, qw) = MatrixToQuaternion(mLocal);

                        // 平行移動量の算出 (MMD仕様: 移動フラグ 0x0002 を持たない回転専用ボーンは移動量を0に固定)
                        bool canTranslate = (bone.Flags & 0x0002) != 0;
                        float tx = 0.0f;
                        float ty = 0.0f;
                        float tz = 0.0f;

                        if (canTranslate)
                        {
                            float ox = bone.Position[0];
                            float oy = bone.Position[1];
                            float oz = bone.Position[2];
                            if (p >= 0 && p < n && p != i)
                            {
                                ox -= bones[p].Position[0];
                                oy -= bones[p].Position[1];
                                oz -= bones[p].Position[2];
                            }

                            tx = mLocal.Origin.X - ox;
                            ty = mLocal.Origin.Y - oy;
                            tz = mLocal.Origin.Z - oz;
                        }

                        bakedVmd.BoneTracks[bone.Name].Add(new VmdBoneKeyframe
                        {
                            Frame = f,
                            Tx = tx,
                            Ty = ty,
                            Tz = tz,
                            Qx = qx,
                            Qy = qy,
                            Qz = qz,
                            Qw = qw
                        });
                    }

                    // 進捗情報と残り時間の算出
                    int processed = f + 1;
                    int remaining = totalFrames - processed;
                    var elapsed = sw.Elapsed;
                    double msPerFrame = elapsed.TotalMilliseconds / processed;
                    var estRemaining = TimeSpan.FromMilliseconds(msPerFrame * remaining);
                    float percent = (float)processed / totalFrames * 100.0f;

                    SliderTimeline.Value = Math.Clamp(f, SliderTimeline.Minimum, SliderTimeline.Maximum);
                    TxtFrameInfo.Text = $"フレーム: {processed} / {totalFrames} (ベイク中)";
                    TxtStatus.Text = $"物理ベイク中...\n進捗: {processed} / {totalFrames} ({percent:F1}%)\n経過: {elapsed:mm\\:ss} | 残り: {estRemaining:mm\\:ss}";

                    // UIレンダリングを実行させ、応答なしを防止
                    await System.Windows.Threading.Dispatcher.Yield(System.Windows.Threading.DispatcherPriority.Background);
                }

                // 元のVMDフォルダに出力
                string vmdPath = TxtVmdPath.Text;
                string vmdDir = Path.GetDirectoryName(vmdPath) ?? Directory.GetCurrentDirectory();
                string vmdBaseName = Path.GetFileNameWithoutExtension(vmdPath);
                string outPath = Path.Combine(vmdDir, $"{vmdBaseName}_physics_baked.vmd");

                VmdLoader.SaveVmd(outPath, bakedVmd);

                TxtStatus.Text = $"ベイク完了！\n・出力先: {Path.GetFileName(outPath)}\n・物理ボーン: {physicsBoneIndices.Count} 本 ({totalFrames} フレーム)\n・所要時間: {sw.Elapsed:mm\\:ss}";
                MessageBox.Show(
                    $"物理演算のベイク（VMD出力）が完了しました！\n\n出力先:\n{outPath}\n\nMayaの「物理演算GUI」タブで「最新ベイクを自動検出」またはこのVMDを指定して「物理ベイク済みモーション読込」を実行してください。",
                    "ベイク完了 (MMM互換)",
                    MessageBoxButton.OK,
                    MessageBoxImage.Information
                );
            }
            catch (Exception ex)
            {
                TxtStatus.Text = $"ベイクエラー: {ex.Message}";
                MessageBox.Show($"ベイク処理中にエラーが発生しました:\n{ex.Message}", "エラー", MessageBoxButton.OK, MessageBoxImage.Error);
            }
            finally
            {
                BtnBake.IsEnabled = true;
                BtnPlay.IsEnabled = true;
                BtnPause.IsEnabled = true;
            }
        }

        // テクスチャ画像ファイルの読み込みヘルパー
        private ImageBrush? LoadTexture(string pmxPath, string relativeTexturePath, out bool hasAlpha)
        {
            hasAlpha = false;
            if (string.IsNullOrWhiteSpace(relativeTexturePath)) return null;

            // アスタリスク区切りの場合、通常テクスチャ部分のみ抽出
            if (relativeTexturePath.Contains('*'))
            {
                relativeTexturePath = relativeTexturePath.Split('*')[0].Trim();
            }

            // スフィアマップ (*.sph, *.spa) は除外
            string ext = Path.GetExtension(relativeTexturePath).ToLowerInvariant();
            if (ext == ".sph" || ext == ".spa") return null;

            if (_textureCache.TryGetValue(relativeTexturePath, out var cached))
            {
                hasAlpha = cached.HasAlpha;
                return cached.Brush;
            }

            try
            {
                string pmxDir = Path.GetDirectoryName(pmxPath) ?? "";
                string normalized = relativeTexturePath.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
                string fullPath = Path.Combine(pmxDir, normalized);

                if (!File.Exists(fullPath))
                {
                    // ファイル名のみで同ディレクトリ内を検索
                    string fileName = Path.GetFileName(normalized);
                    string altPath = Path.Combine(pmxDir, fileName);
                    if (File.Exists(altPath))
                    {
                        fullPath = altPath;
                    }
                    else
                    {
                        // 拡張子を変更して再検索 (.tga -> .png / .bmp / .jpg)
                        string baseNameNoExt = Path.GetFileNameWithoutExtension(normalized);
                        string[] testExts = { ".png", ".bmp", ".jpg" };
                        bool found = false;
                        foreach (var te in testExts)
                        {
                            string testP = Path.Combine(pmxDir, baseNameNoExt + te);
                            if (File.Exists(testP)) { fullPath = testP; found = true; break; }
                        }
                        if (!found) return null;
                    }
                }

                var bitmap = new System.Windows.Media.Imaging.BitmapImage();
                bitmap.BeginInit();
                bitmap.UriSource = new Uri(fullPath, UriKind.Absolute);
                bitmap.CacheOption = System.Windows.Media.Imaging.BitmapCacheOption.OnLoad;
                bitmap.EndInit();
                bitmap.Freeze();

                // 透過ピクセル（アルファ値）の判定
                if (bitmap.Format.BitsPerPixel == 32)
                {
                    try
                    {
                        var converted = new System.Windows.Media.Imaging.FormatConvertedBitmap(bitmap, PixelFormats.Bgra32, null, 0);
                        int stride = (converted.PixelWidth * 32 + 7) / 8;
                        byte[] pixels = new byte[stride * converted.PixelHeight];
                        converted.CopyPixels(pixels, stride, 0);
                        for (int i = 3; i < pixels.Length; i += 4)
                        {
                            if (pixels[i] < 250)
                            {
                                hasAlpha = true;
                                break;
                            }
                        }
                    }
                    catch
                    {
                        if (ext == ".png") hasAlpha = true;
                    }
                }

                var brush = new ImageBrush(bitmap)
                {
                    TileMode = TileMode.Tile,
                    ViewportUnits = BrushMappingMode.Absolute,
                    Viewport = new Rect(0, 0, 1, 1)
                };
                brush.Freeze();
                _textureCache[relativeTexturePath] = (brush, hasAlpha);
                return brush;
            }
            catch
            {
                return null;
            }
        }

        protected override void OnClosed(EventArgs e)
        {
            _playTimer.Stop();
            _alwaysPhysicsTimer.Stop();
            _physicsEngine.Dispose();
            base.OnClosed(e);
        }
    }
}
