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

        private RigidBody? _groundBody;
        private CollisionShape? _groundShape;

        // ジョイント表示用 (剔体Aと、剔体Aから見たジョイントのローカル姿勢)
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
            _broadphase = new DbvtBroadphase();
            _solver = new SequentialImpulseConstraintSolver();

            _world = new DiscreteDynamicsWorld(_dispatcher, _broadphase, _solver, _collisionConfig);
            _world.Gravity = new Vector3(0, -98.0f, 0); // MMDの長さ単位に合わせた重力 (9.8 x 10)

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

                // PMXモデルの過剰な減衰設定による回転・並進の停止を防止するためダンピングを適正化
                float linearDamp = Math.Min(rbData.PositionDamping, 0.85f);
                float angularDamp = Math.Min(rbData.RotationDamping, 0.85f);

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

                // 高速移動時の突き抜け防止のためCCD (連続衝突判定) を設定
                if (rbData.PhysicsMode != PmxPhysicsMode.FollowBone && mass > 0.0f)
                {
                    float minRadius = Math.Max(0.05f, rbData.Size[0]);
                    body.CcdMotionThreshold = minRadius * 0.5f;
                    body.CcdSweptSphereRadius = minRadius * 0.2f;
                }

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

                _world.AddConstraint(constraint, true);
                _constraints.Add(constraint);
                _jointFrames.Add((bodyA, frameInA));
            }
        }

        // 追従剛体（体や足）の位置をMayaモーションに基づいて更新
        public void UpdateKinematicBodies(Dictionary<string, float[]> boneWorldPositions, Dictionary<string, Matrix> boneWorldRotations, List<PmxBone> bones)
        {
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
                    body.MotionState.WorldTransform = worldMat;
                }
            }
        }

        // すべての剛体を現在のボーン姿勢に合わせて再配置・初期化（物理剛体も瞬時にボーン姿勢へスナップ）
        public void ResetBodiesToBones(Dictionary<string, float[]> boneWorldPositions, Dictionary<string, Matrix> boneWorldRotations, List<PmxBone> bones)
        {
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

        // 物理シミュレーションを1ステップ進める
        public void StepSimulation(float timeStep, int maxSubSteps = 10, float fixedTimeStep = 1.0f / 60.0f)
        {
            _world?.StepSimulation(timeStep, maxSubSteps, fixedTimeStep);
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
