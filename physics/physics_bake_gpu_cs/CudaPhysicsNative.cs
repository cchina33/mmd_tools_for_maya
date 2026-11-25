using System;
using System.Runtime.InteropServices;

namespace PhysicsSimulationBakeViewer
{
    // C++ / CUDA ネイティブ DLL (mmd_physics_cuda.dll) との P/Invoke 相互運用クラス
    public static class CudaPhysicsNative
    {
        private const string DllName = "mmd_physics_cuda";

        [StructLayout(LayoutKind.Sequential, Pack = 4, CharSet = CharSet.Ansi)]
        public struct GpuDeviceInfo
        {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
            public string DeviceName;
            public int MajorCapability;
            public int MinorCapability;
            public int MultiProcessorCount;
            public int CudaCores;
            public nuint TotalMemoryBytes;
            public nuint FreeMemoryBytes;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct GpuRigidBodyData
        {
            public int BoneIndex;
            public int CollisionGroup;
            public int CollisionMask;
            public int ShapeType; // 0: 球, 1: 箱, 2: カプセル
            public float SizeX, SizeY, SizeZ;
            public float PosX, PosY, PosZ;
            public float RotX, RotY, RotZ;
            public float Mass;
            public float LinearDamping;
            public float AngularDamping;
            public float Restitution;
            public float Friction;
            public int PhysicsMode;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct GpuJointData
        {
            public int BodyA;
            public int BodyB;
            public float PosX, PosY, PosZ;
            public float RotX, RotY, RotZ;
            public float LinearLowerLimitX, LinearLowerLimitY, LinearLowerLimitZ;
            public float LinearUpperLimitX, LinearUpperLimitY, LinearUpperLimitZ;
            public float AngularLowerLimitX, AngularLowerLimitY, AngularLowerLimitZ;
            public float AngularUpperLimitX, AngularUpperLimitY, AngularUpperLimitZ;
            public float SpringLinearStiffnessX, SpringLinearStiffnessY, SpringLinearStiffnessZ;
            public float SpringAngularStiffnessX, SpringAngularStiffnessY, SpringAngularStiffnessZ;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct GpuRigidBodyTransform
        {
            public float PosX, PosY, PosZ;
            public float RotX, RotY, RotZ, RotW;
            public float LinearVelX, LinearVelY, LinearVelZ;
            public float AngularVelX, AngularVelY, AngularVelZ;
        }

        // 頂点スキニング用初期データ構造体 (BDEF1 / BDEF2 / BDEF4 対応)
        [StructLayout(LayoutKind.Sequential, Pack = 4)]
        public struct GpuVertexSkinData
        {
            public float OrigPosX, OrigPosY, OrigPosZ;
            public int BoneIndex0, BoneIndex1, BoneIndex2, BoneIndex3;
            public float Weight0, Weight1, Weight2, Weight3;
        }

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_is_available();

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_get_device_info(out GpuDeviceInfo outInfo);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_initialize(int maxBodies, int maxJoints);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void cuda_physics_shutdown();

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_upload_bodies(GpuRigidBodyData[] bodies, int count);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_upload_joints(GpuJointData[] joints, int count);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_set_transforms(GpuRigidBodyTransform[] transforms, int count);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_get_transforms([Out] GpuRigidBodyTransform[] outTransforms, int count);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_reset_velocities();

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_physics_step_simulation(float timeStep, int maxSubSteps, float subStepHz);

        // GPU 頂点スキニング並列アクセラレータ API
        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_skinning_initialize(int vertexCount, GpuVertexSkinData[] vertices);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern int cuda_skinning_compute(float[] boneMatrices, int boneCount, [Out] float[] outPositions);

        [DllImport(DllName, CallingConvention = CallingConvention.Cdecl)]
        public static extern void cuda_skinning_shutdown();

        // 防御的な GPU 診断ヘルパー
        public static bool TryGetGpuInfo(out GpuDeviceInfo info)
        {
            info = default;
            try
            {
                if (cuda_physics_is_available() != 0)
                {
                    return cuda_physics_get_device_info(out info) != 0;
                }
            }
            catch
            {
                // ネイティブ DLL 未配置または非対応環境時の防御的フォールバック
            }
            return false;
        }
    }
}

