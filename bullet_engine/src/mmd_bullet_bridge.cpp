#ifndef NOMINMAX
#define NOMINMAX
#endif

#include "mmd_bullet_bridge.h"

#include "BulletDynamics/ConstraintSolver/btConeTwistConstraint.h"
#include "BulletDynamics/ConstraintSolver/btGeneric6DofConstraint.h"
#include "BulletDynamics/ConstraintSolver/btGeneric6DofSpringConstraint.h"
#include "BulletDynamics/ConstraintSolver/btHingeConstraint.h"
#include "BulletDynamics/ConstraintSolver/btPoint2PointConstraint.h"
#include "BulletDynamics/ConstraintSolver/btSliderConstraint.h"
#include "btBulletDynamicsCommon.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <vector>

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
  btRigidBody *body;
  btCollisionShape *shape;
  btDefaultMotionState *motionState;
  btVector3 targetPos;
  btQuaternion targetRot;
  btTransform initialTransform;
};

struct JointEntry {
  int jointType;
  btTypedConstraint *constraint;
  btGeneric6DofSpringConstraint *spring; // 6DOFスプリング型キャッシュ
};

} // namespace

struct BulletEngine {
  btDefaultCollisionConfiguration *collisionConfig = nullptr;
  btCollisionDispatcher *dispatcher = nullptr;
  btBroadphaseInterface *broadphase = nullptr;
  btSequentialImpulseConstraintSolver *solver = nullptr;
  btDiscreteDynamicsWorld *world = nullptr;

  std::vector<RigidBodyEntry> rigidBodies;
  std::vector<JointEntry> joints;

  btCollisionShape *floorShape = nullptr;
  btDefaultMotionState *floorMotionState = nullptr;
  btRigidBody *floorBody = nullptr;

  btVector3 gravity =
      btVector3(0.0f, -98.0f, 0.0f); // MMD標準重力 (約 -9.8 m/s^2 * 10)

  BulletEngine() { initWorld(); }

  ~BulletEngine() { cleanup(); }

  void initWorld() {
    collisionConfig = new btDefaultCollisionConfiguration();
    dispatcher = new btCollisionDispatcher(collisionConfig);
    broadphase = new btDbvtBroadphase();
    solver = new btSequentialImpulseConstraintSolver();
    world = new btDiscreteDynamicsWorld(dispatcher, broadphase, solver,
                                        collisionConfig);
    world->setGravity(gravity);

    // ERP (Error Reduction Parameter) の設定
    // 関節拘束の補正率をマイルド (0.2)
    // に設定し、めり込み復帰時の過度なゴム跳ね・振動を抑制
    world->getSolverInfo().m_erp = 0.2f;
    world->getSolverInfo().m_erp2 = 0.2f;
    world->getSolverInfo().m_numIterations = 10;
  }

  void clearFloor() {
    if (floorBody && world) {
      world->removeRigidBody(floorBody);
    }
    if (floorBody) {
      delete floorBody;
      floorBody = nullptr;
    }
    if (floorMotionState) {
      delete floorMotionState;
      floorMotionState = nullptr;
    }
    if (floorShape) {
      delete floorShape;
      floorShape = nullptr;
    }
  }

  void setFloorPlane(bool enable, float yHeight, float friction = 0.5f,
                     float restitution = 0.0f) {
    clearFloor();
    if (!enable || !world)
      return;

    // Y軸上向きの無限平面法線 (0, 1, 0)、高さ yHeight
    floorShape = new btStaticPlaneShape(btVector3(0.0f, 1.0f, 0.0f), yHeight);
    btTransform floorTrans;
    floorTrans.setIdentity();
    floorMotionState = new btDefaultMotionState(floorTrans);

    btRigidBody::btRigidBodyConstructionInfo rbInfo(
        0.0f, floorMotionState, floorShape, btVector3(0.0f, 0.0f, 0.0f));
    rbInfo.m_friction = friction;
    rbInfo.m_restitution = restitution;
    floorBody = new btRigidBody(rbInfo);

    // 全グループと衝突するように追加 (MMD地面剛体相当)
    world->addRigidBody(floorBody, 0xFFFF, 0xFFFF);
  }

  void cleanup() {
    clear();
    clearFloor();
    if (world) {
      delete world;
      world = nullptr;
    }
    if (solver) {
      delete solver;
      solver = nullptr;
    }
    if (broadphase) {
      delete broadphase;
      broadphase = nullptr;
    }
    if (dispatcher) {
      delete dispatcher;
      dispatcher = nullptr;
    }
    if (collisionConfig) {
      delete collisionConfig;
      collisionConfig = nullptr;
    }
  }

  void clear() {
    if (!world)
      return;

    // ジョイント拘束の解放
    for (auto &je : joints) {
      if (je.constraint) {
        world->removeConstraint(je.constraint);
        delete je.constraint;
      }
    }
    joints.clear();

    // 剛体の解放
    for (auto &re : rigidBodies) {
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
    clearFloor();
  }

  void reset() {
    for (auto &re : rigidBodies) {
      if (!re.body)
        continue;
      re.body->setWorldTransform(re.initialTransform);
      if (re.motionState) {
        re.motionState->setWorldTransform(re.initialTransform);
      }
      // Bullet公式初期化手順:
      // 補間トランスフォームおよび速度バッファのゼロクリア
      re.body->setInterpolationWorldTransform(re.initialTransform);
      re.body->setLinearVelocity(btVector3(0, 0, 0));
      re.body->setAngularVelocity(btVector3(0, 0, 0));
      re.body->setInterpolationLinearVelocity(btVector3(0, 0, 0));
      re.body->setInterpolationAngularVelocity(btVector3(0, 0, 0));
      re.body->clearForces();
      re.body->activate(true);
    }
  }
};

BULLET_MMD_API BulletEngine *bullet_create() { return new BulletEngine(); }

BULLET_MMD_API void bullet_destroy(BulletEngine *engine) {
  if (engine) {
    delete engine;
  }
}

BULLET_MMD_API void bullet_reset(BulletEngine *engine) {
  if (engine)
    engine->reset();
}

BULLET_MMD_API void bullet_clear(BulletEngine *engine) {
  if (engine)
    engine->clear();
}

BULLET_MMD_API void bullet_set_gravity(BulletEngine *engine, float gx, float gy,
                                       float gz) {
  if (!engine)
    return;
  engine->gravity = btVector3(gx, gy, gz);
  if (engine->world) {
    engine->world->setGravity(engine->gravity);
  }
}

BULLET_MMD_API int bullet_add_rigidbody(
    BulletEngine *engine, int boneIndex, int shapeType, int physicsMode,
    float sizeX, float sizeY, float sizeZ, float posX, float posY, float posZ,
    float rotEulerX, float rotEulerY, float rotEulerZ, float mass,
    float linearDamping, float angularDamping, float restitution,
    float friction, uint16_t group, uint16_t collisionMask) {
  if (!engine || !engine->world)
    return -1;

  // 形状オブジェクト生成
  btCollisionShape *shape = nullptr;
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

  // 初期トランスフォーム
  btTransform startTransform;
  startTransform.setIdentity();
  startTransform.setOrigin(btVector3(posX, posY, posZ));
  startTransform.setRotation(
      eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

  // 慣性モーメントと質量
  btVector3 localInertia(0, 0, 0);
  float actualMass = (physicsMode == 0) ? 0.0f : mass;
  if (actualMass > 0.0f) {
    shape->calculateLocalInertia(actualMass, localInertia);
  }

  // モーションステートと剛体本体
  btDefaultMotionState *motionState = new btDefaultMotionState(startTransform);
  btRigidBody::btRigidBodyConstructionInfo rbInfo(actualMass, motionState,
                                                  shape, localInertia);
  rbInfo.m_linearDamping = linearDamping;
  rbInfo.m_angularDamping = angularDamping;
  rbInfo.m_restitution = restitution;
  rbInfo.m_friction = friction;

  btRigidBody *body = new btRigidBody(rbInfo);

  // 物理モード別設定
  if (physicsMode == 0) {
    // Kinematic: 骨のアニメーションに忠実追従
    body->setCollisionFlags(body->getCollisionFlags() |
                            btCollisionObject::CF_KINEMATIC_OBJECT);
    body->setActivationState(DISABLE_DEACTIVATION);
  } else if (physicsMode == 2) {
    // Aligned: 物理演算しつつ位置は目標固定 (重力遮断)
    body->setActivationState(DISABLE_DEACTIVATION);
  } else {
    // Dynamic
    body->setActivationState(DISABLE_DEACTIVATION);
  }

  // 床や他剛体のすり抜け防止 (CCD: Continuous Collision Detection)
  if (physicsMode != 0 && actualMass > 0.0f) {
    float minRadius = sizeX;
    body->setCcdMotionThreshold(minRadius * 0.5f);
    body->setCcdSweptSphereRadius(minRadius * 0.2f);
  }

  // ワールドへ追加
  // (PMXバイナリのcollision_maskは衝突許可フラグのため、反転せずそのまま渡す)
  short groupBit = static_cast<short>(1 << group);
  short maskBit = static_cast<short>(collisionMask);
  // 全グループ非衝突に設定されている場合でも環境(床)との衝突を維持
  if (maskBit == 0) {
    maskBit = static_cast<short>(0x0001);
  }
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

BULLET_MMD_API void
bullet_set_rigidbody_transform(BulletEngine *engine, int rbIndex, float posX,
                               float posY, float posZ, float rotEulerX,
                               float rotEulerY, float rotEulerZ) {
  if (!engine || rbIndex < 0 ||
      rbIndex >= static_cast<int>(engine->rigidBodies.size()))
    return;
  auto &re = engine->rigidBodies[rbIndex];
  if (!re.body)
    return;

  btTransform tr;
  tr.setOrigin(btVector3(posX, posY, posZ));
  tr.setRotation(eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

  re.body->setWorldTransform(tr);
  if (re.motionState) {
    re.motionState->setWorldTransform(tr);
  }
  // 補間トランスフォームと速度のゼロ化により急激な移動補間バグを防止
  re.body->setInterpolationWorldTransform(tr);
  re.body->setInterpolationLinearVelocity(btVector3(0, 0, 0));
  re.body->setInterpolationAngularVelocity(btVector3(0, 0, 0));
}

BULLET_MMD_API void
bullet_set_target_transform(BulletEngine *engine, int rbIndex, float posX,
                            float posY, float posZ, float rotEulerX,
                            float rotEulerY, float rotEulerZ) {
  if (!engine || rbIndex < 0 ||
      rbIndex >= static_cast<int>(engine->rigidBodies.size()))
    return;
  auto &re = engine->rigidBodies[rbIndex];
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

BULLET_MMD_API void
bullet_get_rigidbody_transform(BulletEngine *engine, int rbIndex,
                               float *outPosX, float *outPosY, float *outPosZ,
                               float *outRotX, float *outRotY, float *outRotZ,
                               float *outRotW) {
  if (!engine || rbIndex < 0 ||
      rbIndex >= static_cast<int>(engine->rigidBodies.size()))
    return;
  auto &re = engine->rigidBodies[rbIndex];
  if (!re.body)
    return;

  btTransform tr;
  if (re.motionState) {
    re.motionState->getWorldTransform(tr);
  } else {
    tr = re.body->getWorldTransform();
  }

  const btVector3 &pos = tr.getOrigin();
  const btQuaternion &rot = tr.getRotation();

  if (outPosX)
    *outPosX = pos.x();
  if (outPosY)
    *outPosY = pos.y();
  if (outPosZ)
    *outPosZ = pos.z();

  if (outRotX)
    *outRotX = rot.x();
  if (outRotY)
    *outRotY = rot.y();
  if (outRotZ)
    *outRotZ = rot.z();
  if (outRotW)
    *outRotW = rot.w();
}

BULLET_MMD_API int
bullet_add_joint(BulletEngine *engine, int rbAIndex, int rbBIndex, float posX,
                 float posY, float posZ, float rotEulerX, float rotEulerY,
                 float rotEulerZ, float posMinX, float posMinY, float posMinZ,
                 float posMaxX, float posMaxY, float posMaxZ, float rotMinX,
                 float rotMinY, float rotMinZ, float rotMaxX, float rotMaxY,
                 float rotMaxZ, float springPosX, float springPosY,
                 float springPosZ, float springRotX, float springRotY,
                 float springRotZ, int jointType) {
  if (!engine || !engine->world)
    return -1;
  if (rbAIndex < 0 || rbAIndex >= static_cast<int>(engine->rigidBodies.size()))
    return -1;
  if (rbBIndex < 0 || rbBIndex >= static_cast<int>(engine->rigidBodies.size()))
    return -1;

  btRigidBody *rbA = engine->rigidBodies[rbAIndex].body;
  btRigidBody *rbB = engine->rigidBodies[rbBIndex].body;
  if (!rbA || !rbB)
    return -1;

  // ジョイントのワールドトランスフォーム
  btTransform jointWorld;
  jointWorld.setIdentity();
  jointWorld.setOrigin(btVector3(posX, posY, posZ));
  jointWorld.setRotation(eulerToQuaternionXYZ(rotEulerX, rotEulerY, rotEulerZ));

  // 各剛体のローカル座標系におけるジョイントトランスフォーム
  btTransform frameInA = rbA->getWorldTransform().inverse() * jointWorld;
  btTransform frameInB = rbB->getWorldTransform().inverse() * jointWorld;

  // PMX共通仕様に基づく制限値の正規化:
  // A < B : 範囲で制限 (lower = A, upper = B)
  // A == B : 指定値でロック (lower = A, upper = A)
  // A > B : 制限なし・フリー (Bullet公式仕様: lower > upper でフリー解放)
  btVector3 linLower, linUpper;
  linLower.setX((posMinX > posMaxX) ? 1.0f : posMinX);
  linUpper.setX((posMinX > posMaxX) ? 0.0f : posMaxX);
  linLower.setY((posMinY > posMaxY) ? 1.0f : posMinY);
  linUpper.setY((posMinY > posMaxY) ? 0.0f : posMaxY);
  linLower.setZ((posMinZ > posMaxZ) ? 1.0f : posMinZ);
  linUpper.setZ((posMinZ > posMaxZ) ? 0.0f : posMaxZ);

  btVector3 angLower, angUpper;
  angLower.setX((rotMinX > rotMaxX) ? 1.0f : rotMinX);
  angUpper.setX((rotMinX > rotMaxX) ? -1.0f : rotMaxX);
  angLower.setY((rotMinY > rotMaxY) ? 1.0f : rotMinY);
  angUpper.setY((rotMinY > rotMaxY) ? -1.0f : rotMaxY);
  angLower.setZ((rotMinZ > rotMaxZ) ? 1.0f : rotMinZ);
  angUpper.setZ((rotMinZ > rotMaxZ) ? -1.0f : rotMaxZ);

  btTypedConstraint *constraint = nullptr;
  btGeneric6DofSpringConstraint *springConstraint = nullptr;

  // PMX 2.1 拡張ジョイントタイプマッピング
  if (jointType == 1) {
    // タイプ1: 6DOF (バネなし)
    btGeneric6DofConstraint *dof =
        new btGeneric6DofConstraint(*rbA, *rbB, frameInA, frameInB, true);
    dof->setLinearLowerLimit(linLower);
    dof->setLinearUpperLimit(linUpper);
    dof->setAngularLowerLimit(angLower);
    dof->setAngularUpperLimit(angUpper);
    constraint = dof;
  } else if (jointType == 2) {
    // タイプ2: Point to Point (P2P ボールジョイント)
    btPoint2PointConstraint *p2p = new btPoint2PointConstraint(
        *rbA, *rbB, frameInA.getOrigin(), frameInB.getOrigin());
    constraint = p2p;
  } else if (jointType == 3) {
    // タイプ3: ConeTwist (円錐・ねじれスパン制限)
    btConeTwistConstraint *cone =
        new btConeTwistConstraint(*rbA, *rbB, frameInA, frameInB);
    float swingSpan1 = (rotMinY > rotMaxY)
                           ? SIMD_PI
                           : (std::max)(std::abs(rotMinY), std::abs(rotMaxY));
    float swingSpan2 = (rotMinZ > rotMaxZ)
                           ? SIMD_PI
                           : (std::max)(std::abs(rotMinZ), std::abs(rotMaxZ));
    float twistSpan = (rotMinX > rotMaxX)
                          ? SIMD_PI
                          : (std::max)(std::abs(rotMinX), std::abs(rotMaxX));
    cone->setLimit(swingSpan1, swingSpan2, twistSpan, 1.0f, 0.3f, 1.0f);
    constraint = cone;
  } else if (jointType == 5) {
    // タイプ5: Slider (スライダー)
    btSliderConstraint *slider =
        new btSliderConstraint(*rbA, *rbB, frameInA, frameInB, true);
    if (posMinX > posMaxX) {
      slider->setLowerLinLimit(1.0f);
      slider->setUpperLinLimit(0.0f);
    } else {
      slider->setLowerLinLimit(posMinX);
      slider->setUpperLinLimit(posMaxX);
    }
    if (rotMinX > rotMaxX) {
      slider->setLowerAngLimit(1.0f);
      slider->setUpperAngLimit(-1.0f);
    } else {
      slider->setLowerAngLimit(rotMinX);
      slider->setUpperAngLimit(rotMaxX);
    }
    constraint = slider;
  } else if (jointType == 6) {
    // タイプ6: Hinge (1軸回転ヒンジ)
    btHingeConstraint *hinge =
        new btHingeConstraint(*rbA, *rbB, frameInA, frameInB, true);
    if (rotMinZ > rotMaxZ) {
      hinge->setLimit(1.0f, -1.0f); // フリー
    } else {
      hinge->setLimit(rotMinZ, rotMaxZ, 0.9f, 0.3f, 1.0f);
    }
    constraint = hinge;
  } else {
    // タイプ0 (デフォルト) およびタイプ4: 6DOF スプリングコンストレイント
    btGeneric6DofSpringConstraint *spring =
        new btGeneric6DofSpringConstraint(*rbA, *rbB, frameInA, frameInB, true);
    spring->setLinearLowerLimit(linLower);
    spring->setLinearUpperLimit(linUpper);
    spring->setAngularLowerLimit(angLower);
    spring->setAngularUpperLimit(angUpper);

    float springParams[6] = {springPosX, springPosY, springPosZ,
                             springRotX, springRotY, springRotZ};

    for (int i = 0; i < 6; ++i) {
      if (springParams[i] != 0.0f) {
        spring->enableSpring(i, true);
        spring->setStiffness(i, springParams[i]);
        spring->setDamping(i, 1.0f);
      }
    }
    spring->setEquilibriumPoint();
    constraint = spring;
    springConstraint = spring;
  }

  engine->world->addConstraint(constraint, true);

  JointEntry entry;
  entry.jointType = jointType;
  entry.constraint = constraint;
  entry.spring = springConstraint;

  int jointIdx = static_cast<int>(engine->joints.size());
  engine->joints.push_back(entry);
  return jointIdx;
}

BULLET_MMD_API void bullet_step_simulation(BulletEngine *engine, float dt,
                                           int maxSubSteps,
                                           float fixedTimeStep) {
  if (!engine || !engine->world)
    return;

  // Aligned 剛体 (タイプ2) の位置補正と重力遮断
  for (auto &re : engine->rigidBodies) {
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

  // Bullet 物理ワールドのシミュレーション進行
  engine->world->stepSimulation(dt, maxSubSteps, fixedTimeStep);

  // Aligned 剛体のシミュレーション後位置再固定
  for (auto &re : engine->rigidBodies) {
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

BULLET_MMD_API void bullet_reset_velocities(BulletEngine *engine) {
  if (!engine || !engine->world)
    return;
  for (auto &re : engine->rigidBodies) {
    if (!re.body)
      continue;
    re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->setInterpolationLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->setInterpolationAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->clearForces();
  }
}

BULLET_MMD_API void bullet_reset_constraints(BulletEngine *engine) {
  if (!engine || !engine->world)
    return;
  // PMX設計時の平衡点を保護するため、動的姿勢での平衡点再設定は行わない
}

BULLET_MMD_API void bullet_relax_penetration(BulletEngine *engine, int steps,
                                             float relaxationDamping) {
  if (!engine || !engine->world || steps <= 0)
    return;

  // 重力を一時退避してゼロに設定
  btVector3 originalGravity = engine->world->getGravity();
  engine->world->setGravity(btVector3(0.0f, 0.0f, 0.0f));

  // 動的剛体の元のダンピングを保存し、高ダンピングを一時適用
  std::vector<std::pair<float, float>> originalDamping;
  originalDamping.reserve(engine->rigidBodies.size());

  for (auto &re : engine->rigidBodies) {
    if (!re.body) {
      originalDamping.push_back({0.0f, 0.0f});
      continue;
    }
    originalDamping.push_back(
        {re.body->getLinearDamping(), re.body->getAngularDamping()});

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
    for (auto &re : engine->rigidBodies) {
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
    auto &re = engine->rigidBodies[i];
    if (!re.body)
      continue;
    re.body->setDamping(originalDamping[i].first, originalDamping[i].second);
    re.body->setLinearVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->setAngularVelocity(btVector3(0.0f, 0.0f, 0.0f));
    re.body->clearForces();
  }
  engine->world->setGravity(originalGravity);
}

BULLET_MMD_API void bullet_set_floor_plane(BulletEngine *engine, int enable,
                                           float yHeight, float friction,
                                           float restitution) {
  if (!engine)
    return;
  engine->setFloorPlane(enable != 0, yHeight, friction, restitution);
}
