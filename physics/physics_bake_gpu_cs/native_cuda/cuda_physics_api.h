#pragma once

#ifdef _WIN32
  #define CUDA_PHYSICS_API extern "C" __declspec(dllexport)
#else
  #define CUDA_PHYSICS_API extern "C"
#endif

// GPU デバイス情報構造体 (C# とのアライメント整合)
#pragma pack(push, 4)
struct GpuDeviceInfo {
    char deviceName[256];
    int majorCapability;
    int minorCapability;
    int multiProcessorCount;
    int cudaCores;
    size_t totalMemoryBytes;
    size_t freeMemoryBytes;
};

// 剛体パラメータ構造体 (MMD Bullet 準拠)
struct GpuRigidBodyData {
    int boneIndex;
    int collisionGroup;
    int collisionMask;
    int shapeType; // 0: 球, 1: 箱, 2: カプセル
    float size[3];
    float position[3];
    float rotation[3];
    float mass;
    float linearDamping;
    float angularDamping;
    float restitution;
    float friction;
    int physicsMode; // 0: ボーン追従, 1: 物理演算, 2: 物理＋位置吸着
};

// スプリング拘束パラメータ構造体 (MMD 6DoF 準拠)
struct GpuJointData {
    int bodyA;
    int bodyB;
    float position[3];
    float rotation[3];
    float linearLowerLimit[3];
    float linearUpperLimit[3];
    float angularLowerLimit[3];
    float angularUpperLimit[3];
    float springLinearStiffness[3];
    float springAngularStiffness[3];
};

// 剛体動的トランスフォーム構造体 (位置、四元数回転、速度、角速度)
struct GpuRigidBodyTransform {
    float posX, posY, posZ;
    float rotX, rotY, rotZ, rotW;
    float linearVelX, linearVelY, linearVelZ;
    float angularVelX, angularVelY, angularVelZ;
};

// 頂点スキニング用初期データ構造体 (BDEF1 / BDEF2 / BDEF4 対応)
struct GpuVertexSkinData {
    float origPos[3];
    int boneIndices[4];
    float boneWeights[4];
};
#pragma pack(pop)

// C# から呼び出すエクスポート API 群
CUDA_PHYSICS_API int cuda_physics_is_available();
CUDA_PHYSICS_API int cuda_physics_get_device_info(GpuDeviceInfo* outInfo);
CUDA_PHYSICS_API int cuda_physics_initialize(int maxBodies, int maxJoints);
CUDA_PHYSICS_API void cuda_physics_shutdown();
CUDA_PHYSICS_API int cuda_physics_upload_bodies(const GpuRigidBodyData* bodies, int count);
CUDA_PHYSICS_API int cuda_physics_upload_joints(const GpuJointData* joints, int count);
CUDA_PHYSICS_API int cuda_physics_set_transforms(const GpuRigidBodyTransform* transforms, int count);
CUDA_PHYSICS_API int cuda_physics_get_transforms(GpuRigidBodyTransform* outTransforms, int count);
CUDA_PHYSICS_API int cuda_physics_reset_velocities();
CUDA_PHYSICS_API int cuda_physics_step_simulation(float timeStep, int maxSubSteps, float subStepHz);

// GPU 頂点スキニング並列アクセラレータ API
CUDA_PHYSICS_API int cuda_skinning_initialize(int vertexCount, const GpuVertexSkinData* vertices);
CUDA_PHYSICS_API int cuda_skinning_compute(const float* boneMatrices, int boneCount, float* outPositions);
CUDA_PHYSICS_API void cuda_skinning_shutdown();

