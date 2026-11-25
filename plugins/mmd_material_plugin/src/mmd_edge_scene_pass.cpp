#include "mmd_edge_scene_pass.h"
#include "mmd_edge_shader_code.h"

#include <maya/MColor.h>
#include <maya/MColorArray.h>
#include <maya/MDagPath.h>
#include <maya/MDrawContext.h>
#include <maya/MFnDagNode.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnMesh.h>
#include <maya/MGlobal.h>
#include <maya/MIntArray.h>
#include <maya/MItDag.h>
#include <maya/MObjectArray.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MStringArray.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

namespace
{
    const MString kEdgeColorSetName("mmd_edge_scale");
    const MString kEdgeSrcColorSetName("mmd_edge_scale_src");

    double nowSec()
    {
        using namespace std::chrono;
        return duration<double>(steady_clock::now().time_since_epoch()).count();
    }

    // シェーディンググループに接続された mmdMaterial / mmdToonShader から
    // (MMDシェーダー有無, 実効エッジ倍率) を取得する
    bool getShadingGroupEdgeScale(const MObject& sgObj, float& outScale)
    {
        outScale = 0.0f;
        MStatus st;
        MFnDependencyNode sg(sgObj, &st);
        if (!st) return false;

        MPlug surf = sg.findPlug("surfaceShader", true, &st);
        if (!st) return false;

        MPlugArray srcs;
        surf.connectedTo(srcs, true, false);
        for (unsigned int j = 0; j < srcs.length(); ++j)
        {
            MFnDependencyNode shd(srcs[j].node(), &st);
            if (!st) continue;
            const MString typeName = shd.typeName();
            if (typeName != "mmdMaterial" && typeName != "mmdToonShader") continue;

            bool enabled = true;
            MPlug enPlug = shd.findPlug("edgeEnable", true, &st);
            if (st) enPlug.getValue(enabled);

            float edgeSize = 1.0f;
            MPlug esPlug = shd.findPlug("edgeSize", true, &st);
            if (st) esPlug.getValue(edgeSize);

            float diffAlpha = 1.0f;
            MPlug daPlug = shd.findPlug("diffuseAlpha", true, &st);
            if (st) daPlug.getValue(diffAlpha);

            float transAvg = 0.0f;
            MPlug trPlug = shd.findPlug("transparency", true, &st);
            if (st && trPlug.isCompound() && trPlug.numChildren() >= 3)
            {
                float trR = 0.0f, trG = 0.0f, trB = 0.0f;
                trPlug.child(0).getValue(trR);
                trPlug.child(1).getValue(trG);
                trPlug.child(2).getValue(trB);
                transAvg = (trR + trG + trB) / 3.0f;
            }

            const float opacity = std::max(0.0f, std::min(diffAlpha, 1.0f - transAvg));
            if (enabled && edgeSize > 0.001f && opacity > 0.05f)
            {
                outScale = edgeSize * opacity;
            }
            else
            {
                outScale = 0.0f;
            }
            return true;
        }
        return false;
    }

    // メッシュに MMD シェーダーが少なくとも1つ割り当てられているかを判定
    bool usesMmdEdgeMaterial(const MDagPath& path)
    {
        MStatus st;
        MFnMesh mesh(path, &st);
        if (!st) return false;

        MObjectArray shaders;
        MIntArray indices;
        const unsigned int inst = path.isInstanced() ? path.instanceNumber() : 0;
        if (!mesh.getConnectedShaders(inst, shaders, indices)) return false;

        for (unsigned int i = 0; i < shaders.length(); ++i)
        {
            float scale = 0.0f;
            if (getShadingGroupEdgeScale(shaders[i], scale))
            {
                return true;
            }
        }
        return false;
    }

    bool hasColorSet(MFnMesh& mesh, const MString& setName)
    {
        MStringArray names;
        mesh.getColorSetNames(names);
        for (unsigned int i = 0; i < names.length(); ++i)
        {
            if (names[i] == setName) return true;
        }
        return false;
    }
}

MMDEdgeScenePass::MMDEdgeScenePass(const MString& name)
    : MMDSceneRender(name, MHWRender::MSceneRender::kRenderOpaqueShadedItems)
    , mShader(nullptr)
    , mEdgeSizePx(1.5f)
    , mDebugMode(0)
    , mLastRefreshSec(-100.0)
    , mHasTargets(false)
{
    mEdgeColor[0] = 0.0f;
    mEdgeColor[1] = 0.0f;
    mEdgeColor[2] = 0.0f;
    mEdgeColor[3] = 1.0f;
}

MMDEdgeScenePass::~MMDEdgeScenePass()
{
    releaseShader();
}

bool MMDEdgeScenePass::initShader()
{
    if (mShader) return true;

    MHWRender::MRenderer* renderer = MHWRender::MRenderer::theRenderer();
    if (!renderer) return false;

    const MHWRender::MShaderManager* shaderMgr = renderer->getShaderManager();
    if (!shaderMgr) return false;

    const MHWRender::DrawAPI api = renderer->drawAPI();
    try
    {
        if (api == MHWRender::kDirectX11)
        {
            mShader = shaderMgr->getEffectsBufferShader(
                g_mmdEdgeShaderHLSL, (unsigned int)strlen(g_mmdEdgeShaderHLSL),
                "Main", 0, 0, false);
        }
        else if (api == MHWRender::kOpenGLCoreProfile)
        {
            mShader = shaderMgr->getEffectsBufferShader(
                g_mmdEdgeShaderOGSFX, (unsigned int)strlen(g_mmdEdgeShaderOGSFX),
                "Main", 0, 0, false);
        }
    }
    catch (...)
    {
        mShader = nullptr;
    }

    if (!mShader)
    {
        return false;
    }
    return true;
}

void MMDEdgeScenePass::releaseShader()
{
    if (!mShader) return;

    MHWRender::MRenderer* renderer = MHWRender::MRenderer::theRenderer();
    if (renderer)
    {
        const MHWRender::MShaderManager* shaderMgr = renderer->getShaderManager();
        if (shaderMgr) shaderMgr->releaseShader(mShader);
    }
    mShader = nullptr;
}

void MMDEdgeScenePass::syncMeshEdgeColors(const MDagPath& path, bool force)
{
    MStatus st;
    MFnMesh mesh(path, &st);
    if (!st) return;

    MObjectArray shaders;
    MIntArray faceSgIndices;
    const unsigned int inst = path.isInstanced() ? path.instanceNumber() : 0;
    if (!mesh.getConnectedShaders(inst, shaders, faceSgIndices)) return;

    std::vector<float> currentSgScales(shaders.length(), 0.0f);
    for (unsigned int i = 0; i < shaders.length(); ++i)
    {
        float s = 0.0f;
        getShadingGroupEdgeScale(shaders[i], s);
        currentSgScales[i] = s;
    }

    const std::string key = path.fullPathName().asChar();
    MeshEdgeCache& cache = mMeshCaches[key];

    const int numVerts = mesh.numVertices();
    if (numVerts <= 0) return;

    // 変更があるかを判定
    bool changed = force || (cache.lastSgScales.size() != currentSgScales.size()) || ((int)cache.srcVertexScales.size() != numVerts);
    if (!changed)
    {
        for (size_t i = 0; i < currentSgScales.size(); ++i)
        {
            if (std::fabs(cache.lastSgScales[i] - currentSgScales[i]) > 0.0005f)
            {
                changed = true;
                break;
            }
        }
    }
    if (!changed) return;

    // PMX本来の頂点エッジ倍率をキャッシュに読み込む
    if ((int)cache.srcVertexScales.size() != numVerts)
    {
        cache.srcVertexScales.assign(numVerts, 1.0f);
        if (hasColorSet(mesh, kEdgeSrcColorSetName))
        {
            MColorArray srcCols;
            if (mesh.getVertexColors(srcCols, &kEdgeSrcColorSetName) == MS::kSuccess)
            {
                const int lim = std::min(numVerts, (int)srcCols.length());
                for (int v = 0; v < lim; ++v)
                {
                    cache.srcVertexScales[v] = std::max(0.0f, srcCols[v].r);
                }
            }
        }
        else if (hasColorSet(mesh, kEdgeColorSetName))
        {
            MColorArray cols;
            if (mesh.getVertexColors(cols, &kEdgeColorSetName) == MS::kSuccess && cols.length() > 0 && cols[0].g <= 0.5f)
            {
                const int lim = std::min(numVerts, (int)cols.length());
                for (int v = 0; v < lim; ++v)
                {
                    cache.srcVertexScales[v] = std::max(0.0f, cols[v].r);
                }
            }
        }
    }

    if (!hasColorSet(mesh, kEdgeColorSetName))
    {
        MString csName(kEdgeColorSetName);
        mesh.createColorSetDataMesh(csName, false, MFnMesh::kRGBA);
    }
    mesh.setCurrentColorSetName(kEdgeColorSetName);

    const int numPolys = mesh.numPolygons();
    MColorArray colors;
    MIntArray faceIds;
    MIntArray vertIds;

    MIntArray polyVerts;
    for (int f = 0; f < numPolys; ++f)
    {
        const int sgIdx = (f < (int)faceSgIndices.length()) ? faceSgIndices[f] : -1;
        const float matScale = (sgIdx >= 0 && sgIdx < (int)currentSgScales.size()) ? currentSgScales[sgIdx] : 0.0f;

        polyVerts.clear();
        mesh.getPolygonVertices(f, polyVerts);
        for (unsigned int k = 0; k < polyVerts.length(); ++k)
        {
            const int v = polyVerts[k];
            const float vSrc = (v >= 0 && v < numVerts) ? cache.srcVertexScales[v] : 1.0f;
            const float finalScale = (matScale > 0.001f) ? (matScale * vSrc) : 0.0f;
            const float alphaFlag = (finalScale > 0.001f) ? 1.0f : 0.0f;
            colors.append(MColor(finalScale, 1.0f, 0.0f, alphaFlag));
            faceIds.append(f);
            vertIds.append(v);
        }
    }

    mesh.setFaceVertexColors(colors, faceIds, vertIds);
    mesh.updateSurface();
    cache.lastSgScales = currentSgScales;
}

bool MMDEdgeScenePass::refreshTargets(bool force)
{
    const double t = nowSec();
    if (force || (t - mLastRefreshSec) >= 0.25)
    {
        mLastRefreshSec = t;
        mTargets.clear();
        mTargetPaths.clear();

        MItDag it(MItDag::kDepthFirst, MFn::kMesh);
        for (; !it.isDone(); it.next())
        {
            MDagPath path;
            if (!it.getPath(path)) continue;

            MFnDagNode dn(path);
            if (dn.isIntermediateObject()) continue;

            if (usesMmdEdgeMaterial(path))
            {
                mTargets.add(path);
                mTargetPaths.append(path);
            }
        }
        mHasTargets = !mTargets.isEmpty();
    }

    // 毎フレーム各対象メッシュの材質アトリビュート（モーフによる透過やエッジサイズ変化）を確認し、
    // 変化があった場合のみ頂点カラーセット mmd_edge_scale を即座に更新する
    for (unsigned int i = 0; i < mTargetPaths.length(); ++i)
    {
        if (mTargetPaths[i].isValid())
        {
            syncMeshEdgeColors(mTargetPaths[i], force);
        }
    }

    return mHasTargets;
}

void MMDEdgeScenePass::setEdgeParams(const float color[4], float sizePx, int debugMode)
{
    for (int i = 0; i < 4; ++i) mEdgeColor[i] = color[i];
    mEdgeSizePx = sizePx;
    mDebugMode  = debugMode;
}

const MHWRender::MShaderInstance* MMDEdgeScenePass::shaderOverride()
{
    return mShader;
}

const MSelectionList* MMDEdgeScenePass::objectSetOverride()
{
    return &mTargets;
}

MHWRender::MSceneRender::MCullingOption MMDEdgeScenePass::cullingOverride()
{
    // 裏面（押し出したInverted Hull）のみを描画
    return MHWRender::MSceneRender::kCullFrontFaces;
}

void MMDEdgeScenePass::preSceneRender(const MHWRender::MDrawContext& context)
{
    if (!mShader) return;

    int x = 0, y = 0, w = 1, h = 1;
    context.getViewportDimensions(x, y, w, h);
    float screen[2] = { (float)(w > 0 ? w : 1), (float)(h > 0 ? h : 1) };

    mShader->setParameter("gScreenSize", screen);
    mShader->setParameter("gEdgeColor", mEdgeColor);
    mShader->setParameter("gEdgeSize", mEdgeSizePx);
    mShader->setParameter("gEdgeDebug", mDebugMode);
}
