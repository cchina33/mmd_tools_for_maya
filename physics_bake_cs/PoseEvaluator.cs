using System;
using System.Collections.Generic;
using System.Linq;
using BulletSharp.Math;
using Matrix = BulletSharp.Math.Matrix;
using MmdPhysicsBridge;

namespace MmdPhysicsViewer
{
    // 各ボーンのFK・付与親・足IKおよび物理結果の評価とクォータニオン逆算を行うクラス
    public class PoseEvaluator
    {
        private readonly PmxModelData _pmx;
        private readonly VmdMotionData _vmd;
        private readonly PhysicsSimulationEngine _physics;

        private readonly List<Matrix> _boneWorldMatrices;
        private readonly List<Matrix> _cachedLocalMatrices;
        private readonly List<int>[] _children;
        private readonly HashSet<int> _physicsBoneIndices;

        public IReadOnlyList<Matrix> BoneWorldMatrices => _boneWorldMatrices;
        public IReadOnlySet<int> PhysicsBoneIndices => _physicsBoneIndices;

        public PoseEvaluator(PmxModelData pmx, VmdMotionData vmd, PhysicsSimulationEngine physics)
        {
            _pmx = pmx;
            _vmd = vmd;
            _physics = physics;

            int n = _pmx.Bones.Count;
            _boneWorldMatrices = new List<Matrix>(n);
            _cachedLocalMatrices = new List<Matrix>(n);
            _children = new List<int>[n];

            for (int i = 0; i < n; i++)
            {
                _boneWorldMatrices.Add(Matrix.Identity);
                _cachedLocalMatrices.Add(Matrix.Identity);
                _children[i] = new List<int>();
            }

            for (int i = 0; i < n; i++)
            {
                int p = _pmx.Bones[i].ParentIndex;
                if (p >= 0 && p < n && p != i)
                {
                    _children[p].Add(i);
                }
            }

            // 物理剛体（物理演算または位置合わせモード）を持つボーンを抽出
            _physicsBoneIndices = new HashSet<int>();
            for (int i = 0; i < _pmx.Rigidbodies.Count; i++)
            {
                var rb = _pmx.Rigidbodies[i];
                if (rb.PhysicsMode != PmxPhysicsMode.FollowBone && rb.BoneIndex >= 0 && rb.BoneIndex < n)
                {
                    _physicsBoneIndices.Add(rb.BoneIndex);
                }
            }

            // 物理剛体を持たないが、物理親ボーンに追従する子ボーンも対象に追加
            void AddChildrenRecursive(int p)
            {
                for (int c = 0; c < n; c++)
                {
                    if (_pmx.Bones[c].ParentIndex == p && !_physicsBoneIndices.Contains(c))
                    {
                        _physicsBoneIndices.Add(c);
                        AddChildrenRecursive(c);
                    }
                }
            }

            foreach (int idx in _physicsBoneIndices.ToArray())
            {
                AddChildrenRecursive(idx);
            }
        }

        // 指定フレームのFK・IK姿勢を計算し、物理剛体へ同期
        public void EvaluateFkAndSyncBodies(float frame, bool resetAllBodies = false)
        {
            var bones = _pmx.Bones;
            int n = bones.Count;

            var boneWorldPositions = new Dictionary<string, float[]>();
            var boneWorldRotations = new Dictionary<string, Matrix>();

            var ownRot = new Matrix[n];
            var ownTrans = new Vector3[n];
            var localRot = new Matrix[n];
            var localTrans = new Vector3[n];
            var ikSolved = new bool[n];
            var localDone = new bool[n];
            var worldDone = new bool[n];

            for (int i = 0; i < n; i++)
            {
                var (trans, quat) = _vmd.SampleBone(bones[i].Name, frame);
                Matrix r = Matrix.RotationQuaternion(new BulletSharp.Math.Quaternion(quat[0], quat[1], quat[2], quat[3]));
                r.Origin = new Vector3(0, 0, 0);
                ownRot[i] = r;
                ownTrans[i] = new Vector3(trans[0], trans[1], trans[2]);
            }

            void ComputeLocal(int i)
            {
                if (localDone[i]) return;
                localDone[i] = true;
                if (ikSolved[i]) return;

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

            void UpdateSubtree(int i)
            {
                int p = bones[i].ParentIndex;
                _boneWorldMatrices[i] = (p >= 0 && p < n && p != i)
                    ? LocalMatrix(i) * _boneWorldMatrices[p]
                    : LocalMatrix(i);
                foreach (int c in _children[i]) UpdateSubtree(c);
            }

            for (int i = 0; i < n; i++) ComputeLocal(i);
            for (int i = 0; i < n; i++) ComputeWorld(i);

            // 主足IKの計算 (VMDで有効な場合)
            for (int i = 0; i < n; i++)
            {
                var ikBone = bones[i];
                if (ikBone.Name != "左足ＩＫ" && ikBone.Name != "右足ＩＫ") continue;
                if (!_vmd.IsIkEnabled(ikBone.Name, frame)) continue;

                var ik = ikBone.IkData;
                if (ik == null || ik.Links.Count == 0) continue;
                int targetIdx = ik.TargetBoneIndex;
                if (targetIdx < 0 || targetIdx >= n) continue;

                Vector3 targetPos = _boneWorldMatrices[i].Origin;
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

                        Vector3 le = ToLocalDir(_boneWorldMatrices[li], effPos - linkPos);
                        Vector3 lt = ToLocalDir(_boneWorldMatrices[li], targetPos - linkPos);
                        if (le.LengthSquared < 1e-8f || lt.LengthSquared < 1e-8f) continue;

                        bool xOnly = link.HasLimit
                            && Math.Abs(link.MinAngle[1]) < 1e-4f && Math.Abs(link.MaxAngle[1]) < 1e-4f
                            && Math.Abs(link.MinAngle[2]) < 1e-4f && Math.Abs(link.MaxAngle[2]) < 1e-4f;

                        if (xOnly)
                        {
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
                            if (angle >= 1e-5f)
                            {
                                angle = Math.Min(angle, unitAngle);
                                Vector3 axis = Vector3.Cross(le, lt);
                                if (axis.LengthSquared >= 1e-10f)
                                {
                                    axis.Normalize();
                                    Matrix newRot = AxisAngle(axis, angle) * localRot[li];
                                    if (link.HasLimit)
                                    {
                                        newRot = ClampEuler(newRot, link.MinAngle, link.MaxAngle);
                                    }
                                    localRot[li] = newRot;
                                }
                            }
                        }

                        ikSolved[li] = true;
                        UpdateSubtree(li);
                    }

                    if ((_boneWorldMatrices[targetIdx].Origin - targetPos).LengthSquared < 1e-6f) break;
                }
            }

            Array.Clear(localDone);
            Array.Clear(worldDone);
            for (int i = 0; i < n; i++) ComputeLocal(i);
            for (int i = 0; i < n; i++) ComputeWorld(i);

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
            }

            if (resetAllBodies)
            {
                _physics.ResetBodiesToBones(boneWorldPositions, boneWorldRotations, bones);
            }
            else
            {
                _physics.UpdateKinematicBodies(boneWorldPositions, boneWorldRotations, bones);
            }
        }

        // 物理エンジンの計算結果をボーンへ書き戻す
        public void ApplyPhysicsToBones()
        {
            var bones = _pmx.Bones;
            int n = bones.Count;

            int[] driveMode = _physics.SyncPhysicsToBones(_boneWorldMatrices, bones);

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

        // 揺れものボーンのローカル回転クォータニオンを算出
        public Dictionary<string, float[]> ExtractPhysicsBoneRotations()
        {
            var result = new Dictionary<string, float[]>(_physicsBoneIndices.Count);
            var bones = _pmx.Bones;
            int n = bones.Count;

            foreach (int i in _physicsBoneIndices)
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

                var (qx, qy, qz, qw) = MatrixToQuaternion(mLocal);
                result[bone.Name] = new float[] { qx, qy, qz, qw };
            }

            return result;
        }

        public static (float X, float Y, float Z, float W) MatrixToQuaternion(Matrix m)
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

        private static Matrix AxisAngle(Vector3 axis, float angle)
        {
            float c = MathF.Cos(angle), s = MathF.Sin(angle), t = 1.0f - c;
            float x = axis.X, y = axis.Y, z = axis.Z;
            return MakeRot(
                c + x * x * t, x * y * t + z * s, x * z * t - y * s,
                x * y * t - z * s, c + y * y * t, y * z * t + x * s,
                x * z * t + y * s, y * z * t - x * s, c + z * z * t);
        }

        private static Vector3 ToLocalDir(Matrix w, Vector3 v)
        {
            return new Vector3(
                v.X * w.M11 + v.Y * w.M12 + v.Z * w.M13,
                v.X * w.M21 + v.Y * w.M22 + v.Z * w.M23,
                v.X * w.M31 + v.Y * w.M32 + v.Z * w.M33);
        }

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
    }
}
