#include "mmd_edge_scene_pass.h"
#include "mmd_edge_shader_code.h"

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

#include <chrono>
#include <cstring>

namespace
{
    double nowSec()
    {
        using namespace std::chrono;
        return duration<double>(steady_clock::now().time_since_epoch()).count();
    }

    // True when at least one shading group of the mesh has a mmdMaterial with edgeEnable = true.
    bool usesEdgeEnabledMmdMaterial(const MDagPath& path)
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
            MFnDependencyNode sg(shaders[i], &st);
            if (!st) continue;

            MPlug surf = sg.findPlug("surfaceShader", true, &st);
            if (!st) continue;

            MPlugArray srcs;
            surf.connectedTo(srcs, true, false);
            for (unsigned int j = 0; j < srcs.length(); ++j)
            {
                MFnDependencyNode shd(srcs[j].node(), &st);
                if (!st || shd.typeName() != "mmdMaterial") continue;

                bool enabled = true;
                MPlug en = shd.findPlug("edgeEnable", true, &st);
                if (st) en.getValue(enabled);
                if (enabled) return true;
            }
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
    // MMDSceneRender already sets kClearNone (the MMDClearOperation clears the targets).
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
        else if (api == MHWRender::kOpenGLCoreProfile || api == MHWRender::kOpenGL)
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
        MGlobal::displayError("[MMD Edge] failed to create the edge shader instance (check the Output Window for shader compile errors).");
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

bool MMDEdgeScenePass::refreshTargets(bool force)
{
    const double t = nowSec();
    if (!force && (t - mLastRefreshSec) < 0.5) return mHasTargets;
    mLastRefreshSec = t;

    mTargets.clear();

    MItDag it(MItDag::kDepthFirst, MFn::kMesh);
    for (; !it.isDone(); it.next())
    {
        MDagPath path;
        if (!it.getPath(path)) continue;

        MFnDagNode dn(path);
        if (dn.isIntermediateObject()) continue;

        if (usesEdgeEnabledMmdMaterial(path))
        {
            mTargets.add(path);
        }
    }

    mHasTargets = !mTargets.isEmpty();
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
    // Draw only back faces (the pushed-out hull).
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
