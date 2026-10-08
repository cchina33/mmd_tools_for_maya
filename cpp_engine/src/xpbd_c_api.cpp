#include "xpbd_engine.h"

#define XPBD_API extern "C" __declspec(dllexport)

XPBD_API xpbd::XpbdEngine* xpbd_create() {
    return new xpbd::XpbdEngine();
}

XPBD_API void xpbd_destroy(xpbd::XpbdEngine* engine) {
    if (engine) {
        delete engine;
    }
}

XPBD_API void xpbd_reset(xpbd::XpbdEngine* engine) {
    if (engine) engine->reset();
}

XPBD_API void xpbd_clear(xpbd::XpbdEngine* engine) {
    if (engine) engine->clear();
}

XPBD_API void xpbd_set_gravity(xpbd::XpbdEngine* engine, float gx, float gy, float gz) {
    if (engine) engine->setGravity({gx, gy, gz});
}

XPBD_API int xpbd_add_rigidbody(
    xpbd::XpbdEngine* engine,
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
    if (!engine) return -1;

    xpbd::RigidBody rb;
    rb.boneIndex = boneIndex;
    rb.shapeType = static_cast<xpbd::ShapeType>(shapeType);
    rb.physicsMode = static_cast<xpbd::PhysicsMode>(physicsMode);
    rb.size = {sizeX, sizeY, sizeZ};
    rb.position = {posX, posY, posZ};
    rb.rotation = xpbd::Quat::fromEulerXYZ(rotEulerX, rotEulerY, rotEulerZ);
    rb.mass = mass;
    rb.linearDamping = linearDamping;
    rb.angularDamping = angularDamping;
    rb.restitution = restitution;
    rb.friction = friction;
    rb.group = group;
    rb.collisionMask = collisionMask;

    return engine->addRigidBody(rb);
}

XPBD_API void xpbd_set_rigidbody_transform(
    xpbd::XpbdEngine* engine,
    int index,
    float px, float py, float pz,
    float qx, float qy, float qz, float qw
) {
    if (!engine) return;
    engine->setRigidBodyTransform(index, {px, py, pz}, {qx, qy, qz, qw});
}

XPBD_API int xpbd_add_joint(
    xpbd::XpbdEngine* engine,
    int bodyA, int bodyB,
    float jposX, float jposY, float jposZ,
    float jrotX, float jrotY, float jrotZ,
    float minTx, float minTy, float minTz,
    float maxTx, float maxTy, float maxTz,
    float minRx, float minRy, float minRz,
    float maxRx, float maxRy, float maxRz,
    float spTx, float spTy, float spTz,
    float spRx, float spRy, float spRz
) {
    if (!engine) return -1;

    xpbd::Joint6DOF j;
    j.bodyA = bodyA;
    j.bodyB = bodyB;
    j.jointPosition = {jposX, jposY, jposZ};
    j.jointRotation = xpbd::Quat::fromEulerXYZ(jrotX, jrotY, jrotZ);

    j.linearLimitMin = {minTx, minTy, minTz};
    j.linearLimitMax = {maxTx, maxTy, maxTz};
    j.angularLimitMin = {minRx, minRy, minRz};
    j.angularLimitMax = {maxRx, maxRy, maxRz};

    j.linearSpring = {spTx, spTy, spTz};
    j.angularSpring = {spRx, spRy, spRz};

    return engine->addJoint(j);
}

XPBD_API void xpbd_step_simulation(xpbd::XpbdEngine* engine, float dt, int substeps) {
    if (engine) engine->stepSimulation(dt, substeps);
}

XPBD_API int xpbd_get_rigidbody_transform(
    xpbd::XpbdEngine* engine,
    int index,
    float* outPos3,
    float* outQuat4
) {
    if (!engine || !outPos3 || !outQuat4) return 0;
    xpbd::RigidBody* rb = engine->getRigidBody(index);
    if (!rb) return 0;

    outPos3[0] = rb->position.x;
    outPos3[1] = rb->position.y;
    outPos3[2] = rb->position.z;

    outQuat4[0] = rb->rotation.x;
    outQuat4[1] = rb->rotation.y;
    outQuat4[2] = rb->rotation.z;
    outQuat4[3] = rb->rotation.w;

    return 1;
}

XPBD_API int xpbd_get_rigidbody_count(xpbd::XpbdEngine* engine) {
    return engine ? engine->getRigidBodyCount() : 0;
}

XPBD_API int xpbd_get_joint_count(xpbd::XpbdEngine* engine) {
    return engine ? engine->getJointCount() : 0;
}
