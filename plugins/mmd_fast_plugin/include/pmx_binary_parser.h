#ifndef PMX_BINARY_PARSER_H
#define PMX_BINARY_PARSER_H

#include <string>
#include <vector>
#include <cstdint>

namespace mmd_fast {

// PMX頂点データ構造
struct PmxVertexData
{
    float pos[3];
    float normal[3];
    float uv[2];
    uint8_t weightType;
    int32_t boneIndices[4];
    float boneWeights[4];
    float edgeScale;
};

// PMX材質データ構造（メッシュ面割り当て・エッジ判定用）
struct PmxMaterialInfo
{
    float diffuseAlpha;
    uint8_t drawFlags;
    float edgeSize;
    int32_t faceCount; // 三角形面数 (vertex_count / 3)
};

// 頂点モーフの単一オフセット要素
struct PmxVertexMorphOffset
{
    int32_t vertexIndex;
    float offset[3];
};

// 頂点モーフデータ構造
struct PmxVertexMorph
{
    int32_t morphIndex; // PMX内の通しモーフインデックス
    int32_t vertexMorphOrder; // 頂点モーフのみでの順番 (0, 1, 2...)
    std::string nameUtf8;
    std::string nameEnUtf8;
    std::vector<PmxVertexMorphOffset> offsets;
};

// 解析済みPMXモデルキャッシュ構造
struct PmxParsedModel
{
    std::wstring filePath;
    float version = 2.0f;
    int32_t boneCount = 0;
    std::vector<PmxVertexData> vertices;
    std::vector<int32_t> triangleIndices; // 3要素ごとに1三角形 (i0, i1, i2)
    std::vector<PmxMaterialInfo> materials;
    std::vector<PmxVertexMorph> vertexMorphs;
};

// PMXバイナリパーサーおよびオンメモリキャッシュ管理クラス
class PmxBinaryCache
{
public:
    // 指定パスのPMXを解析してキャッシュを取得（同一パスなら再解析せずキャッシュ返却）
    static const PmxParsedModel* getOrParse(const std::wstring& wFilePath, bool forceReload = false, std::string* outError = nullptr);

    // キャッシュクリア
    static void clearCache();

private:
    static bool parsePmxFile(const std::wstring& wFilePath, PmxParsedModel& outModel, std::string* outError);
    static PmxParsedModel s_cachedModel;
};

} // namespace mmd_fast

#endif // PMX_BINARY_PARSER_H

