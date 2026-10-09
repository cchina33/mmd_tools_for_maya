#include "xpbd_engine.h"
#include <cmath>
#include <algorithm>

namespace xpbd {

XpbdEngine::XpbdEngine() {
    rigidBodies_.reserve(256);
    joints_.reserve(256);
}

void XpbdEngine::reset() {
    for (auto& rb : rigidBodies_) {
        rb.linearVelocity = {0.0f, 0.0f, 0.0f};
        rb.angularVelocity = {0.0f, 0.0f, 0.0f};
        rb.prevPosition = rb.position;
        rb.prevRotation = rb.rotation;
    }
    for (auto& j : joints_) {
        j.totalPosLambda = {0.0f, 0.0f, 0.0f};
        j.totalRotLambda = {0.0f, 0.0f, 0.0f};
    }
}

void XpbdEngine::clear() {
    rigidBodies_.clear();
    joints_.clear();
}

int XpbdEngine::addRigidBody(const RigidBody& rb) {
    int id = static_cast<int>(rigidBodies_.size());
    RigidBody copy = rb;
    copy.id = id;
    copy.updateInertia();
    copy.prevPosition = copy.position;
    copy.prevRotation = copy.rotation;
    copy.targetPosition = copy.position;
    copy.targetRotation = copy.rotation;
    rigidBodies_.push_back(copy);
    return id;
}

RigidBody* XpbdEngine::getRigidBody(int index) {
    if (index >= 0 && index < static_cast<int>(rigidBodies_.size())) {
        return &rigidBodies_[index];
    }
    return nullptr;
}

void XpbdEngine::setRigidBodyTransform(int index, const Vec3& pos, const Quat& rot) {
    RigidBody* rb = getRigidBody(index);
    if (!rb) return;

    rb->targetPosition = pos;
    rb->targetRotation = rot;
}

int XpbdEngine::addJoint(const Joint6DOF& joint) {
    int id = static_cast<int>(joints_.size());
    Joint6DOF copy = joint;
    copy.id = id;

    // 剛体A、Bの初期姿勢に対するローカルアンカーとローカル回転を自動算出
    RigidBody* rbA = getRigidBody(joint.bodyA);
    RigidBody* rbB = getRigidBody(joint.bodyB);

    if (rbA) {
        Quat invRotA = rbA->rotation.inverse();
        copy.localAnchorA = invRotA.rotate(joint.jointPosition - rbA->position);
        copy.localRotA = invRotA * joint.jointRotation;
    }
    if (rbB) {
        Quat invRotB = rbB->rotation.inverse();
        copy.localAnchorB = invRotB.rotate(joint.jointPosition - rbB->position);
        copy.localRotB = invRotB * joint.jointRotation;
    }

    joints_.push_back(copy);
    return id;
}

Joint6DOF* XpbdEngine::getJoint(int index) {
    if (index >= 0 && index < static_cast<int>(joints_.size())) {
        return &joints_[index];
    }
    return nullptr;
}

void XpbdEngine::stepSimulation(float dt, int substeps) {
    if (dt <= 0.0f || substeps <= 0) return;

    // 各フレームの開始時に全剛体の現在姿勢を開始姿勢として記録
    for (auto& rb : rigidBodies_) {
        rb.startPosition = rb.position;
        rb.startRotation = rb.rotation;
    }

    float h = dt / static_cast<float>(substeps);
    for (int step = 0; step < substeps; ++step) {
        float alpha = static_cast<float>(step + 1) / static_cast<float>(substeps);
        subStep(h, alpha);
    }

    // ステップ完了後: KinematicおよびAligned剛体の位置をボーン目標位置に100%完全固定
    for (auto& rb : rigidBodies_) {
        if (rb.physicsMode == PhysicsMode::Kinematic || rb.physicsMode == PhysicsMode::Aligned) {
            rb.position = rb.targetPosition;
        }
    }
}

void XpbdEngine::subStep(float h, float alpha) {
    // 予測ステップ: 外力（重力）の適用と位置・姿勢の仮更新
    for (auto& rb : rigidBodies_) {
        if (rb.physicsMode == PhysicsMode::Kinematic) {
            rb.prevPosition = rb.position;
            rb.prevRotation = rb.rotation;
            // サブステップ補間: 前フレームから目標フレームへ滑らかに移動しすり抜けを防止
            rb.position = rb.startPosition + (rb.targetPosition - rb.startPosition) * alpha;
            rb.rotation = Quat::slerp(rb.startRotation, rb.targetRotation, alpha);
            continue;
        }

        // 速度減衰と外力の加算
        if (rb.physicsMode != PhysicsMode::Aligned) {
            rb.linearVelocity += gravity_ * h;
            rb.linearVelocity *= std::max(0.0f, 1.0f - rb.linearDamping * h);
        } else {
            rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
        }
        rb.angularVelocity *= std::max(0.0f, 1.0f - rb.angularDamping * h);

        // 前状態の保存
        rb.prevPosition = rb.position;
        rb.prevRotation = rb.rotation;

        // 速度上限クランプ (暴走防止)
        constexpr float MAX_SPEED = 400.0f;
        float spdSq = rb.linearVelocity.lengthSq();
        if (spdSq > MAX_SPEED * MAX_SPEED) {
            rb.linearVelocity = rb.linearVelocity.normalized() * MAX_SPEED;
        }

        constexpr float MAX_ANG_SPEED = 30.0f;
        float angSq = rb.angularVelocity.lengthSq();
        if (angSq > MAX_ANG_SPEED * MAX_ANG_SPEED) {
            rb.angularVelocity = rb.angularVelocity.normalized() * MAX_ANG_SPEED;
        }

        // 位置の予測 (Aligned剛体は目標位置へ滑らかに補間、Dynamic剛体は慣性移動)
        if (rb.physicsMode == PhysicsMode::Aligned) {
            rb.position = rb.startPosition + (rb.targetPosition - rb.startPosition) * alpha;
        } else {
            rb.position += rb.linearVelocity * h;
        }

        // 姿勢の予測 (クォータニオン積分)
        Quat spin(rb.angularVelocity.x, rb.angularVelocity.y, rb.angularVelocity.z, 0.0f);
        rb.rotation = (rb.rotation + spin * rb.rotation * (0.5f * h)).normalized();
    }

    // 制約解消ループ (ジョイント & 衝突)
    solveJointConstraints(h);
    solveCollisions(h);

    // 速度更新ステップ (位置の変化量から速度を逆算)
    float invH = 1.0f / h;
    for (auto& rb : rigidBodies_) {
        if (rb.physicsMode == PhysicsMode::Kinematic) {
            rb.linearVelocity = (rb.position - rb.prevPosition) * invH;
            Quat dq = rb.rotation * rb.prevRotation.inverse();
            rb.angularVelocity = Vec3(dq.x, dq.y, dq.z) * (2.0f * invH);
            continue;
        }

        rb.linearVelocity = (rb.position - rb.prevPosition) * invH;

        // 速度上限クランプ (ステップ間)
        constexpr float MAX_SPEED = 400.0f;
        float spdSq = rb.linearVelocity.lengthSq();
        if (spdSq > MAX_SPEED * MAX_SPEED) {
            rb.linearVelocity = rb.linearVelocity.normalized() * MAX_SPEED;
        }

        // クォータニオン変位から角速度を算出
        Quat dq = rb.rotation * rb.prevRotation.inverse();
        if (dq.w < 0.0f) {
            dq = dq * -1.0f;
        }
        rb.angularVelocity = Vec3(dq.x, dq.y, dq.z) * (2.0f * invH);

        constexpr float MAX_ANG_SPEED = 30.0f;
        float angSq = rb.angularVelocity.lengthSq();
        if (angSq > MAX_ANG_SPEED * MAX_ANG_SPEED) {
            rb.angularVelocity = rb.angularVelocity.normalized() * MAX_ANG_SPEED;
        }

        // 物理+ボーン位置合わせモードの処理 (MMD仕様: 位置はボーンに100%固定、回転のみ物理演算)
        if (rb.physicsMode == PhysicsMode::Aligned) {
            rb.position = rb.startPosition + (rb.targetPosition - rb.startPosition) * alpha;
            rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
        }
    }
}

// 6自由度ジョイント制約の解決 (XPBD法)
void XpbdEngine::solveJointConstraints(float h) {
    for (auto& joint : joints_) {
        solveJoint(joint, h);
    }
}

void XpbdEngine::solveJoint(Joint6DOF& joint, float h) {
    RigidBody* rbA = getRigidBody(joint.bodyA);
    RigidBody* rbB = getRigidBody(joint.bodyB);
    if (!rbA || !rbB) return;
    if (rbA->invMass == 0.0f && rbB->invMass == 0.0f) return;

    // ワールド空間での各剛体アンカー点
    Vec3 rA = rbA->rotation.rotate(joint.localAnchorA);
    Vec3 rB = rbB->rotation.rotate(joint.localAnchorB);
    Vec3 pA = rbA->position + rA;
    Vec3 pB = rbB->position + rB;

    // ジョイント基準回転フレーム
    Quat qJointA = rbA->rotation * joint.localRotA;
    Mat3 jointRotMat = qJointA.toRotationMatrix();

    // 1. 並進変位の解消 (移動制限・バネ)
    Vec3 diffWorld = pB - pA;
    Vec3 diffJoint = jointRotMat.transposed() * diffWorld;

    for (int axis = 0; axis < 3; ++axis) {
        float val = (axis == 0) ? diffJoint.x : (axis == 1) ? diffJoint.y : diffJoint.z;
        float minL = (axis == 0) ? joint.linearLimitMin.x : (axis == 1) ? joint.linearLimitMin.y : joint.linearLimitMin.z;
        float maxL = (axis == 0) ? joint.linearLimitMax.x : (axis == 1) ? joint.linearLimitMax.y : joint.linearLimitMax.z;
        float springK = (axis == 0) ? joint.linearSpring.x : (axis == 1) ? joint.linearSpring.y : joint.linearSpring.z;

        // 移動制限 (ハードリミット)
        float limitViolation = 0.0f;
        if (val < minL) {
            limitViolation = val - minL;
        } else if (val > maxL) {
            limitViolation = val - maxL;
        }

        // 移動バネ復元力 (変位 0 への復元)
        float springViolation = (springK > 0.0f) ? val : 0.0f;
        float violation = limitViolation + springViolation;

        if (std::abs(violation) > EPSILON) {
            Vec3 axisWorld = (axis == 0) ? Vec3(jointRotMat.m[0][0], jointRotMat.m[1][0], jointRotMat.m[2][0]) :
                             (axis == 1) ? Vec3(jointRotMat.m[0][1], jointRotMat.m[1][1], jointRotMat.m[2][1]) :
                                           Vec3(jointRotMat.m[0][2], jointRotMat.m[1][2], jointRotMat.m[2][2]);

            // 実効質量の計算 (Aligned剛体は位置固定のため並進の逆質量は0)
            Vec3 crA = rA.cross(axisWorld);
            Vec3 crB = rB.cross(axisWorld);
            float invMA = (rbA->physicsMode == PhysicsMode::Aligned) ? 0.0f : rbA->invMass;
            float invMB = (rbB->physicsMode == PhysicsMode::Aligned) ? 0.0f : rbB->invMass;
            float wA = invMA + crA.dot(rbA->getInvInertiaWorld() * crA);
            float wB = invMB + crB.dot(rbB->getInvInertiaWorld() * crB);
            float wSum = wA + wB;

            // コンプライアンス（XPBDバネ柔軟性: ハードリミット違反時はコンプライアンス0で完全固定）
            float compliance = (limitViolation == 0.0f && springK > 0.0f) ? (1.0f / (springK * h * h + 1e-4f)) : 0.0f;
            float dLambda = -violation / (wSum + compliance + EPSILON);

            // ハードリミット違反時はジョイント外れを防ぐためクランプ幅を大幅に拡大
            float maxImpulse = (limitViolation != 0.0f) ? 5000.0f : 200.0f;
            dLambda = std::clamp(dLambda, -maxImpulse, maxImpulse);

            Vec3 impulse = axisWorld * dLambda;
            if (invMA > 0.0f) {
                rbA->position -= impulse * invMA;
            }
            if (rbA->invMass > 0.0f) {
                Vec3 dRot = rbA->getInvInertiaWorld() * rA.cross(-impulse);
                float lenRot = dRot.length();
                if (lenRot > 0.5f) dRot = dRot * (0.5f / lenRot);
                Quat dq(dRot.x, dRot.y, dRot.z, 0.0f);
                rbA->rotation = (rbA->rotation + dq * rbA->rotation * 0.5f).normalized();
            }
            if (invMB > 0.0f) {
                rbB->position += impulse * invMB;
            }
            if (rbB->invMass > 0.0f) {
                Vec3 dRot = rbB->getInvInertiaWorld() * rB.cross(impulse);
                float lenRot = dRot.length();
                if (lenRot > 0.5f) dRot = dRot * (0.5f / lenRot);
                Quat dq(dRot.x, dRot.y, dRot.z, 0.0f);
                rbB->rotation = (rbB->rotation + dq * rbB->rotation * 0.5f).normalized();
            }
        }
    }

    // 回転変位の解消 (角度制限・回転バネ)
    Quat qJointB = rbB->rotation * joint.localRotB;
    Quat qRel = qJointA.inverse() * qJointB;
    if (qRel.w < 0.0f) qRel = qRel * -1.0f;

    Vec3 relEuler = qRel.toEulerXYZ();
    for (int axis = 0; axis < 3; ++axis) {
        float angle = (axis == 0) ? relEuler.x : (axis == 1) ? relEuler.y : relEuler.z;
        float minA = (axis == 0) ? joint.angularLimitMin.x : (axis == 1) ? joint.angularLimitMin.y : joint.angularLimitMin.z;
        float maxA = (axis == 0) ? joint.angularLimitMax.x : (axis == 1) ? joint.angularLimitMax.y : joint.angularLimitMax.z;
        float springK = (axis == 0) ? joint.angularSpring.x : (axis == 1) ? joint.angularSpring.y : joint.angularSpring.z;

        // 角度制限 (ハードリミット)
        float limitViolation = 0.0f;
        if (angle < minA) {
            limitViolation = Quat::normalizeAngle(angle - minA);
        } else if (angle > maxA) {
            limitViolation = Quat::normalizeAngle(angle - maxA);
        }

        // 回転バネ復元力 (初期姿勢 0度 への引き戻し力)
        float springViolation = (springK > 0.0f) ? Quat::normalizeAngle(angle) : 0.0f;
        float violation = limitViolation + springViolation;

        if (std::abs(violation) > EPSILON) {
            Vec3 axisWorld = (axis == 0) ? Vec3(jointRotMat.m[0][0], jointRotMat.m[1][0], jointRotMat.m[2][0]) :
                             (axis == 1) ? Vec3(jointRotMat.m[0][1], jointRotMat.m[1][1], jointRotMat.m[2][1]) :
                                           Vec3(jointRotMat.m[0][2], jointRotMat.m[1][2], jointRotMat.m[2][2]);

            float wA = axisWorld.dot(rbA->getInvInertiaWorld() * axisWorld);
            float wB = axisWorld.dot(rbB->getInvInertiaWorld() * axisWorld);
            // ハードリミット超過時はコンプライアンス0で最優先引き戻し
            float compliance = (limitViolation == 0.0f && springK > 0.0f) ? (1.0f / (springK * h * h + 1e-4f)) : 0.0f;
            float dLambda = -violation / (wA + wB + compliance + EPSILON);

            // 回転インパルスの安全上限クランプ
            dLambda = std::clamp(dLambda, -10.0f, 10.0f);

            Vec3 rotImpulse = axisWorld * dLambda;
            constexpr float MAX_ROT_STEP = 0.15f;
            if (rbA->invMass > 0.0f) {
                Vec3 dRot = rbA->getInvInertiaWorld() * (-rotImpulse);
                float lenRot = dRot.length();
                if (lenRot > MAX_ROT_STEP) dRot = dRot * (MAX_ROT_STEP / lenRot);
                Quat dq(dRot.x, dRot.y, dRot.z, 0.0f);
                rbA->rotation = (rbA->rotation + dq * rbA->rotation * 0.5f).normalized();
            }
            if (rbB->invMass > 0.0f) {
                Vec3 dRot = rbB->getInvInertiaWorld() * rotImpulse;
                float lenRot = dRot.length();
                if (lenRot > MAX_ROT_STEP) dRot = dRot * (MAX_ROT_STEP / lenRot);
                Quat dq(dRot.x, dRot.y, dRot.z, 0.0f);
                rbB->rotation = (rbB->rotation + dq * rbB->rotation * 0.5f).normalized();
            }
        }
    }

    // ジョイント間の相対速度・相対角速度に対するダンピング（高周波ジッター・あらぶりを抑制）
    Vec3 velA = rbA->linearVelocity + rbA->angularVelocity.cross(rA);
    Vec3 velB = rbB->linearVelocity + rbB->angularVelocity.cross(rB);
    Vec3 relVel = velB - velA;
    float dampFactor = std::min(0.8f, 15.0f * h);
    Vec3 dampImpulse = relVel * dampFactor;
    float totalInvM = rbA->invMass + rbB->invMass;
    if (totalInvM > EPSILON) {
        if (rbA->physicsMode == PhysicsMode::Dynamic) {
            rbA->linearVelocity += dampImpulse * (rbA->invMass / totalInvM);
        }
        if (rbB->physicsMode == PhysicsMode::Dynamic) {
            rbB->linearVelocity -= dampImpulse * (rbB->invMass / totalInvM);
        }
    }

    Vec3 relAngVel = rbB->angularVelocity - rbA->angularVelocity;
    float angDampFactor = std::min(0.8f, 20.0f * h);
    Vec3 dampAngImpulse = relAngVel * angDampFactor;
    if (rbA->invMass > 0.0f && rbA->physicsMode == PhysicsMode::Dynamic) {
        rbA->angularVelocity += dampAngImpulse * 0.5f;
    }
    if (rbB->invMass > 0.0f && rbB->physicsMode == PhysicsMode::Dynamic) {
        rbB->angularVelocity -= dampAngImpulse * 0.5f;
    }
}

// 剛体同士の衝突判定・分離補正
void XpbdEngine::solveCollisions(float h) {
    int count = static_cast<int>(rigidBodies_.size());
    for (int i = 0; i < count; ++i) {
        for (int j = i + 1; j < count; ++j) {
            RigidBody& a = rigidBodies_[i];
            RigidBody& b = rigidBodies_[j];

            // 衝突グループ・マスクチェック (PMX/Bullet仕様: 相手のグループビットが双方向で立っている場合のみ衝突)
            if ((a.collisionMask & (1 << b.group)) == 0 || (b.collisionMask & (1 << a.group)) == 0) {
                continue;
            }

            // 両方が Kinematic の場合は衝突処理不要
            if (a.invMass == 0.0f && b.invMass == 0.0f) {
                continue;
            }

            // Joint で直接接続された剛体ペアは衝突判定から除外 (反発と引張のケンカを遮断)
            bool isJointLinked = false;
            for (const auto& joint : joints_) {
                if ((joint.bodyA == a.id && joint.bodyB == b.id) || (joint.bodyA == b.id && joint.bodyB == a.id)) {
                    isJointLinked = true;
                    break;
                }
            }
            if (isJointLinked) {
                continue;
            }

            // 形状別の衝突判定
            if (a.shapeType == ShapeType::Sphere && b.shapeType == ShapeType::Sphere) {
                checkCollisionSphereSphere(a, b, h);
            } else if (a.shapeType == ShapeType::Sphere && b.shapeType == ShapeType::Capsule) {
                checkCollisionSphereCapsule(a, b, h);
            } else if (a.shapeType == ShapeType::Capsule && b.shapeType == ShapeType::Sphere) {
                checkCollisionSphereCapsule(b, a, h);
            } else if (a.shapeType == ShapeType::Capsule && b.shapeType == ShapeType::Capsule) {
                checkCollisionCapsuleCapsule(a, b, h);
            } else if (a.shapeType == ShapeType::Sphere && b.shapeType == ShapeType::Box) {
                checkCollisionSphereBox(a, b, h);
            } else if (a.shapeType == ShapeType::Box && b.shapeType == ShapeType::Sphere) {
                checkCollisionSphereBox(b, a, h);
            } else if (a.shapeType == ShapeType::Capsule && b.shapeType == ShapeType::Box) {
                checkCollisionCapsuleBox(a, b, h);
            } else if (a.shapeType == ShapeType::Box && b.shapeType == ShapeType::Capsule) {
                checkCollisionCapsuleBox(b, a, h);
            } else if (a.shapeType == ShapeType::Box && b.shapeType == ShapeType::Box) {
                checkCollisionBoxBox(a, b, h);
            }
        }
    }
}

// 剛体同士の接触拘束をXPBD法により解決 (位置補正および回転トルク補正)
void XpbdEngine::resolveContact(RigidBody& a, RigidBody& b, const Vec3& contactPoint, const Vec3& normal, float penetration, float h) {
    if (penetration <= EPSILON) return;

    // normal は a から b へ向かう方向 (a を -normal, b を +normal に補正)
    Vec3 rA = contactPoint - a.position;
    Vec3 rB = contactPoint - b.position;

    // アームベクトルと法線の外積
    Vec3 crA = rA.cross(normal);
    Vec3 crB = rB.cross(normal);

    // 一般化逆質量の計算
    float invMA = (a.physicsMode == PhysicsMode::Aligned) ? 0.0f : a.invMass;
    float invMB = (b.physicsMode == PhysicsMode::Aligned) ? 0.0f : b.invMass;
    float wA = invMA;
    if (a.invMass > 0.0f) {
        wA += crA.dot(a.getInvInertiaWorld() * crA);
    }
    float wB = invMB;
    if (b.invMass > 0.0f) {
        wB += crB.dot(b.getInvInertiaWorld() * crB);
    }

    float wSum = wA + wB;
    if (wSum <= EPSILON) return;

    // XPBD法による接触インパルス
    float impulseMag = penetration / wSum;
    Vec3 impulse = normal * impulseMag;

    // 位置補正 (Aligned剛体は位置固定)
    if (invMA > 0.0f) {
        a.position -= impulse * invMA;
    }
    if (invMB > 0.0f) {
        b.position += impulse * invMB;
    }

    // トルクによる回転姿勢の補正 (角変位の安全上限クランプ付き)
    constexpr float MAX_ANG_CORRECTION = 0.5f;
    if (a.invMass > 0.0f) {
        Vec3 torqueImpulseA = rA.cross(impulse * -1.0f);
        Vec3 dThetaA = a.getInvInertiaWorld() * torqueImpulseA;
        float dThetaLen = dThetaA.length();
        if (dThetaLen > MAX_ANG_CORRECTION) {
            dThetaA = dThetaA * (MAX_ANG_CORRECTION / dThetaLen);
        }
        Quat dqA(dThetaA.x * 0.5f, dThetaA.y * 0.5f, dThetaA.z * 0.5f, 0.0f);
        a.rotation = (a.rotation + dqA * a.rotation).normalized();
    }
    if (b.invMass > 0.0f) {
        Vec3 torqueImpulseB = rB.cross(impulse);
        Vec3 dThetaB = b.getInvInertiaWorld() * torqueImpulseB;
        float dThetaLen = dThetaB.length();
        if (dThetaLen > MAX_ANG_CORRECTION) {
            dThetaB = dThetaB * (MAX_ANG_CORRECTION / dThetaLen);
        }
        Quat dqB(dThetaB.x * 0.5f, dThetaB.y * 0.5f, dThetaB.z * 0.5f, 0.0f);
        b.rotation = (b.rotation + dqB * b.rotation).normalized();
    }
}

// 球 vs 球の衝突
void XpbdEngine::checkCollisionSphereSphere(RigidBody& a, RigidBody& b, float h) {
    Vec3 diff = b.position - a.position;
    float distSq = diff.lengthSq();
    // すり抜け防止の接触マージン
    constexpr float MARGIN_FACTOR = 0.05f;
    float radiusSum = (a.size.x + b.size.x) * (1.0f + MARGIN_FACTOR);

    if (distSq < radiusSum * radiusSum && distSq > EPSILON) {
        float dist = std::sqrt(distSq);
        Vec3 normal = diff / dist;
        float penetration = radiusSum - dist;
        Vec3 contactPt = a.position + normal * a.size.x;
        resolveContact(a, b, contactPt, normal, penetration, h);
    }
}

// 球 vs カプセルの衝突
void XpbdEngine::checkCollisionSphereCapsule(RigidBody& sphere, RigidBody& capsule, float h) {
    // カプセルの中心軸セグメント (ローカルY軸方向)
    Vec3 capAxis = capsule.rotation.rotate(Vec3(0.0f, 1.0f, 0.0f));
    float halfHeight = capsule.size.y * 0.5f;
    Vec3 p0 = capsule.position - capAxis * halfHeight;
    Vec3 p1 = capsule.position + capAxis * halfHeight;

    // 球の中心からセグメントへの最近接点
    Vec3 d = p1 - p0;
    float lenSq = d.lengthSq();
    float t = (lenSq > EPSILON) ? (sphere.position - p0).dot(d) / lenSq : 0.0f;
    t = std::max(0.0f, std::min(1.0f, t));
    Vec3 closestOnCap = p0 + d * t;

    Vec3 diff = sphere.position - closestOnCap;
    float distSq = diff.lengthSq();
    constexpr float MARGIN_FACTOR = 0.05f;
    float radiusSum = (sphere.size.x + capsule.size.x) * (1.0f + MARGIN_FACTOR);

    if (distSq < radiusSum * radiusSum && distSq > EPSILON) {
        float dist = std::sqrt(distSq);
        Vec3 normal = diff / dist; // capsuleからsphereに向かう法線
        float penetration = radiusSum - dist;
        Vec3 contactPt = closestOnCap + normal * capsule.size.x;
        resolveContact(capsule, sphere, contactPt, normal, penetration, h);
    }
}

// カプセル vs カプセルの衝突
void XpbdEngine::checkCollisionCapsuleCapsule(RigidBody& capA, RigidBody& capB, float h) {
    Vec3 axisA = capA.rotation.rotate(Vec3(0.0f, 1.0f, 0.0f));
    Vec3 axisB = capB.rotation.rotate(Vec3(0.0f, 1.0f, 0.0f));
    float hA = capA.size.y * 0.5f;
    float hB = capB.size.y * 0.5f;

    Vec3 p1 = capA.position - axisA * hA;
    Vec3 q1 = capA.position + axisA * hA;
    Vec3 p2 = capB.position - axisB * hB;
    Vec3 q2 = capB.position + axisB * hB;

    Vec3 d1 = q1 - p1;
    Vec3 d2 = q2 - p2;
    Vec3 r = p1 - p2;

    float a = d1.lengthSq();
    float e = d2.lengthSq();
    float f = d2.dot(r);

    float s = 0.0f, t = 0.0f;
    if (a <= EPSILON && e <= EPSILON) {
        s = t = 0.0f;
    } else if (a <= EPSILON) {
        s = 0.0f;
        t = std::clamp(f / e, 0.0f, 1.0f);
    } else {
        float c = d1.dot(r);
        if (e <= EPSILON) {
            t = 0.0f;
            s = std::clamp(-c / a, 0.0f, 1.0f);
        } else {
            float b = d1.dot(d2);
            float denom = a * e - b * b;
            if (denom > EPSILON) {
                s = std::clamp((b * f - c * e) / denom, 0.0f, 1.0f);
            } else {
                s = 0.0f;
            }
            t = (b * s + f) / e;
            if (t < 0.0f) {
                t = 0.0f;
                s = std::clamp(-c / a, 0.0f, 1.0f);
            } else if (t > 1.0f) {
                t = 1.0f;
                s = std::clamp((b - c) / a, 0.0f, 1.0f);
            }
        }
    }

    Vec3 closestA = p1 + d1 * s;
    Vec3 closestB = p2 + d2 * t;
    Vec3 diff = closestB - closestA;
    float distSq = diff.lengthSq();
    constexpr float MARGIN_FACTOR = 0.05f;
    float radiusSum = (capA.size.x + capB.size.x) * (1.0f + MARGIN_FACTOR);

    if (distSq < radiusSum * radiusSum && distSq > EPSILON) {
        float dist = std::sqrt(distSq);
        Vec3 normal = diff / dist; // capAからcapBに向かう法線
        float penetration = radiusSum - dist;
        Vec3 contactPt = closestA + normal * capA.size.x;
        resolveContact(capA, capB, contactPt, normal, penetration, h);
    }
}

// 球 vs 箱の衝突
void XpbdEngine::checkCollisionSphereBox(RigidBody& sphere, RigidBody& box, float h) {
    Vec3 e = box.size; // 箱の半サイズ
    Vec3 v = sphere.position - box.position;
    Vec3 vLoc = box.rotation.inverse().rotate(v);

    Vec3 cLoc(
        std::clamp(vLoc.x, -e.x, e.x),
        std::clamp(vLoc.y, -e.y, e.y),
        std::clamp(vLoc.z, -e.z, e.z)
    );

    Vec3 cWorld = box.position + box.rotation.rotate(cLoc);
    Vec3 diff = sphere.position - cWorld;
    float distSq = diff.lengthSq();
    constexpr float MARGIN_FACTOR = 0.05f;
    float r = sphere.size.x * (1.0f + MARGIN_FACTOR);

    Vec3 normal;
    float penetration = 0.0f;

    if (distSq > EPSILON) {
        float dist = std::sqrt(distSq);
        if (dist < r) {
            normal = diff / dist; // boxからsphereに向かう法線
            penetration = r - dist;
        }
    } else {
        // 球の中心が箱内部に完全侵入している場合: 最も近い面へ押し出す
        float dx = e.x - std::abs(vLoc.x);
        float dy = e.y - std::abs(vLoc.y);
        float dz = e.z - std::abs(vLoc.z);

        Vec3 locNorm;
        if (dx <= dy && dx <= dz) {
            locNorm = Vec3((vLoc.x >= 0.0f) ? 1.0f : -1.0f, 0.0f, 0.0f);
            penetration = r + dx;
        } else if (dy <= dx && dy <= dz) {
            locNorm = Vec3(0.0f, (vLoc.y >= 0.0f) ? 1.0f : -1.0f, 0.0f);
            penetration = r + dy;
        } else {
            locNorm = Vec3(0.0f, 0.0f, (vLoc.z >= 0.0f) ? 1.0f : -1.0f);
            penetration = r + dz;
        }
        normal = box.rotation.rotate(locNorm);
    }

    if (penetration > 0.0f) {
        resolveContact(box, sphere, cWorld, normal, penetration, h);
    }
}

// カプセル vs 箱の衝突 (太もも vs スカート深部めり込み解消 & 外側押し出し対応)
void XpbdEngine::checkCollisionCapsuleBox(RigidBody& capsule, RigidBody& box, float h) {
    Vec3 axis = capsule.rotation.rotate(Vec3(0.0f, 1.0f, 0.0f));
    float halfH = capsule.size.y * 0.5f;
    constexpr float MARGIN_FACTOR = 0.08f;
    float r = capsule.size.x * (1.0f + MARGIN_FACTOR);
    Vec3 e = box.size;

    // カプセル軸線分上の代表サンプル点 (分解能を高めるため12分割)
    constexpr int NUM_SAMPLES = 12;
    float maxPen = 0.0f;
    Vec3 bestNormal;
    Vec3 bestContactPt;

    for (int i = 0; i < NUM_SAMPLES; ++i) {
        float ratio = static_cast<float>(i) / static_cast<float>(NUM_SAMPLES - 1);
        float offset = -halfH + 2.0f * halfH * ratio;
        Vec3 samplePt = capsule.position + axis * offset;

        Vec3 v = samplePt - box.position;
        Vec3 vLoc = box.rotation.inverse().rotate(v);

        Vec3 cLoc(
            std::clamp(vLoc.x, -e.x, e.x),
            std::clamp(vLoc.y, -e.y, e.y),
            std::clamp(vLoc.z, -e.z, e.z)
        );

        Vec3 cWorld = box.position + box.rotation.rotate(cLoc);
        Vec3 diff = samplePt - cWorld;
        float distSq = diff.lengthSq();

        if (distSq > EPSILON) {
            float dist = std::sqrt(distSq);
            if (dist < r) {
                float pen = r - dist;
                if (pen > maxPen) {
                    maxPen = pen;
                    bestNormal = diff / dist; // boxからcapsuleに向かう法線
                    bestContactPt = cWorld;
                }
            }
        } else {
            // カプセル軸が箱内部に完全侵入している場合: 太ももの中心軸から外側へ強力に押し出す
            Vec3 toBox = box.position - samplePt;
            Vec3 radial = toBox - axis * toBox.dot(axis);
            float radLen = radial.length();
            Vec3 outDir;
            if (radLen > EPSILON) {
                outDir = radial / radLen;
            } else {
                // 完全重なり時は箱のローカルZ外側
                outDir = box.rotation.rotate(Vec3(0.0f, 0.0f, 1.0f));
            }

            float boxExtent = std::max({e.x, e.y, e.z});
            float pen = r + boxExtent - radLen;
            if (pen > maxPen) {
                maxPen = pen;
                bestNormal = outDir * -1.0f; // boxからcapsuleに向かう法線
                bestContactPt = samplePt + outDir * r;
            }
        }
    }

    // 箱の8頂点からカプセル軸線分への近接・食い込み判定 (薄い板状スカートの角・エッジのすり抜けを防止)
    Vec3 p0 = capsule.position - axis * halfH;
    Vec3 p1 = capsule.position + axis * halfH;
    Vec3 capSeg = p1 - p0;
    float segLenSq = capSeg.lengthSq();

    for (int ix = -1; ix <= 1; ix += 2) {
        for (int iy = -1; iy <= 1; iy += 2) {
            for (int iz = -1; iz <= 1; iz += 2) {
                Vec3 cornerLoc(e.x * ix, e.y * iy, e.z * iz);
                Vec3 cornerWorld = box.position + box.rotation.rotate(cornerLoc);

                float t = 0.0f;
                if (segLenSq > EPSILON) {
                    t = std::clamp((cornerWorld - p0).dot(capSeg) / segLenSq, 0.0f, 1.0f);
                }
                Vec3 ptOnCapAxis = p0 + capSeg * t;
                Vec3 cornerDiff = ptOnCapAxis - cornerWorld;
                float distSq = cornerDiff.lengthSq();
                if (distSq < r * r && distSq > EPSILON) {
                    float dist = std::sqrt(distSq);
                    float pen = r - dist;
                    if (pen > maxPen) {
                        maxPen = pen;
                        bestNormal = cornerDiff / dist; // boxからcapsuleに向かう法線
                        bestContactPt = cornerWorld;
                    }
                }
            }
        }
    }

    if (maxPen > 0.0f) {
        resolveContact(box, capsule, bestContactPt, bestNormal, maxPen, h);

        // Aligned剛体 (黄色) は位置固定のため、太ももを避ける外側チルト回転をアシスト
        if (box.physicsMode == PhysicsMode::Aligned && box.invMass > 0.0f) {
            Vec3 pushOutDir = bestNormal * -1.0f;
            Vec3 tiltAxis = axis.cross(pushOutDir);
            if (tiltAxis.lengthSq() > EPSILON) {
                tiltAxis = tiltAxis.normalized();
                float tiltAngle = std::min(0.2f, maxPen * 0.08f);
                Quat dTilt = Quat::fromAxisAngle(tiltAxis, tiltAngle);
                box.rotation = (dTilt * box.rotation).normalized();
            }
        }
    }
}

// 箱 vs 箱の衝突 (OBB中心・頂点近接判定)
void XpbdEngine::checkCollisionBoxBox(RigidBody& a, RigidBody& b, float h) {
    Vec3 diff = b.position - a.position;
    float distSq = diff.lengthSq();
    float approxRadiusA = std::max({a.size.x, a.size.y, a.size.z});
    float approxRadiusB = std::max({b.size.x, b.size.y, b.size.z});
    constexpr float MARGIN_FACTOR = 0.05f;
    float rSum = (approxRadiusA + approxRadiusB) * (1.0f + MARGIN_FACTOR);

    if (distSq < rSum * rSum && distSq > EPSILON) {
        float dist = std::sqrt(distSq);
        Vec3 normal = diff / dist;
        float penetration = rSum - dist;
        Vec3 contactPt = (a.position + b.position) * 0.5f;
        resolveContact(a, b, contactPt, normal, penetration * 0.5f, h);
    }
}

// 全剛体の線形速度・角速度をゼロクリアし、現在姿勢に同期
void XpbdEngine::resetVelocities() {
    for (auto& rb : rigidBodies_) {
        rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
        rb.angularVelocity = Vec3(0.0f, 0.0f, 0.0f);
        rb.prevPosition = rb.position;
        rb.prevRotation = rb.rotation;
    }
}

// 全ジョイントの累積ラグランジュ乗数をリセット
void XpbdEngine::resetConstraints() {
    for (auto& joint : joints_) {
        joint.totalPosLambda = Vec3(0.0f, 0.0f, 0.0f);
        joint.totalRotLambda = Vec3(0.0f, 0.0f, 0.0f);
    }
}

// 初期めり込み解消ウォームアップ (Pre-roll Relaxation)
void XpbdEngine::relaxPenetration(int steps, float relaxationDamping) {
    if (steps <= 0) return;

    // 重力を一時退避してゼロに設定
    Vec3 origGravity = gravity_;
    gravity_ = Vec3(0.0f, 0.0f, 0.0f);

    // 各剛体の元のダンピングを保存し、極大減衰を一時設定
    std::vector<std::pair<float, float>> origDamping;
    origDamping.reserve(rigidBodies_.size());

    for (auto& rb : rigidBodies_) {
        origDamping.push_back({rb.linearDamping, rb.angularDamping});
        if (rb.physicsMode != PhysicsMode::Kinematic) {
            rb.linearDamping = relaxationDamping;
            rb.angularDamping = relaxationDamping;
            rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
            rb.angularVelocity = Vec3(0.0f, 0.0f, 0.0f);
        }
    }

    const float h = 1.0f / 60.0f;
    for (int step = 0; step < steps; ++step) {
        // Kinematic剛体（太もも等）の姿勢を目標位置に完全固定
        for (auto& rb : rigidBodies_) {
            if (rb.physicsMode == PhysicsMode::Kinematic) {
                rb.position = rb.targetPosition;
                rb.rotation = rb.targetRotation;
                rb.prevPosition = rb.position;
                rb.prevRotation = rb.rotation;
                rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
                rb.angularVelocity = Vec3(0.0f, 0.0f, 0.0f);
            } else if (rb.physicsMode == PhysicsMode::Aligned) {
                rb.position = rb.targetPosition;
                rb.prevPosition = rb.position;
                rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
            }
        }

        // 拘束解決（ジョイント拘束と衝突解決）
        solveJointConstraints(h);
        solveCollisions(h);

        // 緩和中は慣性速度の蓄積を遮断
        for (auto& rb : rigidBodies_) {
            rb.linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
            rb.angularVelocity = Vec3(0.0f, 0.0f, 0.0f);
            rb.prevPosition = rb.position;
            rb.prevRotation = rb.rotation;
        }
    }

    // 元のダンピングと重力を復元
    for (size_t i = 0; i < rigidBodies_.size(); ++i) {
        rigidBodies_[i].linearDamping = origDamping[i].first;
        rigidBodies_[i].angularDamping = origDamping[i].second;
        rigidBodies_[i].linearVelocity = Vec3(0.0f, 0.0f, 0.0f);
        rigidBodies_[i].angularVelocity = Vec3(0.0f, 0.0f, 0.0f);
        rigidBodies_[i].prevPosition = rigidBodies_[i].position;
        rigidBodies_[i].prevRotation = rigidBodies_[i].rotation;
    }
    gravity_ = origGravity;

    resetConstraints();
}

} // namespace xpbd
