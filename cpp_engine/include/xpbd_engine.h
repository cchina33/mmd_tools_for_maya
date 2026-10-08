#pragma once
#include "xpbd_types.h"
#include <vector>

namespace xpbd {

// XPBD 物理エンジンクラス
class XpbdEngine {
public:
    XpbdEngine();
    ~XpbdEngine() = default;

    // エンジンのリセット・クリア
    void reset();
    void clear();

    // 剛体の追加・取得・更新
    int addRigidBody(const RigidBody& rb);
    RigidBody* getRigidBody(int index);
    int getRigidBodyCount() const { return static_cast<int>(rigidBodies_.size()); }

    // ボーン追従用 Kinematic 剛体の姿勢更新
    void setRigidBodyTransform(int index, const Vec3& pos, const Quat& rot);

    // ジョイントの追加・取得
    int addJoint(const Joint6DOF& joint);
    Joint6DOF* getJoint(int index);
    int getJointCount() const { return static_cast<int>(joints_.size()); }

    // シミュレーション実行
    void stepSimulation(float dt, int substeps);

    // 環境設定
    void setGravity(const Vec3& g) { gravity_ = g; }
    Vec3 getGravity() const { return gravity_; }

private:
    // 内部サブステップ実行
    void subStep(float h, float alpha);

    // 衝突判定および位置補正
    void solveCollisions(float h);
    void resolveContact(RigidBody& a, RigidBody& b, const Vec3& contactPoint, const Vec3& normal, float penetration, float h);
    void checkCollisionSphereSphere(RigidBody& a, RigidBody& b, float h);
    void checkCollisionSphereBox(RigidBody& sphere, RigidBody& box, float h);
    void checkCollisionSphereCapsule(RigidBody& a, RigidBody& b, float h);
    void checkCollisionCapsuleCapsule(RigidBody& a, RigidBody& b, float h);
    void checkCollisionCapsuleBox(RigidBody& capsule, RigidBody& box, float h);
    void checkCollisionBoxBox(RigidBody& a, RigidBody& b, float h);

    // 6自由度ジョイント制約の解決
    void solveJointConstraints(float h);
    void solveJoint(Joint6DOF& joint, float h);

    std::vector<RigidBody> rigidBodies_;
    std::vector<Joint6DOF> joints_;
    Vec3 gravity_ = {0.0f, -9.80665f, 0.0f};
};

} // namespace xpbd
