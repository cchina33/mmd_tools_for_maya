#pragma once
#include "xpbd_math.h"
#include <cstdint>

namespace xpbd {

// 剛体形状タイプ (MMD PMX 準拠)
enum class ShapeType : uint8_t {
    Sphere = 0,   // 球 (size.x = 半径)
    Box = 1,      // 直方体 (size = 半幅/ハーフサイズ [x, y, z])
    Capsule = 2   // カプセル (size.x = 半径, size.y = 高さ)
};

// 剛体物理モード (MMD PMX 準拠)
enum class PhysicsMode : uint8_t {
    Kinematic = 0,  // ボーン追従 (アニメーション駆動、力学で動かないが衝突する)
    Dynamic = 1,    // 物理演算 (物理法則に従って自由運動)
    Aligned = 2     // 物理+ボーン位置合わせ (物理演算しつつボーン位置に追従)
};

// XPBD 剛体構造体
struct RigidBody {
    int id = -1;
    int boneIndex = -1;

    ShapeType shapeType = ShapeType::Sphere;
    PhysicsMode physicsMode = PhysicsMode::Dynamic;
    Vec3 size = {1.0f, 1.0f, 1.0f};

    // 質量および慣性特性
    float mass = 1.0f;
    float invMass = 1.0f;
    Mat3 inertiaLocal = Mat3::identity();
    Mat3 invInertiaLocal = Mat3::identity();

    // 現在のワールド状態
    Vec3 position = {0.0f, 0.0f, 0.0f};
    Quat rotation = Quat::identity();

    // 前ステップのワールド状態 (XPBD数値積分用)
    Vec3 prevPosition = {0.0f, 0.0f, 0.0f};
    Quat prevRotation = Quat::identity();

    // 速度および角速度
    Vec3 linearVelocity = {0.0f, 0.0f, 0.0f};
    Vec3 angularVelocity = {0.0f, 0.0f, 0.0f};

    // 物理パラメータ
    float linearDamping = 0.0f;
    float angularDamping = 0.0f;
    float restitution = 0.0f;  // 反発係数
    float friction = 0.5f;     // 摩擦係数

    // 衝突グループおよび衝突マスク (ビットフラグ)
    uint16_t group = 0;
    uint16_t collisionMask = 0xFFFF;

    // ボーン追従モード用のターゲット（アニメーション姿勢）
    Vec3 targetPosition = {0.0f, 0.0f, 0.0f};
    Quat targetRotation = Quat::identity();

    // サブステップ補間用の開始姿勢
    Vec3 startPosition = {0.0f, 0.0f, 0.0f};
    Quat startRotation = Quat::identity();

    // ワールド逆慣性テンソルの取得
    Mat3 getInvInertiaWorld() const {
        if (invMass == 0.0f) return Mat3::diagonal(0.0f, 0.0f, 0.0f);
        Mat3 rot = rotation.toRotationMatrix();
        return rot * invInertiaLocal * rot.transposed();
    }

    // 質量特性の再計算
    void updateInertia() {
        if (physicsMode == PhysicsMode::Kinematic || mass <= 0.0f) {
            invMass = 0.0f;
            inertiaLocal = Mat3::diagonal(0.0f, 0.0f, 0.0f);
            invInertiaLocal = Mat3::diagonal(0.0f, 0.0f, 0.0f);
            return;
        }

        invMass = 1.0f / mass;
        float ixx = 1.0f, iyy = 1.0f, izz = 1.0f;

        if (shapeType == ShapeType::Sphere) {
            float r = size.x;
            float val = 0.4f * mass * r * r;
            ixx = iyy = izz = val;
        } else if (shapeType == ShapeType::Box) {
            float w = size.x * 2.0f;
            float h = size.y * 2.0f;
            float d = size.z * 2.0f;
            ixx = (1.0f / 12.0f) * mass * (h * h + d * d);
            iyy = (1.0f / 12.0f) * mass * (w * w + d * d);
            izz = (1.0f / 12.0f) * mass * (w * w + h * h);
        } else if (shapeType == ShapeType::Capsule) {
            float r = size.x;
            float h = size.y;
            // 円柱近似 + 端部
            ixx = mass * ((1.0f / 12.0f) * h * h + 0.25f * r * r);
            iyy = 0.5f * mass * r * r;
            izz = ixx;
        }

        inertiaLocal = Mat3::diagonal(ixx, iyy, izz);
        invInertiaLocal = Mat3::diagonal(
            ixx > EPSILON ? 1.0f / ixx : 0.0f,
            iyy > EPSILON ? 1.0f / iyy : 0.0f,
            izz > EPSILON ? 1.0f / izz : 0.0f
        );
    }
};

// XPBD 6DOF ジョイント制約構造体 (MMD Joint 準拠)
struct Joint6DOF {
    int id = -1;
    int bodyA = -1;
    int bodyB = -1;

    // ワールド空間でのジョイント初期配置
    Vec3 jointPosition = {0.0f, 0.0f, 0.0f};
    Quat jointRotation = Quat::identity();

    // 剛体A、Bの各ローカル空間でのアンカー位置および回転
    Vec3 localAnchorA = {0.0f, 0.0f, 0.0f};
    Quat localRotA = Quat::identity();

    Vec3 localAnchorB = {0.0f, 0.0f, 0.0f};
    Quat localRotB = Quat::identity();

    // 移動制限 (最小・最大 [X, Y, Z])
    Vec3 linearLimitMin = {0.0f, 0.0f, 0.0f};
    Vec3 linearLimitMax = {0.0f, 0.0f, 0.0f};

    // 回転制限 (最小・最大 [X, Y, Z] ラジアン)
    Vec3 angularLimitMin = {0.0f, 0.0f, 0.0f};
    Vec3 angularLimitMax = {0.0f, 0.0f, 0.0f};

    // バネ定数 (移動バネ [X, Y, Z], 回転バネ [X, Y, Z])
    Vec3 linearSpring = {0.0f, 0.0f, 0.0f};
    Vec3 angularSpring = {0.0f, 0.0f, 0.0f};

    // XPBD ラグランジュ乗数アキュムレータ
    Vec3 totalPosLambda = {0.0f, 0.0f, 0.0f};
    Vec3 totalRotLambda = {0.0f, 0.0f, 0.0f};
};

} // namespace xpbd
