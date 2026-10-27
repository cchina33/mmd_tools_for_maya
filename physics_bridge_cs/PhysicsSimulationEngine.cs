using System;
using System.Collections.Generic;
using BulletSharp;
using BulletSharp.Math;

namespace MmdPhysicsBridge
{
    // PMXとBullet物理エンジンの連携管理クラス
    public class PhysicsSimulationEngine : IDisposable
    {
        private DefaultCollisionConfiguration? _collisionConfig;
        private CollisionDispatcher? _dispatcher;
        private BroadphaseInterface? _broadphase;
        private SequentialImpulseConstraintSolver? _solver;
        private DiscreteDynamicsWorld? _world;

        // 生成された剛体・拘束の保持
        private readonly List<RigidBody> _rigidBodies = new();
        private readonly List<TypedConstraint> _constraints = new();
        private readonly List<PmxRigidbody> _pmxRigidbodies = new();

        // 剛体とボーンの対応マップ
        public IReadOnlyList<RigidBody> RigidBodies => _rigidBodies;
        public IReadOnlyList<PmxRigidbody> PmxRigidbodies => _pmxRigidbodies;

        // 前フレームのKinematic剛体姿勢 (速度計算用)
        private readonly Dictionary<int, Matrix> _prevKinematicTransforms = new();

        // 物理シミュレーションの内部計算周波数 (デフォルト120Hz、貫通防止強化)
        public float SubstepHz { get; set; } = 120.0f;

#if BULLET_275
        public string EngineVersionName => "Bullet 2.75 (本家MMD仕様)";
#else
        public string EngineVersionName => "Bullet 2.83.7 (安定版仕様)";
#endif

        private RigidBody? _groundBody;
        private CollisionShape? _groundShape;

        // ジョイント表示用 (剛体Aと、剛体Aから見たジョイントのローカル姿勢)
        private readonly List<(RigidBody Body, Matrix FrameInA)> _jointFrames = new();
        public int JointCount => _jointFrames.Count;

        // ジョイントの現在のワールド姿勢を取得
        public Matrix GetJointTransform(int index)
        {
            if (index < 0 || index >= _jointFrames.Count) return Matrix.Identity;
            var (body, frameInA) = _jointFrames[index];
            return frameInA * body.MotionState.WorldTransform;
        }

        public void InitializeWorld()
        {
            Dispose();

            _collisionConfig = new DefaultCollisionConfiguration();
            _dispatcher = new CollisionDispatcher(_collisionConfig);
#if BULLET_275
            // MMD本家仕様: 32bit AxisSweep3 (範囲 -10000 〜 +10000, 最大ペア数 1,500,000)
            _broadphase = new AxisSweep3_32Bit(new Vector3(-10000.0f, -10000.0f, -10000.0f), new Vector3(10000.0f, 10000.0f, 10000.0f), 1500000);
#else
            _broadphase = new DbvtBroadphase();
#endif
            _solver = new SequentialImpulseConstraintSolver();

            _world = new DiscreteDynamicsWorld(_dispatcher, _broadphase, _solver, _collisionConfig);
            _world.Gravity = new Vector3(0, -98.0f, 0); // MMDの長さ単位に合わせた重力 (9.8 x 10)

            // ソルバー設定 (2.75 本家仕様 vs 2.83.7 安定版仕様)
            var solverInfo = _world.SolverInfo;
            // 決定論的解決によりランダムシャッフル起因の微小ジッター(震え)を抑制
            solverInfo.SolverMode &= ~SolverModes.RandomizeOrder;
#if BULLET_275
            // MMD本家 Bullet 2.75 仕様: 反復回数10、ERP 0.2
            solverInfo.NumIterations = 10;
            solverInfo.SplitImpulse = 0;
            solverInfo.Erp = 0.2f;
            solverInfo.Erp2 = 0.2f;

            // 地面判定コライダー (MMD本家仕様: Restitution = 0.88, グループ 0x8000)
            _groundShape = new StaticPlaneShape(Vector3.UnitY, 0.0f);
            var groundMotionState = new DefaultMotionState(Matrix.Identity);
            var groundRbInfo = new RigidBodyConstructionInfo(0.0f, groundMotionState, _groundShape, Vector3.Zero)
            {
                Friction = 0.5f,
                Restitution = 0.88f
            };
            _groundBody = new RigidBody(groundRbInfo);
            _world.AddRigidBody(_groundBody, unchecked((short)0x8000), -1);
#else
            // 改良版 Bullet 2.83.7 仕様 (高剛性・貫通防止重視)
            solverInfo.NumIterations = 25;
            solverInfo.SplitImpulse = 1;
            solverInfo.SplitImpulsePenetrationThreshold = -0.04f;
            solverInfo.SplitImpulseTurnErp = 0.1f;
            solverInfo.Erp = 0.2f;
            solverInfo.Erp2 = 0.2f;

            // 地面判定コライダー (Y=0 無限平面、Static)
            _groundShape = new StaticPlaneShape(Vector3.UnitY, 0.0f);
            var groundMotionState = new DefaultMotionState(Matrix.Identity);
            var groundRbInfo = new RigidBodyConstructionInfo(0.0f, groundMotionState, _groundShape, Vector3.Zero)
            {
                Friction = 0.5f,
                Restitution = 0.0f
            };
            _groundBody = new RigidBody(groundRbInfo);
            _world.AddRigidBody(_groundBody, -1, -1);
#endif
        }

        public void ResetWorld(PmxModelData pmxModel)
        {
            if (_world != null)
            {
                foreach (var constraint in _constraints)
                {
                    try { _world.RemoveConstraint(constraint); constraint.Dispose(); } catch { }
                }
                _constraints.Clear();
                _jointFrames.Clear();

                foreach (var body in _rigidBodies)
                {
                    try
                    {
                        _world.RemoveRigidBody(body);
                        body.MotionState?.Dispose();
                        body.CollisionShape?.Dispose();
                        body.Dispose();
                    }
                    catch { }
                }
                _rigidBodies.Clear();
                _pmxRigidbodies.Clear();
            }

            BuildPhysicsFromPmx(pmxModel);
        }

        public void BuildPhysicsFromPmx(PmxModelData pmxModel)
        {
            if (_world == null) InitializeWorld();
            if (_world == null) return;

            // 既存のリストを初期化
            _rigidBodies.Clear();
            _constraints.Clear();
            _jointFrames.Clear();
            _pmxRigidbodies.Clear();
            _pmxRigidbodies.AddRange(pmxModel.Rigidbodies);

            // 剛体の構築
            foreach (var rbData in pmxModel.Rigidbodies)
            {
                CollisionShape shape = rbData.Shape switch
                {
                    PmxColliderShape.Sphere => new SphereShape(rbData.Size[0]),
                    PmxColliderShape.Box => new BoxShape(rbData.Size[0], rbData.Size[1], rbData.Size[2]),
                    PmxColliderShape.Capsule => new CapsuleShape(rbData.Size[0], rbData.Size[1]),
                    _ => new SphereShape(rbData.Size[0])
                };

                // オイラー角(ラジアン)から回転行列を作成
                Matrix transform = Matrix.RotationYawPitchRoll(rbData.Rotation[1], rbData.Rotation[0], rbData.Rotation[2]);
                transform.Origin = new Vector3(rbData.Position[0], rbData.Position[1], rbData.Position[2]);

                float mass = (rbData.PhysicsMode == PmxPhysicsMode.FollowBone) ? 0.0f : rbData.Mass;
                Vector3 localInertia = Vector3.Zero;
                if (mass > 0.0f)
                {
                    shape.CalculateLocalInertia(mass, out localInertia);
                }

                var motionState = new DefaultMotionState(transform);

                // ダンピング設定 (PMX定義値を純粋にそのまま適用)
                float linearDamp = rbData.PositionDamping;
                float angularDamp = rbData.RotationDamping;

                var rbInfo = new RigidBodyConstructionInfo(mass, motionState, shape, localInertia)
                {
                    LinearDamping = linearDamp,
                    AngularDamping = angularDamp,
                    Restitution = rbData.Restitution,
                    Friction = rbData.Friction
                };

                var body = new RigidBody(rbInfo);

                // Kinematic (ボーン追従) フラグ設定
                if (rbData.PhysicsMode == PmxPhysicsMode.FollowBone)
                {
                    body.CollisionFlags |= CollisionFlags.KinematicObject;
                }

                // 動きが小さい剛体が自動休止して固まるのを防止
                body.ActivationState = ActivationState.DisableDeactivation;

                short group = (short)(1 << rbData.Group);
                // PMXバイナリのNonCollisionGroupは各グループとの衝突許可ビットフラグであるため、反転せずそのままBulletに渡す
                short mask = (short)(ushort)rbData.NonCollisionGroup;
                if (mask == 0)
                {
                    mask = 0x0001;
                }

#if BULLET_275
                // MMD本家 Bullet 2.75 仕様: CCDは設定せず、しなやかな本来の衝突判定を使用
#else
                // 高速移動時の突き抜け防止のためCCD (連続衝突判定) を設定
                float minRadius = Math.Max(0.05f, rbData.Size[0]);
                body.CcdMotionThreshold = minRadius * 0.25f;
                body.CcdSweptSphereRadius = minRadius * 0.5f;
                shape.Margin = 0.04f;
#endif

                _world.AddRigidBody(body, group, mask);
                _rigidBodies.Add(body);
            }

            // Joint (拘束) の構築
            foreach (var jointData in pmxModel.Joints)
            {
                if (jointData.RigidbodyAIndex < 0 || jointData.RigidbodyAIndex >= _rigidBodies.Count ||
                    jointData.RigidbodyBIndex < 0 || jointData.RigidbodyBIndex >= _rigidBodies.Count)
                {
                    continue;
                }

                var bodyA = _rigidBodies[jointData.RigidbodyAIndex];
                var bodyB = _rigidBodies[jointData.RigidbodyBIndex];

                Matrix jointTransform = Matrix.RotationYawPitchRoll(jointData.Rotation[1], jointData.Rotation[0], jointData.Rotation[2]);
                jointTransform.Origin = new Vector3(jointData.Position[0], jointData.Position[1], jointData.Position[2]);

                // 剛体AおよびBに対するローカル変換行列
                Matrix frameInA = jointTransform * Matrix.Invert(bodyA.MotionState.WorldTransform);
                Matrix frameInB = jointTransform * Matrix.Invert(bodyB.MotionState.WorldTransform);

                var constraint = new Generic6DofSpringConstraint(bodyA, bodyB, frameInA, frameInB, true);

                // 可動制限
                constraint.LinearLowerLimit = new Vector3(jointData.PositionLimitMin[0], jointData.PositionLimitMin[1], jointData.PositionLimitMin[2]);
                constraint.LinearUpperLimit = new Vector3(jointData.PositionLimitMax[0], jointData.PositionLimitMax[1], jointData.PositionLimitMax[2]);
                constraint.AngularLowerLimit = new Vector3(jointData.RotationLimitMin[0], jointData.RotationLimitMin[1], jointData.RotationLimitMin[2]);
                constraint.AngularUpperLimit = new Vector3(jointData.RotationLimitMax[0], jointData.RotationLimitMax[1], jointData.RotationLimitMax[2]);

                // スプリング定数 (並進・回転)
                for (int i = 0; i < 3; i++)
                {
                    float springPos = jointData.SpringPosition[i];
                    if (springPos > 0.0f)
                    {
                        constraint.EnableSpring(i, true);
                        constraint.SetStiffness(i, springPos);
                    }

                    float springRot = jointData.SpringRotation[i];
                    if (springRot > 0.0f)
                    {
                        constraint.EnableSpring(i + 3, true);
                        constraint.SetStiffness(i + 3, springRot);
                    }
                }

                // ジョイントで接続された剛体同士の衝突判定は除外(true)して重なり反発による爆発を防止
                _world.AddConstraint(constraint, true);
                _constraints.Add(constraint);
                _jointFrames.Add((bodyA, frameInA));
            }
        }

        // 追従剛体（体や足）の位置をMayaモーションに基づいて更新し、移動速度を付与して物理剛体（スカート等）の貫通を防止
        public void UpdateKinematicBodies(Dictionary<string, float[]> boneWorldPositions, Dictionary<string, Matrix> boneWorldRotations, List<PmxBone> bones, float dt = 1.0f / 30.0f)
        {
            float invDt = dt > 0.0f ? 1.0f / dt : 30.0f;

            for (int i = 0; i < _rigidBodies.Count; i++)
            {
                var body = _rigidBodies[i];
                var rbData = _pmxRigidbodies[i];

                if (rbData.PhysicsMode != PmxPhysicsMode.FollowBone) continue;
                if (rbData.BoneIndex < 0 || rbData.BoneIndex >= bones.Count) continue;

                var bone = bones[rbData.BoneIndex];
                if (boneWorldPositions.TryGetValue(bone.Name, out var pos))
                {
                    Matrix rotMat = Matrix.Identity;
                    if (boneWorldRotations.TryGetValue(bone.Name, out var rm))
                    {
                        rotMat = rm;
                    }

                    Matrix offsetMat = Matrix.RotationYawPitchRoll(rbData.Rotation[1], rbData.Rotation[0], rbData.Rotation[2]);
                    offsetMat.Origin = new Vector3(rbData.Position[0] - bone.Position[0], rbData.Position[1] - bone.Position[1], rbData.Position[2] - bone.Position[2]);

                    Matrix worldMat = offsetMat * rotMat;

                    // 移動差分から線速度を計算して付与 (Bulletの接触反発インパルスを正しく伝達)
                    if (_prevKinematicTransforms.TryGetValue(i, out var prevMat))
                    {
                        Vector3 deltaPos = worldMat.Origin - prevMat.Origin;
                        body.LinearVelocity = deltaPos * invDt;
                    }
                    _prevKinematicTransforms[i] = worldMat;

                    body.WorldTransform = worldMat;
                    body.MotionState.WorldTransform = worldMat;
                }
            }
        }

        // すべての剛体を現在のボーン姿勢に合わせて再配置・初期化（物理剛体も瞬時にボーン姿勢へスナップ）
        public void ResetBodiesToBones(Dictionary<string, float[]> boneWorldPositions, Dictionary<string, Matrix> boneWorldRotations, List<PmxBone> bones)
        {
            _prevKinematicTransforms.Clear();

            for (int i = 0; i < _rigidBodies.Count; i++)
            {
                var body = _rigidBodies[i];
                var rbData = _pmxRigidbodies[i];

                if (rbData.BoneIndex < 0 || rbData.BoneIndex >= bones.Count) continue;

                var bone = bones[rbData.BoneIndex];
                if (boneWorldPositions.TryGetValue(bone.Name, out var pos))
                {
                    Matrix rotMat = Matrix.Identity;
                    if (boneWorldRotations.TryGetValue(bone.Name, out var rm))
                    {
                        rotMat = rm;
                    }

                    Matrix offsetMat = Matrix.RotationYawPitchRoll(rbData.Rotation[1], rbData.Rotation[0], rbData.Rotation[2]);
                    offsetMat.Origin = new Vector3(rbData.Position[0] - bone.Position[0], rbData.Position[1] - bone.Position[1], rbData.Position[2] - bone.Position[2]);

                    Matrix worldMat = offsetMat * rotMat;
                    body.WorldTransform = worldMat;
                    body.MotionState.WorldTransform = worldMat;
                    body.LinearVelocity = Vector3.Zero;
                    body.AngularVelocity = Vector3.Zero;
                    body.ClearForces();
                }
            }
        }

        // 物理シミュレーションを1ステップ進める (デフォルト120Hzサブステップで高速移動時の貫通を大幅抑制)
        public void StepSimulation(float timeStep, int maxSubSteps = 16, float fixedTimeStep = 1.0f / 120.0f)
        {
            float actualStep = fixedTimeStep > 0.0f ? fixedTimeStep : (1.0f / SubstepHz);
            int actualSubSteps = maxSubSteps > 0 ? maxSubSteps : (int)Math.Ceiling(timeStep / actualStep) + 2;
            _world?.StepSimulation(timeStep, actualSubSteps, actualStep);
        }

        // 物理剛体の現在のワールド位置を取得
        public Vector3 GetBodyPosition(int index)
        {
            if (index < 0 || index >= _rigidBodies.Count) return Vector3.Zero;
            return _rigidBodies[index].MotionState.WorldTransform.Origin;
        }

        // 物理剛体の現在のワールド姿勢行列を取得
        public Matrix GetBodyTransform(int index)
        {
            if (index < 0 || index >= _rigidBodies.Count) return Matrix.Identity;
            return _rigidBodies[index].MotionState.WorldTransform;
        }

#if BULLET_275
        // MMD本家仕様: 動的剛体をFKボーン位置へ再配置し速度をゼロクリア (Settle Reseat)
        public void ReseatDynamicBodies(Dictionary<string, float[]> bonePositions, Dictionary<string, Matrix> boneRotations, List<PmxBone> bones)
        {
            for (int i = 0; i < _rigidBodies.Count && i < _pmxRigidbodies.Count; i++)
            {
                var rbData = _pmxRigidbodies[i];
                if (rbData.PhysicsMode == PmxPhysicsMode.FollowBone) continue;
                if (rbData.BoneIndex < 0 || rbData.BoneIndex >= bones.Count) continue;

                var bone = bones[rbData.BoneIndex];
                if (!bonePositions.TryGetValue(bone.Name, out var bPos) || !boneRotations.TryGetValue(bone.Name, out var bRot)) continue;

                var body = _rigidBodies[i];

                Matrix offsetMat = Matrix.RotationYawPitchRoll(rbData.Rotation[1], rbData.Rotation[0], rbData.Rotation[2]);
                offsetMat.Origin = new Vector3(rbData.Position[0] - bone.Position[0], rbData.Position[1] - bone.Position[1], rbData.Position[2] - bone.Position[2]);

                Matrix targetWorld = offsetMat * bRot;
                targetWorld.Origin += new Vector3(bPos[0], bPos[1], bPos[2]) - bRot.Origin;

                body.WorldTransform = targetWorld;
                body.LinearVelocity = Vector3.Zero;
                body.AngularVelocity = Vector3.Zero;
                body.InterpolationLinearVelocity = Vector3.Zero;
                body.InterpolationAngularVelocity = Vector3.Zero;
            }
        }
#endif

        // 物理剛体（スカート等）の計算結果を対応ボーンへ書き戻す
        // 戻り値: ボーンごとの駆動モード (0: 物理なし, 1: 物理で位置・回転, 2: 物理は回転のみで位置はボーンに合わせる)
        public int[] SyncPhysicsToBones(List<Matrix> boneWorldMatrices, List<PmxBone> bones)
        {
            var driveMode = new int[bones.Count];

            for (int i = 0; i < _rigidBodies.Count && i < _pmxRigidbodies.Count; i++)
            {
                var rbData = _pmxRigidbodies[i];
                if (rbData.PhysicsMode == PmxPhysicsMode.FollowBone) continue;
                if (rbData.BoneIndex < 0 || rbData.BoneIndex >= boneWorldMatrices.Count || rbData.BoneIndex >= bones.Count) continue;

                var body = _rigidBodies[i];
                var rbWorld = body.MotionState.WorldTransform;
                var bone = bones[rbData.BoneIndex];

                // 剛体の初期ローカル姿勢
                Matrix offsetMat = Matrix.RotationYawPitchRoll(rbData.Rotation[1], rbData.Rotation[0], rbData.Rotation[2]);
                offsetMat.Origin = new Vector3(rbData.Position[0] - bone.Position[0], rbData.Position[1] - bone.Position[1], rbData.Position[2] - bone.Position[2]);

                // boneWorld = Invert(offsetMat) * rbWorld
                Matrix invOffset = Matrix.Invert(offsetMat);
                Matrix calcWorld = invOffset * rbWorld;

                // 物理演算＋位置合わせモードの場合、位置はFKボーン位置を維持し回転のみ物理結果を適用
                if (rbData.PhysicsMode == PmxPhysicsMode.PhysicsWithBone)
                {
                    Vector3 origPos = boneWorldMatrices[rbData.BoneIndex].Origin;
                    calcWorld.Origin = origPos;
                }

                boneWorldMatrices[rbData.BoneIndex] = calcWorld;
                driveMode[rbData.BoneIndex] = rbData.PhysicsMode == PmxPhysicsMode.PhysicsWithBone ? 2 : 1;
            }

            return driveMode;
        }

        public void Dispose()
        {
            if (_world != null)
            {
                foreach (var constraint in _constraints)
                {
                    _world.RemoveConstraint(constraint);
                    constraint.Dispose();
                }
                _constraints.Clear();
                _jointFrames.Clear();
                _prevKinematicTransforms.Clear();

                foreach (var body in _rigidBodies)
                {
                    _world.RemoveRigidBody(body);
                    body.CollisionShape?.Dispose();
                    body.Dispose();
                }
                _rigidBodies.Clear();
                _pmxRigidbodies.Clear();

                if (_groundBody != null)
                {
                    _world.RemoveRigidBody(_groundBody);
                    _groundBody.Dispose();
                    _groundBody = null;
                }
                _groundShape?.Dispose();
                _groundShape = null;

                _world.Dispose();
                _world = null;
            }

            _solver?.Dispose();
            _broadphase?.Dispose();
            _dispatcher?.Dispose();
            _collisionConfig?.Dispose();
        }
    }
}
