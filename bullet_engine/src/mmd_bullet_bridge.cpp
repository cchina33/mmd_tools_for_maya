#include "mmd_bullet_bridge.h"

#include "btBulletDynamicsCommon.h"
#include "BulletDynamics/ConstraintSolver/btGeneric6DofSpringConstraint.h"

#include <vector>
#include <cmath>
#include <iostream>

namespace {

inline btQuaternion eulerToQuaternionXYZ(float rx, float ry, float rz) {
    // MMD のオイラー角 (X -> Y -> Z 順のローカル回転合成)
    btQuaternion qx(btVector3(1, 0, 0), rx);
    btQuaternion qy(btVector3(0, 1, 0), ry);
    btQuaternion qz(btVector3(0, 0, 1), rz);
    return qz * qy * qx;
}

struct RigidBodyEntry {
    int boneIndex;
    int physicsMode; // 0: Kinematic, 1: Dynamic, 2: Aligned
    btRigidBody* body;
    btCollisionShape* shape;
    btDefaultMotionState* motionState;
    btVector3 targetPos;
    btQuaternion targetRot;
    btTransform initialTransform;
};

struct JointEntry {
    btGeneric6DofSpringConstraint* spring;
};

} // namespace

struct BulletEngine {
    btDefaultCollisionConfiguration* collisionConfig = nullptr;
    btCollisionDispatcher* dispatcher = nullptr;
    btBroadphaseInterface* broadphase = nullptr;
    btSequentialImpulseConstraintSolver* solver = nullptr;
    btDiscreteDynamicsWorld* world = nullptr;

    std::vector<RigidBodyEntry> rigidBodies;
    std::vector<JointEntry> joints;

    btVector3 gravity = btVector3(0.0f, -98.0f, 0.0f); // MMD標準重力 (約 -9.8 m/s^2 * 10)

    BulletEngine() {
        initWorld();
    }

    ~BulletEngine() {
        cleanup();
    }

    void initWorld() {
        collisionConfig = new btDefaultCollisionConfiguration();
        dispatcher = new btCollisionDispatcher(collisionConfig);
        broadphase = new btDbvtBroadphase();
        solver = new btSequentialImpulseConstraintSolver();
        world = new btDiscreteDynamicsWorld(dispatcher, broadphase, solver, collisionConfig);
        world->setGravity(gravity);

        // ERP (Error Reduction Parameter) の設定
        // 関節拘束の補正率をマイルド (0.2) に設定し、めり込み復帰時の過度なゴム跳ね・振動を抑制
        world->getSolverInfo().m_erp = 0.2f;
        world->getSolverInfo().m_erp2 = 0.2f;
        world->getSolverInfo().m_numIterations = 10;
    }

    void cleanup() {
        clear();
        if (world) { delete world; world = nullptr; }
        if (solver) { delete solver; solver = nullptr; }
        if (broadphase) { delete broadphase; broadphase = nullptr; }
        if (dispatcher) { delete dispatcher; dispatcher = nullptr; }
        if (collisionConfig) { delete collisionConfig; collisionConfig = nullptr; }
    }

    void clear() {
        if (!world) return;

        // ジョイント拘束の解放
        for (auto& je : joints) {
            if (je.spring) {
                world->removeConstraint(je.spring);
                delete je.spring;
            }
        }
        joints.clear();

        // 剛体の解放
        for (auto& re : rigidBodies) {
            if (re.body) {
                world->removeRigidBody(re.body);
                delete re.body;
            }
            if (re.motionState) {
                delete re.motionState;
            }
            if (re.shape) {
                delete re.shape;
            }
        }
        rigidBodies.clear();
    }

    void reset() {
        for (auto& re : rigidBodies) {
            if (!re.body) continue;
            re.body->setWorldTransform(re.initialTransform);
            if (re.motionState) {
                re.motionState->setWorldTransform(re.initialTransform);
            }
            re.body->setLinearVelocity(btVector3(0, 0, 0));
            re.body->setAngularVelocity(btVector3(0, 0, 0));
            re.body->clearForces();
            re.body->activate(true);
        }
    }
};

BULLET_MMD_API BulletEngine* bullet_create() {
    return new BulletEngine();
}

BULLET_MMD_API void bullet_destroy(BulletEngine* engine) {
    if (engine) {
        delete engine;
    }
}

BULLET_MMD_API void bullet_reset(BulletEngine* engine) {
    if (engine) engine->reset();
}

BULLET_MMD_API void bullet_clear(BulletEngine* engine) {
    if (engine) engine->clear();
}

BULLET_MMD_API void bullet_set_gravity(BulletEngine* engine, float gx, float gy, float gz) {
    if (!engine) return;
    engine->gravity = btVector3(gx, gy, gz);
    if (engine->world) {
        engine->world->setGravity(engine->gravity);
    }
}

BULLET_MMD_API int bullet_add_rigidbody(
    BulletEngine* engine,
    int boneIndex,
    int shapeType,
    int physicsMode,
    float sizeX, float sizeY, float sizeZ,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ,
    float mass,
    float linearDamping, float angularDamping,
    float restitution, float friction,
    uint16_t group, uint16_t collisionMask
) {
    if (!engine || !engine->world) return -1;

    // 1. 形状オブジェクト生成
    btCollisionShape* shape = nullptr;
    if (shapeType == 0) {
        // 球 (sizeX = 半径)
        shape = new btSphereShape(sizeX);
    } else if (shapeType == 1) {
        // 箱 (sizeX, sizeY, sizeZ = ハーフサイズ)
        shape = new btBoxShape(btVector3(sizeX, sizeY, sizeZ));
    } else {
        // カプセル (sizeX = 半径, sizeY = 高さ)
        shape = new btCapsuleShape(sizeX, sizeY);
    }

    // 2. 初期トランスフォーム
    btTransform startTransform;
    startTransform.setIdentity();
    startTransform.setOrigin(btVector3(posX, posY, posZ));
    startTransform.setRotation(eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

    // 3. 慣性モーメントと質量
    btVector3 localInertia(0, 0, 0);
    float actualMass = (physicsMode == 0) ? 0.0f : mass;
    if (actualMass > 0.0f) {
        shape->calculateLocalInertia(actualMass, localInertia);
    }

    // 4. モーションステートと剛体本体
    btDefaultMotionState* motionState = new btDefaultMotionState(startTransform);
    btRigidBody::btRigidBodyConstructionInfo rbInfo(actualMass, motionState, shape, localInertia);
    rbInfo.m_linearDamping = linearDamping;
    rbInfo.m_angularDamping = angularDamping;
    rbInfo.m_restitution = restitution;
    rbInfo.m_friction = friction;

    btRigidBody* body = new btRigidBody(rbInfo);

    // 物理モード別設定
    if (physicsMode == 0) {
        // Kinematic: 骨のアニメーションに完全追従
        body->setCollisionFlags(body->getCollisionFlags() | btCollisionObject::CF_KINEMATIC_OBJECT);
        body->setActivationState(DISABLE_DEACTIVATION);
    } else if (physicsMode == 2) {
        // Aligned: 物理演算しつつ位置は目標固定 (重力遮断)
        body->setActivationState(DISABLE_DEACTIVATION);
    } else {
        // Dynamic
        body->setActivationState(DISABLE_DEACTIVATION);
    }

    // ワールドへ追加 (PMXのcollision_maskは衝突を許可するグループのビットフラグそのもの)
    short groupBit = static_cast<short>(1 << group);
    short maskBit = static_cast<short>(collisionMask);
    engine->world->addRigidBody(body, groupBit, maskBit);

    // 登録
    RigidBodyEntry entry;
    entry.boneIndex = boneIndex;
    entry.physicsMode = physicsMode;
    entry.body = body;
    entry.shape = shape;
    entry.motionState = motionState;
    entry.targetPos = btVector3(posX, posY, posZ);
    entry.targetRot = startTransform.getRotation();
    entry.initialTransform = startTransform;

    int newIdx = static_cast<int>(engine->rigidBodies.size());
    engine->rigidBodies.push_back(entry);
    return newIdx;
}

BULLET_MMD_API void bullet_set_rigidbody_transform(
    BulletEngine* engine,
    int rbIndex,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ
) {
    if (!engine || rbIndex < 0 || rbIndex >= static_cast<int>(engine->rigidBodies.size())) return;
    auto& re = engine->rigidBodies[rbIndex];
    if (!re.body) return;

    btTransform tr;
    tr.setOrigin(btVector3(posX, posY, posZ));
    tr.setRotation(eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

    re.body->setWorldTransform(tr);
    if (re.motionState) {
        re.motionState->setWorldTransform(tr);
    }
}

BULLET_MMD_API void bullet_set_target_transform(
    BulletEngine* engine,
    int rbIndex,
    float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ
) {
    if (!engine || rbIndex < 0 || rbIndex >= static_cast<int>(engine->rigidBodies.size())) return;
    auto& re = engine->rigidBodies[rbIndex];
    re.targetPos = btVector3(posX, posY, posZ);
    re.targetRot = eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ);

    if (re.physicsMode == 0 && re.body) {
        // Kinematic: アニメーション姿勢へ移動し、衝突境界AABBを即時更新
        btTransform tr;
        tr.setOrigin(re.targetPos);
        tr.setRotation(re.targetRot);
        if (re.motionState) {
            re.motionState->setWorldTransform(tr);
        }
        re.body->setWorldTransform(tr);
        if (engine->world) {
            engine->world->updateSingleAabb(re.body);
        }
    }
}

BULLET_MMD_API void bullet_get_rigidbody_transform(
    BulletEngine* engine,
    int rbIndex,
    float* outPosX, float* outPosY, float* outPosZ,
    float* outRotX, float* outRotY, float* outRotZ, float* outRotW
) {
    if (!engine || rbIndex < 0 || rbIndex >= static_cast<int>(engine->rigidBodies.size())) return;
    auto& re = engine->rigidBodies[rbIndex];
    if (!re.body) return;

    btTransform tr;
    if (re.motionState) {
        re.motionState->getWorldTransform(tr);
    } else {
        tr = re.body->getWorldTransform();
    }

    const btVector3& pos = tr.getOrigin();
    const btQuaternion& rot = tr.getRotation();

    if (outPosX) *outPosX = pos.x();
    if (outPosY) *outPosY = pos.y();
    if (outPosZ) *outPosZ = pos.z();

    if (outRotX) *outRotX = rot.x();
    if (outRotY) *outRotY = rot.y();
    if (outRotZ) *outRotZ = rot.z();
    if (outRotW) *outRotW = rot.w();
}

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
) {
    if (!engine || !engine->world) return -1;
    if (rbAIndex < 0 || rbAIndex >= static_cast<int>(engine->rigidBodies.size())) return -1;
    if (rbBIndex < 0 || rbBIndex >= static_cast<int>(engine->rigidBodies.size())) return -1;

    btRigidBody* rbA = engine->rigidBodies[rbAIndex].body;
    btRigidBody* rbB = engine->rigidBodies[rbBIndex].body;
    if (!rbA || !rbB) return -1;

    // ジョイントのワールドトランスフォーム
    btTransform jointWorld;
    jointWorld.setIdentity();
    jointWorld.setOrigin(btVector3(posX, posY, posZ));
    jointWorld.setRotation(eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

    // 各剛体のローカル座標系におけるジョイントトランスフォーム
    btTransform frameInA = rbA->getWorldTransform().inverse() * jointWorld;
    btTransform frameInB = rbB->getWorldTransform().inverse() * jointWorld;

    // MMD標準 6DOF スプリングコンストレイントの生成
    btGeneric6DofSpringConstraint* spring = new btGeneric6DofSpringConstraint(*rbA, *rbB, frameInA, frameInB, true);

    // 平行移動リミット
    spring->setLinearLowerLimit(btVector3(posMinX, posMinY, posMinZ));
    spring->setLinearUpperLimit(btVector3(posMaxX, posMaxY, posMaxZ));

    // 回転リミット
    spring->setAngularLowerLimit(btVector3(rotMinX, rotMinY, rotMinZ));
    spring->setAngularUpperLimit(btVector3(rotMaxX, rotMaxY, rotMaxZ));

    // ばね定数設定 (0,1,2: 平行移動, 3,4,5: 回転)
    float springParams[6] = {
        springPosX, springPosY, springPosZ,
        springRotX, springRotY, springRotZ
    };

    for (int i = 0; i < 6; ++i) {
        if (springParams[i] != 0.0f) {
            spring->enableSpring(i, true);
            spring->setStiffness(i, springParams[i]);
            spring->setDamping(i, 1.0f);
        }
    }
    spring->setEquilibriumPoint();

    engine->world->addConstraint(spring, true);

    JointEntry entry;
    entry.spring = spring;
    int jointIdx = static_cast<int>(engine->joints.size());
    engine->joints.push_back(entry);
    return jointIdx;
}

BULLET_MMD_API void bullet_step_simulation(
    BulletEngine* engine,
    float dt,
    int maxSubSteps,
    float fixedTimeStep
) {
    if (!engine || !engine->world) return;

    // 1. Aligned 剛体 (タイプ2) の位置補正と重力遮断
    for (auto& re : engine->rigidBodies) {
        if (re.physicsMode == 2 && re.body) {
            // 位置は目標位置へクランプ、線形速度はゼロ
            btTransform tr = re.body->getWorldTransform();
            tr.setOrigin(re.targetPos);
            re.body->setWorldTransform(tr);
            if (re.motionState) {
                re.motionState->setWorldTransform(tr);
            }
            re.body->setLinearVelocity(btVector3(0, 0, 0));
        }
    }

    // 2. Bullet 物理ワールドのシミュレーション進行
    engine->world->stepSimulation(dt, maxSubSteps, fixedTimeStep);

    // 3. Aligned 剛体のシミュレーション後位置再固定
    for (auto& re : engine->rigidBodies) {
        if (re.physicsMode == 2 && re.body) {
            btTransform tr = re.body->getWorldTransform();
            tr.setOrigin(re.targetPos);
            re.body->setWorldTransform(tr);
            if (re.motionState) {
                re.motionState->setWorldTransform(tr);
            }
            re.body->setLinearVelocity(btVector3(0, 0, 0));
        }
    }
}

BULLET_MMD_API void bullet_reset_velocities(BulletEngine* engine) {
    if (!engine || !engine->world) return;
    for (auto& re : engine->rigidBodies) {
        if (!re.body) continue;
        re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        re.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        re.body->clearForces();
    }
}

BULLET_MMD_API void bullet_reset_constraints(BulletEngine* engine) {
    if (!engine || !engine->world) return;
    for (auto& je : engine->joints) {
        if (!je.spring) continue;
        je.spring->setEquilibriumPoint();
    }
}

BULLET_MMD_API void bullet_relax_penetration(
    BulletEngine* engine,
    int steps,
    float relaxationDamping
) {
    if (!engine || !engine->world || steps <= 0) return;

    // 重力を一時退避してゼロに設定
    btVector3 originalGravity = engine->world->getGravity();
    engine->world->setGravity(btVector3(0.0f, 0.0f, 0.0f));

    // 動的剛体の元のダンピングを保存し、高ダンピングを一時適用
    std::vector<std::pair<float, float>> originalDamping;
    originalDamping.reserve(engine->rigidBodies.size());

    for (auto& re : engine->rigidBodies) {
        if (!re.body) {
            originalDamping.push_back({0.0f, 0.0f});
            continue;
        }
        originalDamping.push_back({re.body->getLinearDamping(), re.body->getAngularDamping()});

        if (re.physicsMode != 0) {
            re.body->setDamping(relaxationDamping, relaxationDamping);
            re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
            re.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
            re.body->clearForces();
        }
    }

    // 衝突接触のみを緩やかに解く事前シミュレーション
    const float dt = 1.0f / 60.0f;
    for (int step = 0; step < steps; ++step) {
        // Kinematic剛体（太もも等）の姿勢を目標位置に固定維持
        for (auto& re : engine->rigidBodies) {
            if (re.physicsMode == 0 && re.body) {
                btTransform tr;
                tr.setOrigin(re.targetPos);
                tr.setRotation(re.targetRot);
                if (re.motionState) {
                    re.motionState->setWorldTransform(tr);
                }
                re.body->setWorldTransform(tr);
                engine->world->updateSingleAabb(re.body);
            } else if (re.physicsMode == 2 && re.body) {
                btTransform tr = re.body->getWorldTransform();
                tr.setOrigin(re.targetPos);
                re.body->setWorldTransform(tr);
                if (re.motionState) {
                    re.motionState->setWorldTransform(tr);
                }
                re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
            }
        }

        engine->world->stepSimulation(dt, 1, dt);
    }

    // 元のダンピングと重力を復元
    for (size_t i = 0; i < engine->rigidBodies.size(); ++i) {
        auto& re = engine->rigidBodies[i];
        if (!re.body) continue;
        re.body->setDamping(originalDamping[i].first, originalDamping[i].second);
        re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
        re.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
        re.body->clearForces();
    }
    engine->world->setGravity(originalGravity);

    // 押し出し後の安定姿勢でジョイントの平衡点を再初期化
    for (auto& je : engine->joints) {
        if (!je.spring) continue;
        je.spring->setEquilibriumPoint();
    }
}
