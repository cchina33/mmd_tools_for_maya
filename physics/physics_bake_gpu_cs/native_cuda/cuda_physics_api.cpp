#include "cuda_physics_api.h"
#include <cstdio>
#include <cstring>
#include <cuda.h>
#include <cuda_runtime.h>
#include <nvrtc.h>
#include <string>
#include <vector>

// カーネルソースコード
static const char *g_cudaKernelSource = R"(
// 剛体パラメータ
struct KernelRigidBody {
    int boneIndex;
    int collisionGroup;
    int collisionMask;
    int shapeType;
    float size[3];
    float position[3];
    float rotation[3];
    float mass;
    float linearDamping;
    float angularDamping;
    float restitution;
    float friction;
    int physicsMode;
};

// 6DoF スプリング拘束パラメータ
struct KernelJoint {
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

// 剛体動的トランスフォーム
struct KernelTransform {
    float posX, posY, posZ;
    float rotX, rotY, rotZ, rotW;
    float linearVelX, linearVelY, linearVelZ;
    float angularVelX, angularVelY, angularVelZ;
};

// 剛体積分カーネル (重力・ダンピング・位置速度更新・地面衝突)
extern "C" __global__
void step_rigid_bodies_kernel(
    const KernelRigidBody* bodies,
    KernelTransform* transforms,
    float dt,
    float gravityY,
    int bodyCount
) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx >= bodyCount) return;

    const KernelRigidBody& b = bodies[idx];
    KernelTransform& t = transforms[idx];

    // physicsMode == 0 (ボーン追従) はキネマティックのため物理積分の対象外
    if (b.physicsMode == 0 || b.mass <= 0.0f) {
        t.linearVelX = 0.0f;
        t.linearVelY = 0.0f;
        t.linearVelZ = 0.0f;
        t.angularVelX = 0.0f;
        t.angularVelY = 0.0f;
        t.angularVelZ = 0.0f;
        return;
    }

    // 重力加速度の適用 (Y軸下向き)
    t.linearVelY += gravityY * dt;

    // 線形ダンピングの適用
    float linDamp = 1.0f - b.linearDamping * dt;
    if (linDamp < 0.0f) linDamp = 0.0f;
    t.linearVelX *= linDamp;
    t.linearVelY *= linDamp;
    t.linearVelZ *= linDamp;

    // 角ダンピングの適用
    float angDamp = 1.0f - b.angularDamping * dt;
    if (angDamp < 0.0f) angDamp = 0.0f;
    t.angularVelX *= angDamp;
    t.angularVelY *= angDamp;
    t.angularVelZ *= angDamp;

    // 位置の更新
    t.posX += t.linearVelX * dt;
    t.posY += t.linearVelY * dt;
    t.posZ += t.linearVelZ * dt;

    // 四元数回転の更新 (角速度による微小回転)
    float qx = t.rotX, qy = t.rotY, qz = t.rotZ, qw = t.rotW;
    float wx = t.angularVelX * 0.5f * dt;
    float wy = t.angularVelY * 0.5f * dt;
    float wz = t.angularVelZ * 0.5f * dt;

    float nqx = qx + (qw * wx + qy * wz - qz * wy);
    float nqy = qy + (qw * wy + qz * wx - qx * wz);
    float nqz = qz + (qw * wz + qx * wy - qy * wx);
    float nqw = qw - (qx * wx + qy * wy + qz * wz);

    // 正規化
    float normSq = nqx * nqx + nqy * nqy + nqz * nqz + nqw * nqw;
    if (normSq > 1e-8f) {
        float invNorm = rsqrtf(normSq);
        t.rotX = nqx * invNorm;
        t.rotY = nqy * invNorm;
        t.rotZ = nqz * invNorm;
        t.rotW = nqw * invNorm;
    }

    // 地面との接触判定 (Y = 0 平面)
    float groundLevel = 0.0f;
    if (t.posY < groundLevel) {
        t.posY = groundLevel;
        if (t.linearVelY < 0.0f) {
            t.linearVelY = -t.linearVelY * b.restitution;
        }
        // 地面摩擦
        float frict = 1.0f - b.friction * dt * 10.0f;
        if (frict < 0.0f) frict = 0.0f;
        t.linearVelX *= frict;
        t.linearVelZ *= frict;
    }
}

// 6DoF スプリング拘束反復充足カーネル
extern "C" __global__
void solve_spring_joints_kernel(
    const KernelJoint* joints,
    const KernelRigidBody* bodies,
    KernelTransform* transforms,
    float dt,
    int jointCount
) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx >= jointCount) return;

    const KernelJoint& j = joints[idx];
    if (j.bodyA < 0 || j.bodyB < 0) return;

    KernelTransform& tA = transforms[j.bodyA];
    KernelTransform& tB = transforms[j.bodyB];
    const KernelRigidBody& bA = bodies[j.bodyA];
    const KernelRigidBody& bB = bodies[j.bodyB];

    // 相対位置の差分 (スプリング変位)
    float dx = tB.posX - tA.posX;
    float dy = tB.posY - tA.posY;
    float dz = tB.posZ - tA.posZ;

    // スプリング復元力 F = -k * x
    float fx = -j.springLinearStiffness[0] * dx;
    float fy = -j.springLinearStiffness[1] * dy;
    float fz = -j.springLinearStiffness[2] * dz;

    // 剛体 B が物理対象なら加速度を適用
    if (bB.physicsMode != 0 && bB.mass > 0.0f) {
        float invMassB = 1.0f / bB.mass;
        tB.linearVelX += fx * invMassB * dt;
        tB.linearVelY += fy * invMassB * dt;
        tB.linearVelZ += fz * invMassB * dt;
    }

    // 剛体 A が物理対象なら反作用を適用
    if (bA.physicsMode != 0 && bA.mass > 0.0f) {
        float invMassA = 1.0f / bA.mass;
        tA.linearVelX -= fx * invMassA * dt;
        tA.linearVelY -= fy * invMassA * dt;
        tA.linearVelZ -= fz * invMassA * dt;
    }
}

// 頂点スキニングデータ構造体
struct KernelVertexSkin {
    float origPos[3];
    int boneIndices[4];
    float boneWeights[4];
};

// 頂点スキニング並列カーネル (Linear Blend Skinning / LBS)
extern "C" __global__
void skinning_kernel(
    const KernelVertexSkin* vertices,
    const float* boneMatrices,
    float* outPositions,
    int vertexCount,
    int boneCount
) {
    int idx = blockDim.x * blockIdx.x + threadIdx.x;
    if (idx >= vertexCount) return;

    const KernelVertexSkin& v = vertices[idx];
    float vx = v.origPos[0];
    float vy = v.origPos[1];
    float vz = v.origPos[2];

    float outX = 0.0f;
    float outY = 0.0f;
    float outZ = 0.0f;

    for (int k = 0; k < 4; ++k) {
        int bIdx = v.boneIndices[k];
        float w = v.boneWeights[k];
        if (w <= 0.0001f || bIdx < 0 || bIdx >= boneCount) continue;

        int mOffset = bIdx * 16;
        float m11 = boneMatrices[mOffset + 0];
        float m12 = boneMatrices[mOffset + 1];
        float m13 = boneMatrices[mOffset + 2];
        float m21 = boneMatrices[mOffset + 4];
        float m22 = boneMatrices[mOffset + 5];
        float m23 = boneMatrices[mOffset + 6];
        float m31 = boneMatrices[mOffset + 8];
        float m32 = boneMatrices[mOffset + 9];
        float m33 = boneMatrices[mOffset + 10];
        float m41 = boneMatrices[mOffset + 12];
        float m42 = boneMatrices[mOffset + 13];
        float m43 = boneMatrices[mOffset + 14];

        outX += ((vx * m11) + (vy * m21) + (vz * m31) + m41) * w;
        outY += ((vx * m12) + (vy * m22) + (vz * m32) + m42) * w;
        outZ += ((vx * m13) + (vy * m23) + (vz * m33) + m43) * w;
    }

    int outOffset = idx * 3;
    outPositions[outOffset + 0] = outX;
    outPositions[outOffset + 1] = outY;
    outPositions[outOffset + 2] = outZ;
}
)";

// 内部ステート保持構造体
struct CudaPhysicsState {
  bool isInitialized = false;
  CUdevice device = 0;
  CUcontext context = nullptr;
  CUmodule module = nullptr;
  CUfunction stepBodiesFunc = nullptr;
  CUfunction solveJointsFunc = nullptr;
  CUfunction skinningFunc = nullptr;

  CUdeviceptr dBodies = 0;
  CUdeviceptr dJoints = 0;
  CUdeviceptr dTransforms = 0;

  int bodyCount = 0;
  int jointCount = 0;
  size_t allocatedBodies = 0;
  size_t allocatedJoints = 0;

  std::vector<GpuRigidBodyData> hostBodies;
  std::vector<GpuJointData> hostJoints;
  std::vector<GpuRigidBodyTransform> hostTransforms;
};

static CudaPhysicsState g_state;

// CUDA デバイスが利用可能か照会
CUDA_PHYSICS_API int cuda_physics_is_available() {
  int deviceCount = 0;
  cudaError_t err = cudaGetDeviceCount(&deviceCount);
  if (err != cudaSuccess || deviceCount <= 0) {
    return 0;
  }
  return 1;
}

// GPU デバイス情報の取得
CUDA_PHYSICS_API int cuda_physics_get_device_info(GpuDeviceInfo *outInfo) {
  if (!outInfo)
    return 0;
  int deviceId = 0;
  cudaError_t err = cudaGetDevice(&deviceId);
  if (err != cudaSuccess) {
    deviceId = 0;
  }

  cudaDeviceProp prop;
  err = cudaGetDeviceProperties(&prop, deviceId);
  if (err != cudaSuccess) {
    return 0;
  }

  std::memset(outInfo, 0, sizeof(GpuDeviceInfo));
  std::strncpy(outInfo->deviceName, prop.name, sizeof(outInfo->deviceName) - 1);
  outInfo->majorCapability = prop.major;
  outInfo->minorCapability = prop.minor;
  outInfo->multiProcessorCount = prop.multiProcessorCount;

  // 各世代別 SM あたり CUDA コア数 (Maxwell, Pascal, Volta, Turing, Ampere, Ada
  // Lovelace, 最新世代)
  int coresPerSm = 128;
  if (prop.major == 5)
    coresPerSm = 128;
  else if (prop.major == 6 && prop.minor == 0)
    coresPerSm = 64;
  else if (prop.major == 6)
    coresPerSm = 128;
  else if (prop.major == 7 && prop.minor == 0)
    coresPerSm = 64;
  else if (prop.major == 7 && prop.minor == 5)
    coresPerSm = 64;
  else if (prop.major == 8 && prop.minor == 0)
    coresPerSm = 64;
  else if (prop.major == 8)
    coresPerSm = 128;
  else if (prop.major >= 9)
    coresPerSm = 128;
  outInfo->cudaCores = prop.multiProcessorCount * coresPerSm;

  size_t freeMem = 0, totalMem = 0;
  cudaMemGetInfo(&freeMem, &totalMem);
  outInfo->freeMemoryBytes = freeMem;
  outInfo->totalMemoryBytes = totalMem;

  return 1;
}

// 物理アクセラレータの初期化 (NVRTC JIT コンパイル & GPU バッファ確保)
CUDA_PHYSICS_API int cuda_physics_initialize(int maxBodies, int maxJoints) {
  if (!cuda_physics_is_available())
    return 0;
  if (g_state.isInitialized) {
    cuda_physics_shutdown();
  }

  // CUDA Driver API 初期化
  CUresult res = cuInit(0);
  if (res != CUDA_SUCCESS)
    return 0;

  res = cuDeviceGet(&g_state.device, 0);
  if (res != CUDA_SUCCESS)
    return 0;

  res = cuCtxCreate(&g_state.context, 0, g_state.device);
  if (res != CUDA_SUCCESS)
    return 0;

  // NVRTC による CUDA カーネル JIT コンパイル
  nvrtcProgram prog;
  nvrtcResult nres = nvrtcCreateProgram(
      &prog, g_cudaKernelSource, "mmd_physics_kernel.cu", 0, nullptr, nullptr);
  if (nres != NVRTC_SUCCESS) {
    cuCtxDestroy(g_state.context);
    return 0;
  }

  // 検出された GPU の Compute Capability を動的取得
  int major = 8, minor = 9;
  cuDeviceGetAttribute(&major, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MAJOR,
                       g_state.device);
  cuDeviceGetAttribute(&minor, CU_DEVICE_ATTRIBUTE_COMPUTE_CAPABILITY_MINOR,
                       g_state.device);

  // デバイス固有のアーキテクチャ指定オプションを動的生成 (例: compute_75,
  // compute_86, compute_89 等)
  std::string archOpt = "--gpu-architecture=compute_" + std::to_string(major) +
                        std::to_string(minor);
  const char *opts[] = {archOpt.c_str()};
  nres = nvrtcCompileProgram(prog, 1, opts);
  if (nres != NVRTC_SUCCESS) {
    // フォールバック: 汎用互換アーキテクチャ (compute_75) で再試行
    const char *fallbackOpts[] = {"--gpu-architecture=compute_75"};
    nres = nvrtcCompileProgram(prog, 1, fallbackOpts);
  }
  if (nres != NVRTC_SUCCESS) {
    nvrtcDestroyProgram(&prog);
    cuCtxDestroy(g_state.context);
    return 0;
  }

  size_t ptxSize = 0;
  nvrtcGetPTXSize(prog, &ptxSize);
  std::string ptx(ptxSize, '\0');
  nvrtcGetPTX(prog, &ptx[0]);
  nvrtcDestroyProgram(&prog);

  // PTX からモジュールをロード
  res = cuModuleLoadData(&g_state.module, ptx.c_str());
  if (res != CUDA_SUCCESS) {
    cuCtxDestroy(g_state.context);
    return 0;
  }

  // カーネル関数の取得
  cuModuleGetFunction(&g_state.stepBodiesFunc, g_state.module,
                      "step_rigid_bodies_kernel");
  cuModuleGetFunction(&g_state.solveJointsFunc, g_state.module,
                      "solve_spring_joints_kernel");
  cuModuleGetFunction(&g_state.skinningFunc, g_state.module, "skinning_kernel");

  // バッファサイズの決定
  size_t bodyCapacity = maxBodies > 0 ? (size_t)maxBodies : 2048;
  size_t jointCapacity = maxJoints > 0 ? (size_t)maxJoints : 2048;

  cuMemAlloc(&g_state.dBodies, bodyCapacity * sizeof(GpuRigidBodyData));
  cuMemAlloc(&g_state.dTransforms,
             bodyCapacity * sizeof(GpuRigidBodyTransform));
  cuMemAlloc(&g_state.dJoints, jointCapacity * sizeof(GpuJointData));

  g_state.allocatedBodies = bodyCapacity;
  g_state.allocatedJoints = jointCapacity;
  g_state.bodyCount = 0;
  g_state.jointCount = 0;
  g_state.hostBodies.clear();
  g_state.hostJoints.clear();
  g_state.hostTransforms.clear();

  g_state.isInitialized = true;
  return 1;
}

// リソースの破棄と終了
CUDA_PHYSICS_API void cuda_physics_shutdown() {
  cuda_skinning_shutdown();
  if (!g_state.isInitialized)
    return;

  if (g_state.dBodies) {
    cuMemFree(g_state.dBodies);
    g_state.dBodies = 0;
  }
  if (g_state.dTransforms) {
    cuMemFree(g_state.dTransforms);
    g_state.dTransforms = 0;
  }
  if (g_state.dJoints) {
    cuMemFree(g_state.dJoints);
    g_state.dJoints = 0;
  }

  if (g_state.module) {
    cuModuleUnload(g_state.module);
    g_state.module = nullptr;
  }
  if (g_state.context) {
    cuCtxDestroy(g_state.context);
    g_state.context = nullptr;
  }

  g_state.hostBodies.clear();
  g_state.hostJoints.clear();
  g_state.hostTransforms.clear();
  g_state.bodyCount = 0;
  g_state.jointCount = 0;
  g_state.isInitialized = false;
}

// 剛体パラメータの受領・格納
CUDA_PHYSICS_API int cuda_physics_upload_bodies(const GpuRigidBodyData *bodies,
                                                int count) {
  if (!g_state.isInitialized || !bodies || count <= 0)
    return 0;
  if ((size_t)count > g_state.allocatedBodies)
    return 0;

  g_state.bodyCount = count;
  g_state.hostBodies.assign(bodies, bodies + count);
  cuMemcpyHtoD(g_state.dBodies, bodies, count * sizeof(GpuRigidBodyData));

  // トランスフォーム配列の初期化
  g_state.hostTransforms.resize(count);
  for (int i = 0; i < count; ++i) {
    GpuRigidBodyTransform &t = g_state.hostTransforms[i];
    t.posX = bodies[i].position[0];
    t.posY = bodies[i].position[1];
    t.posZ = bodies[i].position[2];
    t.rotX = bodies[i].rotation[0];
    t.rotY = bodies[i].rotation[1];
    t.rotZ = bodies[i].rotation[2];
    t.rotW = 1.0f;
    t.linearVelX = 0.0f;
    t.linearVelY = 0.0f;
    t.linearVelZ = 0.0f;
    t.angularVelX = 0.0f;
    t.angularVelY = 0.0f;
    t.angularVelZ = 0.0f;
  }
  cuMemcpyHtoD(g_state.dTransforms, g_state.hostTransforms.data(),
               count * sizeof(GpuRigidBodyTransform));

  return 1;
}

// ジョイントパラメータの受領・格納
CUDA_PHYSICS_API int cuda_physics_upload_joints(const GpuJointData *joints,
                                                int count) {
  if (!g_state.isInitialized || !joints || count <= 0)
    return 0;
  if ((size_t)count > g_state.allocatedJoints)
    return 0;

  g_state.jointCount = count;
  g_state.hostJoints.assign(joints, joints + count);
  cuMemcpyHtoD(g_state.dJoints, joints, count * sizeof(GpuJointData));
  return 1;
}

// 剛体トランスフォームのセット (キネマティック位置・回転の更新)
CUDA_PHYSICS_API int
cuda_physics_set_transforms(const GpuRigidBodyTransform *transforms,
                            int count) {
  if (!g_state.isInitialized || !transforms || count <= 0)
    return 0;
  int updateCount = count < g_state.bodyCount ? count : g_state.bodyCount;

  cuMemcpyHtoD(g_state.dTransforms, transforms,
               updateCount * sizeof(GpuRigidBodyTransform));
  std::memcpy(g_state.hostTransforms.data(), transforms,
              updateCount * sizeof(GpuRigidBodyTransform));
  return 1;
}

// 最新の剛体トランスフォームを回収
CUDA_PHYSICS_API int
cuda_physics_get_transforms(GpuRigidBodyTransform *outTransforms, int count) {
  if (!g_state.isInitialized || !outTransforms || count <= 0)
    return 0;
  int copyCount = count < g_state.bodyCount ? count : g_state.bodyCount;

  cuMemcpyDtoH(outTransforms, g_state.dTransforms,
               copyCount * sizeof(GpuRigidBodyTransform));
  return 1;
}

// 速度・角速度のリセット
CUDA_PHYSICS_API int cuda_physics_reset_velocities() {
  if (!g_state.isInitialized || g_state.bodyCount <= 0)
    return 0;

  cuMemcpyDtoH(g_state.hostTransforms.data(), g_state.dTransforms,
               g_state.bodyCount * sizeof(GpuRigidBodyTransform));
  for (auto &t : g_state.hostTransforms) {
    t.linearVelX = 0.0f;
    t.linearVelY = 0.0f;
    t.linearVelZ = 0.0f;
    t.angularVelX = 0.0f;
    t.angularVelY = 0.0f;
    t.angularVelZ = 0.0f;
  }
  cuMemcpyHtoD(g_state.dTransforms, g_state.hostTransforms.data(),
               g_state.bodyCount * sizeof(GpuRigidBodyTransform));
  return 1;
}

// GPU 並列ステップシミュレーションの実行
CUDA_PHYSICS_API int
cuda_physics_step_simulation(float timeStep, int maxSubSteps, float subStepHz) {
  if (!g_state.isInitialized || g_state.bodyCount <= 0)
    return 0;

  float dt =
      (subStepHz > 0.0f) ? (1.0f / subStepHz) : (timeStep / (float)maxSubSteps);
  int subSteps = maxSubSteps > 0 ? maxSubSteps : 1;
  float gravityY = -9.8f * 8.0f; // MMD標準スケール換算の重力加速度

  int threads = 256;
  int bodyBlocks = (g_state.bodyCount + threads - 1) / threads;
  int jointBlocks = (g_state.jointCount > 0)
                        ? ((g_state.jointCount + threads - 1) / threads)
                        : 1;

  for (int step = 0; step < subSteps; ++step) {
    // 剛体積分カーネルの起動
    void *bodyArgs[] = {&g_state.dBodies, &g_state.dTransforms, &dt, &gravityY,
                        &g_state.bodyCount};
    cuLaunchKernel(g_state.stepBodiesFunc, bodyBlocks, 1, 1, threads, 1, 1, 0,
                   nullptr, bodyArgs, nullptr);

    // スプリング拘束カーネルの起動
    if (g_state.jointCount > 0 && g_state.solveJointsFunc) {
      void *jointArgs[] = {&g_state.dJoints, &g_state.dBodies,
                           &g_state.dTransforms, &dt, &g_state.jointCount};
      cuLaunchKernel(g_state.solveJointsFunc, jointBlocks, 1, 1, threads, 1, 1,
                     0, nullptr, jointArgs, nullptr);
    }
  }

  cuCtxSynchronize();
  return 1;
}

// 頂点スキニング管理ステート
struct GpuSkinningState {
  bool isInitialized = false;
  int vertexCount = 0;
  size_t allocatedVertices = 0;
  size_t allocatedBones = 0;
  CUdeviceptr dVertices = 0;
  CUdeviceptr dBoneMatrices = 0;
  CUdeviceptr dOutPositions = 0;
};
static GpuSkinningState g_skinState;

// 頂点スキニング初期化 (初期頂点座標・ボーンインデックス・ウェイトを VRAM
// へ格納)
CUDA_PHYSICS_API int
cuda_skinning_initialize(int vertexCount, const GpuVertexSkinData *vertices) {
  if (!cuda_physics_is_available() || vertexCount <= 0 || !vertices)
    return 0;

  // CUDA コンテキストの確立
  if (!g_state.isInitialized) {
    if (!cuda_physics_initialize(1, 1))
      return 0;
  }

  if (!g_state.skinningFunc)
    return 0;

  cuda_skinning_shutdown();

  size_t vertSize = (size_t)vertexCount * sizeof(GpuVertexSkinData);
  size_t outSize = (size_t)vertexCount * 3 * sizeof(float);
  size_t boneSize = 512 * 16 * sizeof(float);

  CUresult res = cuMemAlloc(&g_skinState.dVertices, vertSize);
  if (res != CUDA_SUCCESS)
    return 0;

  res = cuMemAlloc(&g_skinState.dOutPositions, outSize);
  if (res != CUDA_SUCCESS) {
    cuMemFree(g_skinState.dVertices);
    g_skinState.dVertices = 0;
    return 0;
  }

  res = cuMemAlloc(&g_skinState.dBoneMatrices, boneSize);
  if (res != CUDA_SUCCESS) {
    cuMemFree(g_skinState.dVertices);
    cuMemFree(g_skinState.dOutPositions);
    g_skinState.dVertices = 0;
    g_skinState.dOutPositions = 0;
    return 0;
  }

  // 頂点初期データを VRAM へ一括転送
  cuMemcpyHtoD(g_skinState.dVertices, vertices, vertSize);

  g_skinState.vertexCount = vertexCount;
  g_skinState.allocatedVertices = vertexCount;
  g_skinState.allocatedBones = 512;
  g_skinState.isInitialized = true;
  return 1;
}

// 毎フレームの並列スキニング計算
CUDA_PHYSICS_API int cuda_skinning_compute(const float *boneMatrices,
                                           int boneCount, float *outPositions) {
  if (!g_skinState.isInitialized || !boneMatrices || boneCount <= 0 ||
      !outPositions)
    return 0;
  if (!g_state.skinningFunc)
    return 0;

  // ボーン行列バッファの拡張が必要な場合
  if ((size_t)boneCount > g_skinState.allocatedBones) {
    cuMemFree(g_skinState.dBoneMatrices);
    size_t newSize = (size_t)boneCount * 16 * sizeof(float);
    if (cuMemAlloc(&g_skinState.dBoneMatrices, newSize) != CUDA_SUCCESS) {
      g_skinState.isInitialized = false;
      return 0;
    }
    g_skinState.allocatedBones = boneCount;
  }

  // ボーン行列を VRAM へ転送
  cuMemcpyHtoD(g_skinState.dBoneMatrices, boneMatrices,
               boneCount * 16 * sizeof(float));

  // カーネル起動パラメータ
  int threads = 256;
  int blocks = (g_skinState.vertexCount + threads - 1) / threads;

  void *kernelArgs[] = {&g_skinState.dVertices, &g_skinState.dBoneMatrices,
                        &g_skinState.dOutPositions, &g_skinState.vertexCount,
                        &boneCount};

  CUresult res = cuLaunchKernel(g_state.skinningFunc, blocks, 1, 1, threads, 1,
                                1, 0, nullptr, kernelArgs, nullptr);
  if (res != CUDA_SUCCESS)
    return 0;

  // 変形後頂点座標をホストへ回収
  cuMemcpyDtoH(outPositions, g_skinState.dOutPositions,
               g_skinState.vertexCount * 3 * sizeof(float));
  cuCtxSynchronize();
  return 1;
}

// 頂点スキニングリソースの解放
CUDA_PHYSICS_API void cuda_skinning_shutdown() {
  if (g_skinState.dVertices) {
    cuMemFree(g_skinState.dVertices);
    g_skinState.dVertices = 0;
  }
  if (g_skinState.dOutPositions) {
    cuMemFree(g_skinState.dOutPositions);
    g_skinState.dOutPositions = 0;
  }
  if (g_skinState.dBoneMatrices) {
    cuMemFree(g_skinState.dBoneMatrices);
    g_skinState.dBoneMatrices = 0;
  }
  g_skinState.isInitialized = false;
  g_skinState.vertexCount = 0;
  g_skinState.allocatedVertices = 0;
  g_skinState.allocatedBones = 0;
}
