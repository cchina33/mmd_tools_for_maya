#pragma once

#ifdef _WIN32
  #define BULLET_MMD_API extern "C" __declspec(dllexport)
#else
  #define BULLET_MMD_API extern "C"
#endif

#include <cstdint>

struct BulletEngine;

BULLET_MMD_API BulletEngine* bullet_create();
BULLET_MMD_API void bullet_destroy(BulletEngine* engine);
BULLET_MMD_API void bullet_reset(BulletEngine* engine);
BULLET_MMD_API void bullet_clear(BulletEngine* engine);

BULLET_MMD_API void bullet_set_gravity(BulletEngine* engine, float gx, float gy, float gz);

BULLET_MMD_API int bullet_add_rigidbody(
    BulletEngine* engine,
    int boneIndex,
    int shapeType,      // 0: Sphere, 1: Box, 2: Capsule
    int physicsMode,    // 0: Kinematic, 1: Dynamic, 2: Aligned
    float sizeX, float sizeY, float sizeZ,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ,
    float mass,
    float linearDamping, float angularDamping,
    float restitution, float friction,
    uint16_t group, uint16_t collisionMask
);

BULLET_MMD_API void bullet_set_rigidbody_transform(
    BulletEngine* engine,
    int rbIndex,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ
);

BULLET_MMD_API void bullet_set_target_transform(
    BulletEngine* engine,
    int rbIndex,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ
);

BULLET_MMD_API void bullet_get_rigidbody_transform(
    BulletEngine* engine,
    int rbIndex,
    float* outPosX, float* outPosY, float* outPosZ,
    float* outRotX, float* outRotY, float* outRotZ, float* outRotW
);

BULLET_MMD_API int bullet_add_joint(
    BulletEngine* engine,
    int rbAIndex, int rbBIndex,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ,
    float posMinX, float posMinY, float posMinZ,
    float posMaxX, float posMaxY, float posMaxZ,
    float rotMinX, float rotMinY, float rotMinZ,
    float rotMaxX, float rotMaxY, float rotMaxZ,
    float springPosX, float springPosY, float springPosZ,
    float springRotX, float springRotY, float springRotZ
);

BULLET_MMD_API void bullet_step_simulation(
    BulletEngine* engine,
    float dt,
    int maxSubSteps,
    float fixedTimeStep
);
