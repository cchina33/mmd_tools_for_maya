#include "pmx_binary_parser.h"

#include <fstream>
#include <cmath>
#include <cstring>
#include <algorithm>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace mmd_fast {

PmxParsedModel PmxBinaryCache::s_cachedModel;

namespace {

// メモリバッファからバイナリを高速に読み取るリーダー
class MemoryStreamReader
{
public:
    MemoryStreamReader(const uint8_t* data, size_t size)
        : m_data(data), m_size(size), m_pos(0)
    {
    }

    bool eof() const { return m_pos >= m_size; }
    size_t remaining() const { return (m_pos < m_size) ? (m_size - m_pos) : 0; }

    void skip(size_t bytes)
    {
        m_pos = std::min(m_size, m_pos + bytes);
    }

    template <typename T>
    T readVal()
    {
        if (m_pos + sizeof(T) > m_size)
        {
            m_pos = m_size;
            return T{};
        }
        T val;
        std::memcpy(&val, m_data + m_pos, sizeof(T));
        m_pos += sizeof(T);
        return val;
    }

    int8_t readInt8() { return readVal<int8_t>(); }
    uint8_t readUInt8() { return readVal<uint8_t>(); }
    int16_t readInt16() { return readVal<int16_t>(); }
    uint16_t readUInt16() { return readVal<uint16_t>(); }
    int32_t readInt32() { return readVal<int32_t>(); }
    uint32_t readUInt32() { return readVal<uint32_t>(); }

    float readFloat()
    {
        float v = readVal<float>();
        if (std::isnan(v) || std::isinf(v))
        {
            return 0.0f;
        }
        return v;
    }

    void readFloats(float* outArr, size_t count)
    {
        for (size_t i = 0; i < count; ++i)
        {
            outArr[i] = readFloat();
        }
    }

    int32_t readIndex(uint8_t idxSize, bool isSigned)
    {
        if (idxSize == 1)
        {
            if (isSigned) return static_cast<int32_t>(readInt8());
            uint8_t v = readUInt8();
            return (v == 0xFF) ? -1 : static_cast<int32_t>(v);
        }
        else if (idxSize == 2)
        {
            if (isSigned) return static_cast<int32_t>(readInt16());
            uint16_t v = readUInt16();
            return (v == 0xFFFF) ? -1 : static_cast<int32_t>(v);
        }
        else if (idxSize == 4)
        {
            return readInt32();
        }
        return -1;
    }

    int32_t readVertexIndex(uint8_t idxSize)
    {
        if (idxSize == 1) return static_cast<int32_t>(readUInt8());
        if (idxSize == 2) return static_cast<int32_t>(readUInt16());
        if (idxSize == 4) return readInt32();
        return 0;
    }

    void skipText()
    {
        int32_t len = readInt32();
        if (len > 0 && len <= 1048576)
        {
            skip(static_cast<size_t>(len));
        }
    }

    std::string readTextUtf8(uint8_t encodingFlag)
    {
        int32_t len = readInt32();
        if (len <= 0 || len > 1048576 || m_pos + static_cast<size_t>(len) > m_size)
        {
            if (len > 0) skip(static_cast<size_t>(len));
            return std::string();
        }

        const uint8_t* ptr = m_data + m_pos;
        m_pos += static_cast<size_t>(len);

        if (encodingFlag == 1)
        {
            // UTF-8
            std::string s(reinterpret_cast<const char*>(ptr), static_cast<size_t>(len));
            size_t nullPos = s.find('\0');
            if (nullPos != std::string::npos) s.resize(nullPos);
            return s;
        }
        else
        {
            // UTF-16LE -> UTF-8
#ifdef _WIN32
            int charCount = len / 2;
            if (charCount <= 0) return std::string();
            const wchar_t* wptr = reinterpret_cast<const wchar_t*>(ptr);
            int utf8Len = WideCharToMultiByte(CP_UTF8, 0, wptr, charCount, nullptr, 0, nullptr, nullptr);
            if (utf8Len <= 0) return std::string();
            std::string outStr(static_cast<size_t>(utf8Len), '\0');
            WideCharToMultiByte(CP_UTF8, 0, wptr, charCount, &outStr[0], utf8Len, nullptr, nullptr);
            size_t nullPos = outStr.find('\0');
            if (nullPos != std::string::npos) outStr.resize(nullPos);
            return outStr;
#else
            return std::string();
#endif
        }
    }

private:
    const uint8_t* m_data;
    size_t m_size;
    size_t m_pos;
};

} // namespace

void PmxBinaryCache::clearCache()
{
    s_cachedModel = PmxParsedModel();
}

const PmxParsedModel* PmxBinaryCache::getOrParse(const std::wstring& wFilePath, bool forceReload, std::string* outError)
{
    if (!forceReload && !s_cachedModel.filePath.empty() && s_cachedModel.filePath == wFilePath && !s_cachedModel.vertices.empty())
    {
        return &s_cachedModel;
    }

    PmxParsedModel newModel;
    if (!parsePmxFile(wFilePath, newModel, outError))
    {
        return nullptr;
    }

    s_cachedModel = std::move(newModel);
    return &s_cachedModel;
}

bool PmxBinaryCache::parsePmxFile(const std::wstring& wFilePath, PmxParsedModel& outModel, std::string* outError)
{
    std::ifstream ifs(wFilePath, std::ios::binary | std::ios::ate);
    if (!ifs.is_open())
    {
        if (outError) *outError = "Failed to open PMX file.";
        return false;
    }

    std::streamsize fileSize = ifs.tellg();
    if (fileSize < 16)
    {
        if (outError) *outError = "PMX file is too small.";
        return false;
    }

    ifs.seekg(0, std::ios::beg);
    std::vector<uint8_t> buffer(static_cast<size_t>(fileSize));
    if (!ifs.read(reinterpret_cast<char*>(buffer.data()), fileSize))
    {
        if (outError) *outError = "Failed to read PMX file bytes.";
        return false;
    }
    ifs.close();

    MemoryStreamReader reader(buffer.data(), buffer.size());

    // シグネチャ確認 ("PMX ")
    if (buffer[0] != 'P' || buffer[1] != 'M' || buffer[2] != 'X' || buffer[3] != ' ')
    {
        if (outError) *outError = "Invalid PMX signature.";
        return false;
    }
    reader.skip(4);

    outModel.filePath = wFilePath;
    outModel.version = reader.readFloat();

    uint8_t flagCount = reader.readUInt8();
    if (flagCount < 8)
    {
        if (outError) *outError = "Invalid PMX global flags count.";
        return false;
    }

    uint8_t flags[16] = {0};
    for (uint8_t i = 0; i < flagCount; ++i)
    {
        uint8_t f = reader.readUInt8();
        if (i < 16) flags[i] = f;
    }

    uint8_t encodingFlag = flags[0];
    uint8_t additionalUvCount = flags[1];
    uint8_t vtxIdxSize = flags[2];
    uint8_t texIdxSize = flags[3];
    uint8_t matIdxSize = flags[4];
    uint8_t boneIdxSize = flags[5];
    uint8_t morphIdxSize = flags[6];
    uint8_t rigidIdxSize = flags[7];

    // モデル情報 (名前, 英名, コメント, 英語コメント) をスキップ
    reader.skipText();
    reader.skipText();
    reader.skipText();
    reader.skipText();

    // 頂点データの解析
    int32_t vtxCount = reader.readInt32();
    if (vtxCount <= 0 || vtxCount > 10000000)
    {
        if (outError) *outError = "Invalid vertex count in PMX.";
        return false;
    }

    outModel.vertices.resize(static_cast<size_t>(vtxCount));
    size_t addUvSkipBytes = static_cast<size_t>(additionalUvCount) * 16;

    for (int32_t i = 0; i < vtxCount; ++i)
    {
        PmxVertexData& v = outModel.vertices[static_cast<size_t>(i)];
        reader.readFloats(v.pos, 3);
        reader.readFloats(v.normal, 3);
        reader.readFloats(v.uv, 2);

        if (addUvSkipBytes > 0)
        {
            reader.skip(addUvSkipBytes);
        }

        v.weightType = reader.readUInt8();
        v.boneIndices[0] = 0;
        v.boneIndices[1] = 0;
        v.boneIndices[2] = 0;
        v.boneIndices[3] = 0;
        v.boneWeights[0] = 0.0f;
        v.boneWeights[1] = 0.0f;
        v.boneWeights[2] = 0.0f;
        v.boneWeights[3] = 0.0f;

        if (v.weightType == 0) // BDEF1
        {
            v.boneIndices[0] = reader.readIndex(boneIdxSize, false);
            v.boneWeights[0] = 1.0f;
        }
        else if (v.weightType == 1) // BDEF2
        {
            v.boneIndices[0] = reader.readIndex(boneIdxSize, false);
            v.boneIndices[1] = reader.readIndex(boneIdxSize, false);
            float w0 = reader.readFloat();
            w0 = std::max(0.0f, std::min(1.0f, w0));
            v.boneWeights[0] = w0;
            v.boneWeights[1] = 1.0f - w0;
        }
        else if (v.weightType == 2 || v.weightType == 4) // BDEF4 または QDEF
        {
            for (int k = 0; k < 4; ++k)
            {
                v.boneIndices[k] = reader.readIndex(boneIdxSize, false);
            }
            float rawW[4];
            reader.readFloats(rawW, 4);
            float sumW = 0.0f;
            for (int k = 0; k < 4; ++k)
            {
                rawW[k] = std::max(0.0f, rawW[k]);
                sumW += rawW[k];
            }
            if (sumW > 1e-6f)
            {
                for (int k = 0; k < 4; ++k) v.boneWeights[k] = rawW[k] / sumW;
            }
            else
            {
                v.boneWeights[0] = 1.0f;
            }
        }
        else if (v.weightType == 3) // SDEF
        {
            v.boneIndices[0] = reader.readIndex(boneIdxSize, false);
            v.boneIndices[1] = reader.readIndex(boneIdxSize, false);
            float w0 = reader.readFloat();
            w0 = std::max(0.0f, std::min(1.0f, w0));
            v.boneWeights[0] = w0;
            v.boneWeights[1] = 1.0f - w0;
            // C, R0, R1 (float 9個 = 36バイト) をスキップ
            reader.skip(36);
        }
        else
        {
            v.boneWeights[0] = 1.0f;
        }

        v.edgeScale = reader.readFloat();
    }

    // 面データの解析
    int32_t faceVertCount = reader.readInt32();
    int32_t numTriangles = std::max(0, faceVertCount / 3);
    outModel.triangleIndices.resize(static_cast<size_t>(numTriangles) * 3);

    for (int32_t t = 0; t < numTriangles; ++t)
    {
        int32_t i0 = reader.readVertexIndex(vtxIdxSize);
        int32_t i1 = reader.readVertexIndex(vtxIdxSize);
        int32_t i2 = reader.readVertexIndex(vtxIdxSize);

        i0 = std::max(0, std::min(vtxCount - 1, i0));
        i1 = std::max(0, std::min(vtxCount - 1, i1));
        i2 = std::max(0, std::min(vtxCount - 1, i2));

        size_t baseIdx = static_cast<size_t>(t) * 3;
        outModel.triangleIndices[baseIdx + 0] = i0;
        outModel.triangleIndices[baseIdx + 1] = i1;
        outModel.triangleIndices[baseIdx + 2] = i2;
    }

    // テクスチャテーブルのスキップ
    int32_t texCount = reader.readInt32();
    for (int32_t i = 0; i < texCount; ++i)
    {
        reader.skipText();
    }

    // 材質データの解析
    int32_t matCount = reader.readInt32();
    if (matCount > 0 && matCount < 100000)
    {
        outModel.materials.resize(static_cast<size_t>(matCount));
        for (int32_t i = 0; i < matCount; ++i)
        {
            PmxMaterialInfo& mat = outModel.materials[static_cast<size_t>(i)];
            reader.skipText(); // name
            reader.skipText(); // name_e
            float diff[4];
            reader.readFloats(diff, 4);
            mat.diffuseAlpha = diff[3];
            reader.skip(28); // specular(16) + ambient(12)
            mat.drawFlags = reader.readUInt8();
            reader.skip(16); // edge_color(16)
            mat.edgeSize = reader.readFloat();
            reader.skip(static_cast<size_t>(texIdxSize) * 2); // texture + sphere_texture
            reader.skip(1); // sphere_mode
            uint8_t sharedToon = reader.readUInt8();
            if (sharedToon == 1)
            {
                reader.skip(1);
            }
            else
            {
                reader.skip(static_cast<size_t>(texIdxSize));
            }
            reader.skipText(); // comment
            int32_t matVertCount = std::max(0, reader.readInt32());
            mat.faceCount = matVertCount / 3;
        }
    }

    // ボーンデータの解析 (ボーン総数取得およびモーフ領域到達のための読み進め)
    int32_t boneCount = reader.readInt32();
    outModel.boneCount = std::max(0, boneCount);
    for (int32_t i = 0; i < boneCount && !reader.eof(); ++i)
    {
        reader.skipText(); // name
        reader.skipText(); // name_e
        reader.skip(12);   // location (float * 3)
        reader.skip(static_cast<size_t>(boneIdxSize)); // parent
        reader.skip(4);    // transform_level (int32)
        uint16_t bFlags = reader.readUInt16();

        if (bFlags & 0x0001)
        {
            reader.skip(static_cast<size_t>(boneIdxSize));
        }
        else
        {
            reader.skip(12);
        }

        if ((bFlags & 0x0100) || (bFlags & 0x0200))
        {
            reader.skip(static_cast<size_t>(boneIdxSize) + 4);
        }
        if (bFlags & 0x0400)
        {
            reader.skip(12);
        }
        if (bFlags & 0x0800)
        {
            reader.skip(24);
        }
        if (bFlags & 0x2000)
        {
            reader.skip(4);
        }
        if (bFlags & 0x0020) // IK
        {
            reader.skip(static_cast<size_t>(boneIdxSize) + 8); // target + loop(4) + limit_angle(4)
            int32_t linkCount = reader.readInt32();
            for (int32_t lk = 0; lk < linkCount && !reader.eof(); ++lk)
            {
                reader.skip(static_cast<size_t>(boneIdxSize));
                uint8_t hasLim = reader.readUInt8();
                if (hasLim == 1)
                {
                    reader.skip(24);
                }
            }
        }
    }

    // モーフデータの解析 (頂点モーフの抽出)
    if (!reader.eof() && reader.remaining() >= 4)
    {
        int32_t morphCount = reader.readInt32();
        int32_t vertexMorphCounter = 0;
        for (int32_t m = 0; m < morphCount && !reader.eof(); ++m)
        {
            std::string mName = reader.readTextUtf8(encodingFlag);
            std::string mNameEn = reader.readTextUtf8(encodingFlag);
            reader.skip(1); // panel
            uint8_t morphType = reader.readUInt8();
            int32_t offsetCount = reader.readInt32();
            if (offsetCount < 0) offsetCount = 0;

            if (morphType == 1) // 頂点モーフ
            {
                PmxVertexMorph vm;
                vm.morphIndex = m;
                vm.vertexMorphOrder = vertexMorphCounter++;
                vm.nameUtf8 = std::move(mName);
                vm.nameEnUtf8 = std::move(mNameEn);
                vm.offsets.reserve(static_cast<size_t>(offsetCount));

                for (int32_t k = 0; k < offsetCount; ++k)
                {
                    int32_t vIdx = reader.readVertexIndex(vtxIdxSize);
                    float off[3];
                    reader.readFloats(off, 3);
                    if (vIdx >= 0 && vIdx < vtxCount)
                    {
                        PmxVertexMorphOffset vmo;
                        vmo.vertexIndex = vIdx;
                        vmo.offset[0] = off[0];
                        vmo.offset[1] = off[1];
                        vmo.offset[2] = off[2];
                        vm.offsets.push_back(vmo);
                    }
                }
                outModel.vertexMorphs.push_back(std::move(vm));
            }
            else if (morphType == 0) // グループモーフ
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(morphIdxSize) + 4));
            }
            else if (morphType == 2) // ボーンモーフ
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(boneIdxSize) + 28));
            }
            else if (morphType >= 3 && morphType <= 7) // UVモーフ
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(vtxIdxSize) + 16));
            }
            else if (morphType == 8) // 材質モーフ
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(matIdxSize) + 113));
            }
            else if (morphType == 9) // Flip (PMX 2.1)
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(morphIdxSize) + 4));
            }
            else if (morphType == 10) // Impulse (PMX 2.1)
            {
                reader.skip(static_cast<size_t>(offsetCount) * (static_cast<size_t>(rigidIdxSize) + 25));
            }
        }
    }

    return true;
}

} // namespace mmd_fast
