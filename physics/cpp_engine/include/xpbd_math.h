#pragma once
#include <cmath>
#include <algorithm>

namespace xpbd {

constexpr float PI = 3.14159265358979323846f;
constexpr float EPSILON = 1e-7f;

// 3次元ベクトル構造体
struct Vec3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& b) const { return {x + b.x, y + b.y, z + b.z}; }
    Vec3 operator-(const Vec3& b) const { return {x - b.x, y - b.y, z - b.z}; }
    Vec3 operator*(float s) const { return {x * s, y * s, z * s}; }
    Vec3 operator/(float s) const { float inv = 1.0f / s; return {x * inv, y * inv, z * inv}; }
    Vec3 operator-() const { return {-x, -y, -z}; }

    Vec3& operator+=(const Vec3& b) { x += b.x; y += b.y; z += b.z; return *this; }
    Vec3& operator-=(const Vec3& b) { x -= b.x; y -= b.y; z -= b.z; return *this; }
    Vec3& operator*=(float s) { x *= s; y *= s; z *= s; return *this; }

    float dot(const Vec3& b) const { return x * b.x + y * b.y + z * b.z; }
    Vec3 cross(const Vec3& b) const {
        return {
            y * b.z - z * b.y,
            z * b.x - x * b.z,
            x * b.y - y * b.x
        };
    }

    float lengthSq() const { return x * x + y * y + z * z; }
    float length() const { return std::sqrt(lengthSq()); }

    Vec3 normalized() const {
        float len = length();
        if (len > EPSILON) {
            float inv = 1.0f / len;
            return {x * inv, y * inv, z * inv};
        }
        return {0.0f, 0.0f, 0.0f};
    }
};

inline Vec3 operator*(float s, const Vec3& v) { return v * s; }

// 3x3 行列構造体 (慣性テンソル・回転行列用)
struct Mat3 {
    float m[3][3] = {
        {1.0f, 0.0f, 0.0f},
        {0.0f, 1.0f, 0.0f},
        {0.0f, 0.0f, 1.0f}
    };

    Mat3() = default;

    static Mat3 identity() {
        return Mat3();
    }

    static Mat3 diagonal(float d0, float d1, float d2) {
        Mat3 res;
        res.m[0][0] = d0; res.m[0][1] = 0.0f; res.m[0][2] = 0.0f;
        res.m[1][0] = 0.0f; res.m[1][1] = d1; res.m[1][2] = 0.0f;
        res.m[2][0] = 0.0f; res.m[2][1] = 0.0f; res.m[2][2] = d2;
        return res;
    }

    Vec3 operator*(const Vec3& v) const {
        return {
            m[0][0] * v.x + m[0][1] * v.y + m[0][2] * v.z,
            m[1][0] * v.x + m[1][1] * v.y + m[1][2] * v.z,
            m[2][0] * v.x + m[2][1] * v.y + m[2][2] * v.z
        };
    }

    Mat3 operator*(const Mat3& b) const {
        Mat3 r;
        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 3; ++j) {
                r.m[i][j] = m[i][0] * b.m[0][j] + m[i][1] * b.m[1][j] + m[i][2] * b.m[2][j];
            }
        }
        return r;
    }

    Mat3 transposed() const {
        Mat3 r;
        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 3; ++j) {
                r.m[i][j] = m[j][i];
            }
        }
        return r;
    }

    Mat3 inverse() const {
        float det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                  - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                  + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
        if (std::abs(det) < EPSILON) return identity();
        float invDet = 1.0f / det;

        Mat3 r;
        r.m[0][0] = (m[1][1] * m[2][2] - m[1][2] * m[2][1]) * invDet;
        r.m[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) * invDet;
        r.m[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) * invDet;

        r.m[1][0] = (m[1][2] * m[2][0] - m[1][0] * m[2][2]) * invDet;
        r.m[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) * invDet;
        r.m[1][2] = (m[0][2] * m[1][0] - m[0][0] * m[1][2]) * invDet;

        r.m[2][0] = (m[1][0] * m[2][1] - m[1][1] * m[2][0]) * invDet;
        r.m[2][1] = (m[0][1] * m[2][0] - m[0][0] * m[2][1]) * invDet;
        r.m[2][2] = (m[0][0] * m[1][1] - m[0][1] * m[1][0]) * invDet;
        return r;
    }
};

// クォータニオン構造体 (回転表現)
struct Quat {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
    float w = 1.0f;

    Quat() = default;
    Quat(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}

    static Quat identity() { return {0.0f, 0.0f, 0.0f, 1.0f}; }

    // オイラー角 (ラジアン, ZYX順序) からクォータニオン生成
    static Quat fromEulerXYZ(float rx, float ry, float rz) {
        float cx = std::cos(rx * 0.5f), sx = std::sin(rx * 0.5f);
        float cy = std::cos(ry * 0.5f), sy = std::sin(ry * 0.5f);
        float cz = std::cos(rz * 0.5f), sz = std::sin(rz * 0.5f);

        Quat q;
        q.w = cx * cy * cz + sx * sy * sz;
        q.x = sx * cy * cz - cx * sy * sz;
        q.y = cx * sy * cz + sx * cy * sz;
        q.z = cx * cy * sz - sx * sy * cz;
        return q.normalized();
    }

    // 任意軸と回転角 (ラジアン) からクォータニオン生成
    static Quat fromAxisAngle(const Vec3& axis, float angle) {
        float half = angle * 0.5f;
        float s = std::sin(half);
        float c = std::cos(half);
        Vec3 ax = axis.normalized();
        return Quat(ax.x * s, ax.y * s, ax.z * s, c);
    }


    Quat operator*(const Quat& b) const {
        return {
            w * b.x + x * b.w + y * b.z - z * b.y,
            w * b.y - x * b.z + y * b.w + z * b.x,
            w * b.z + x * b.y - y * b.x + z * b.w,
            w * b.w - x * b.x - y * b.y - z * b.z
        };
    }

    Quat operator*(float s) const { return {x * s, y * s, z * s, w * s}; }
    Quat operator+(const Quat& b) const { return {x + b.x, y + b.y, z + b.z, w + b.w}; }

    float lengthSq() const { return x * x + y * y + z * z + w * w; }
    float length() const { return std::sqrt(lengthSq()); }

    Quat normalized() const {
        float len = length();
        if (len > EPSILON) {
            float inv = 1.0f / len;
            return {x * inv, y * inv, z * inv, w * inv};
        }
        return identity();
    }

    Quat conjugate() const { return {-x, -y, -z, w}; }
    Quat inverse() const {
        float ls = lengthSq();
        if (ls > EPSILON) {
            float inv = 1.0f / ls;
            return {-x * inv, -y * inv, -z * inv, w * inv};
        }
        return identity();
    }

    // ベクトルをクォータニオンで回転
    Vec3 rotate(const Vec3& v) const {
        Vec3 qv(x, y, z);
        Vec3 uv = qv.cross(v);
        Vec3 uuv = qv.cross(uv);
        return v + ((uv * w) + uuv) * 2.0f;
    }

    // 3x3 回転行列へ変換
    Mat3 toRotationMatrix() const {
        Mat3 m;
        float x2 = x + x, y2 = y + y, z2 = z + z;
        float xx = x * x2, xy = x * y2, xz = x * z2;
        float yy = y * y2, yz = y * z2, zz = z * z2;
        float wx = w * x2, wy = w * y2, wz = w * z2;

        m.m[0][0] = 1.0f - (yy + zz);
        m.m[0][1] = xy - wz;
        m.m[0][2] = xz + wy;

        m.m[1][0] = xy + wz;
        m.m[1][1] = 1.0f - (xx + zz);
        m.m[1][2] = yz - wx;

        m.m[2][0] = xz - wy;
        m.m[2][1] = yz + wx;
        m.m[2][2] = 1.0f - (xx + yy);
        return m;
    }

    // 角度を [-PI, PI] の範囲に正規化
    static float normalizeAngle(float a) {
        while (a > PI) a -= 2.0f * PI;
        while (a < -PI) a += 2.0f * PI;
        return a;
    }

    // クォータニオンから厳密なXYZ順オイラー角 (ラジアン) を抽出 (Rx * Ry * Rz)
    Vec3 toEulerXYZ() const {
        Vec3 euler;
        // 回転行列の必要成分を展開
        float x2 = x + x, y2 = y + y, z2 = z + z;
        float xx = x * x2, xy = x * y2, xz = x * z2;
        float yy = y * y2, yz = y * z2, zz = z * z2;
        float wx = w * x2, wy = w * y2, wz = w * z2;

        float m00 = 1.0f - (yy + zz);
        float m01 = xy - wz;
        float m02 = xz + wy;
        float m12 = yz - wx;
        float m22 = 1.0f - (xx + yy);

        // Y軸角度 (ピッチ/ヨー)
        float siny = std::clamp(m02, -1.0f, 1.0f);
        euler.y = std::asin(siny);

        if (std::abs(m02) < 0.99999f) {
            euler.x = std::atan2(-m12, m22);
            euler.z = std::atan2(-m01, m00);
        } else {
            // ジンバルロック特異点付近の保護
            euler.x = std::atan2(m01, m00);
            euler.z = 0.0f;
        }

        euler.x = normalizeAngle(euler.x);
        euler.y = normalizeAngle(euler.y);
        euler.z = normalizeAngle(euler.z);
        return euler;
    }

    // 球面線形補間 (SLERP)
    static Quat slerp(const Quat& q0, const Quat& q1, float t) {
        float cosHalfTheta = q0.x * q1.x + q0.y * q1.y + q0.z * q1.z + q0.w * q1.w;
        Quat q1Copy = q1;
        if (cosHalfTheta < 0.0f) {
            q1Copy = q1 * -1.0f;
            cosHalfTheta = -cosHalfTheta;
        }
        if (cosHalfTheta > 0.9995f) {
            return (q0 * (1.0f - t) + q1Copy * t).normalized();
        }
        float halfTheta = std::acos(cosHalfTheta);
        float sinHalfTheta = std::sqrt(1.0f - cosHalfTheta * cosHalfTheta);
        float ratioA = std::sin((1.0f - t) * halfTheta) / sinHalfTheta;
        float ratioB = std::sin(t * halfTheta) / sinHalfTheta;
        return (q0 * ratioA + q1Copy * ratioB).normalized();
    }
};

} // namespace xpbd
