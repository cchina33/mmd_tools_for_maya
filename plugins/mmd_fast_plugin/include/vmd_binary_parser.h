#ifndef VMD_BINARY_PARSER_H
#define VMD_BINARY_PARSER_H

#include <string>
#include <vector>
#include <unordered_map>
#include <cstdint>

namespace mmd_fast {

// VMDボーンキーフレーム要素 (111バイト相当)
struct VmdBoneKey
{
    uint32_t frame;
    float pos[3];
    float rot[4]; // 正規化済みクォータニオン (qx, qy, qz, qw)
    uint8_t interpolation[64];
};

// VMDモーフキーフレーム要素 (23バイト相当)
struct VmdMorphKey
{
    uint32_t frame;
    float weight;
};

// VMDカメラキーフレーム要素 (61バイト相当)
struct VmdCameraKey
{
    uint32_t frame;
    float distance;
    float pos[3];
    float rot[3]; // ラジアン (rx, ry, rz)
    uint8_t interpolation[24];
    uint32_t fov;
    bool perspective;
};

// 解析済みVMDモーションキャッシュ構造
struct VmdParsedMotion
{
    std::wstring filePath;
    int version = 2;
    std::string modelNameUtf8;
    uint32_t maxFrame = 0;

    // ボーン名(UTF-8) -> フレーム順ソート・重複フレーム統合済みのキー配列
    std::unordered_map<std::string, std::vector<VmdBoneKey>> boneTracks;

    // モーフ名(UTF-8) -> フレーム順ソート・重複フレーム統合済みのキー配列
    std::unordered_map<std::string, std::vector<VmdMorphKey>> morphTracks;

    // フレーム順ソート・重複フレーム統合済みのカメラキー配列
    std::vector<VmdCameraKey> cameraFrames;
};

// VMDバイナリパーサーおよびオンメモリキャッシュ管理クラス
class VmdBinaryCache
{
public:
    static const VmdParsedMotion* getOrParse(const std::wstring& wFilePath, bool forceReload = false, std::string* outError = nullptr);
    static void clearCache();

private:
    static bool parseVmdFile(const std::wstring& wFilePath, VmdParsedMotion& outMotion, std::string* outError);
    static VmdParsedMotion s_cachedMotion;
};

} // namespace mmd_fast

#endif // VMD_BINARY_PARSER_H

