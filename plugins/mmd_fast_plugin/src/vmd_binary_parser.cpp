#include "vmd_binary_parser.h"

#include <fstream>
#include <cstring>
#include <cmath>
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

VmdParsedMotion VmdBinaryCache::s_cachedMotion;

namespace {

// Shift-JIS (CP932) 固定長バイト列（0x00 または 0xFD パディング）を UTF-8 へ変換
std::string decodeSjisToUtf8(const uint8_t* rawBytes, size_t maxLen)
{
    size_t len = 0;
    while (len < maxLen && rawBytes[len] != 0x00 && rawBytes[len] != 0xFD)
    {
        ++len;
    }
    if (len == 0)
    {
        return std::string();
    }

#ifdef _WIN32
    int wlen = MultiByteToWideChar(932, 0, reinterpret_cast<const char*>(rawBytes), static_cast<int>(len), nullptr, 0);
    if (wlen > 0)
    {
        std::wstring wstr(static_cast<size_t>(wlen), L'\0');
        MultiByteToWideChar(932, 0, reinterpret_cast<const char*>(rawBytes), static_cast<int>(len), &wstr[0], wlen);
        int u8len = WideCharToMultiByte(CP_UTF8, 0, wstr.data(), wlen, nullptr, 0, nullptr, nullptr);
        if (u8len > 0)
        {
            std::string u8str(static_cast<size_t>(u8len), '\0');
            WideCharToMultiByte(CP_UTF8, 0, wstr.data(), wlen, &u8str[0], u8len, nullptr, nullptr);
            return u8str;
        }
    }
#endif
    return std::string(reinterpret_cast<const char*>(rawBytes), len);
}

class BinaryReader
{
public:
    BinaryReader(const uint8_t* data, size_t size)
        : m_data(data), m_size(size), m_pos(0)
    {
    }

    bool canRead(size_t bytes) const
    {
        return (m_pos + bytes) <= m_size;
    }

    const uint8_t* readRaw(size_t bytes)
    {
        if (!canRead(bytes))
        {
            return nullptr;
        }
        const uint8_t* ptr = m_data + m_pos;
        m_pos += bytes;
        return ptr;
    }

    uint32_t readUInt32()
    {
        if (!canRead(4))
        {
            m_pos = m_size;
            return 0;
        }
        uint32_t v = 0;
        std::memcpy(&v, m_data + m_pos, 4);
        m_pos += 4;
        return v;
    }

private:
    const uint8_t* m_data;
    size_t m_size;
    size_t m_pos;
};

} // namespace

void VmdBinaryCache::clearCache()
{
    s_cachedMotion = VmdParsedMotion();
}

const VmdParsedMotion* VmdBinaryCache::getOrParse(const std::wstring& wFilePath, bool forceReload, std::string* outError)
{
    if (!forceReload && !s_cachedMotion.filePath.empty() && s_cachedMotion.filePath == wFilePath)
    {
        return &s_cachedMotion;
    }

    VmdParsedMotion parsed;
    if (!parseVmdFile(wFilePath, parsed, outError))
    {
        return nullptr;
    }

    s_cachedMotion = std::move(parsed);
    return &s_cachedMotion;
}

bool VmdBinaryCache::parseVmdFile(const std::wstring& wFilePath, VmdParsedMotion& outMotion, std::string* outError)
{
    std::ifstream ifs(wFilePath.c_str(), std::ios::binary | std::ios::ate);
    if (!ifs.is_open())
    {
        if (outError) *outError = "Failed to open VMD file.";
        return false;
    }

    std::streamsize fileSize = ifs.tellg();
    if (fileSize < 30)
    {
        if (outError) *outError = "VMD file is too small.";
        return false;
    }

    ifs.seekg(0, std::ios::beg);
    std::vector<uint8_t> buffer(static_cast<size_t>(fileSize));
    if (!ifs.read(reinterpret_cast<char*>(buffer.data()), fileSize))
    {
        if (outError) *outError = "Failed to read VMD file buffer.";
        return false;
    }
    ifs.close();

    BinaryReader reader(buffer.data(), buffer.size());
    const uint8_t* headerRaw = reader.readRaw(30);
    if (!headerRaw)
    {
        return false;
    }

    outMotion = VmdParsedMotion();
    outMotion.filePath = wFilePath;

    if (std::memcmp(headerRaw, "Vocaloid Motion Data 0002", 25) == 0)
    {
        outMotion.version = 2;
        const uint8_t* modelNameRaw = reader.readRaw(20);
        if (modelNameRaw)
        {
            outMotion.modelNameUtf8 = decodeSjisToUtf8(modelNameRaw, 20);
        }
    }
    else if (std::memcmp(headerRaw, "Vocaloid Motion Data", 20) == 0)
    {
        outMotion.version = 1;
        const uint8_t* modelNameRaw = reader.readRaw(10);
        if (modelNameRaw)
        {
            outMotion.modelNameUtf8 = decodeSjisToUtf8(modelNameRaw, 10);
        }
    }
    else
    {
        if (outError) *outError = "Unsupported VMD header.";
        return false;
    }

    uint32_t maxFrame = 0;

    // ボーンキーフレーム読み取り (111バイト/個)
    if (reader.canRead(4))
    {
        uint32_t boneCount = reader.readUInt32();
        for (uint32_t i = 0; i < boneCount; ++i)
        {
            const uint8_t* rec = reader.readRaw(111);
            if (!rec)
            {
                break;
            }
            std::string boneName = decodeSjisToUtf8(rec, 15);
            VmdBoneKey bk;
            std::memcpy(&bk.frame, rec + 15, 4);
            std::memcpy(bk.pos, rec + 19, 12);
            std::memcpy(bk.rot, rec + 31, 16);
            std::memcpy(bk.interpolation, rec + 47, 64);

            // クォータニオンの正規化と異常値保護
            float qSq = bk.rot[0] * bk.rot[0] + bk.rot[1] * bk.rot[1] + bk.rot[2] * bk.rot[2] + bk.rot[3] * bk.rot[3];
            if (std::isnan(qSq) || qSq < 1e-8f)
            {
                bk.rot[0] = 0.0f;
                bk.rot[1] = 0.0f;
                bk.rot[2] = 0.0f;
                bk.rot[3] = 1.0f;
            }
            else
            {
                float invLen = 1.0f / std::sqrt(qSq);
                bk.rot[0] *= invLen;
                bk.rot[1] *= invLen;
                bk.rot[2] *= invLen;
                bk.rot[3] *= invLen;
            }

            outMotion.boneTracks[boneName].push_back(bk);
            if (bk.frame > maxFrame)
            {
                maxFrame = bk.frame;
            }
        }
    }

    // 各ボーントラックをフレーム順にソートし、同一フレームの重複キーは後勝ちで統合
    for (auto& kv : outMotion.boneTracks)
    {
        auto& vec = kv.second;
        std::stable_sort(vec.begin(), vec.end(), [](const VmdBoneKey& a, const VmdBoneKey& b) {
            return a.frame < b.frame;
        });
        if (vec.size() > 1)
        {
            std::vector<VmdBoneKey> dedup;
            dedup.reserve(vec.size());
            for (size_t i = 0; i < vec.size(); ++i)
            {
                if (!dedup.empty() && dedup.back().frame == vec[i].frame)
                {
                    dedup.back() = vec[i];
                }
                else
                {
                    dedup.push_back(vec[i]);
                }
            }
            vec.swap(dedup);
        }
    }

    // モーフキーフレーム読み取り (23バイト/個)
    if (reader.canRead(4))
    {
        uint32_t morphCount = reader.readUInt32();
        for (uint32_t i = 0; i < morphCount; ++i)
        {
            const uint8_t* rec = reader.readRaw(23);
            if (!rec)
            {
                break;
            }
            std::string morphName = decodeSjisToUtf8(rec, 15);
            VmdMorphKey mk;
            std::memcpy(&mk.frame, rec + 15, 4);
            std::memcpy(&mk.weight, rec + 19, 4);
            if (std::isnan(mk.weight))
            {
                mk.weight = 0.0f;
            }

            outMotion.morphTracks[morphName].push_back(mk);
            if (mk.frame > maxFrame)
            {
                maxFrame = mk.frame;
            }
        }
    }

    for (auto& kv : outMotion.morphTracks)
    {
        auto& vec = kv.second;
        std::stable_sort(vec.begin(), vec.end(), [](const VmdMorphKey& a, const VmdMorphKey& b) {
            return a.frame < b.frame;
        });
        if (vec.size() > 1)
        {
            std::vector<VmdMorphKey> dedup;
            dedup.reserve(vec.size());
            for (size_t i = 0; i < vec.size(); ++i)
            {
                if (!dedup.empty() && dedup.back().frame == vec[i].frame)
                {
                    dedup.back() = vec[i];
                }
                else
                {
                    dedup.push_back(vec[i]);
                }
            }
            vec.swap(dedup);
        }
    }

    // カメラキーフレーム読み取り (61バイト/個)
    if (reader.canRead(4))
    {
        uint32_t camCount = reader.readUInt32();
        outMotion.cameraFrames.reserve(camCount);
        for (uint32_t i = 0; i < camCount; ++i)
        {
            const uint8_t* rec = reader.readRaw(61);
            if (!rec)
            {
                break;
            }
            VmdCameraKey ck;
            std::memcpy(&ck.frame, rec + 0, 4);
            std::memcpy(&ck.distance, rec + 4, 4);
            std::memcpy(ck.pos, rec + 8, 12);
            std::memcpy(ck.rot, rec + 20, 12);
            std::memcpy(ck.interpolation, rec + 32, 24);
            std::memcpy(&ck.fov, rec + 56, 4);
            ck.perspective = (rec[60] == 0);

            outMotion.cameraFrames.push_back(ck);
            if (ck.frame > maxFrame)
            {
                maxFrame = ck.frame;
            }
        }

        std::stable_sort(outMotion.cameraFrames.begin(), outMotion.cameraFrames.end(), [](const VmdCameraKey& a, const VmdCameraKey& b) {
            return a.frame < b.frame;
        });
    }

    outMotion.maxFrame = maxFrame;
    return true;
}

} // namespace mmd_fast
