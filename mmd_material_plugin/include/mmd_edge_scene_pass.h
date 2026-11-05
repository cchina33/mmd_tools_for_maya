#ifndef MMD_EDGE_SCENE_PASS_H
#define MMD_EDGE_SCENE_PASS_H

// MMD edge pass that is CALLED from MMDRenderOverride.
// mmdMaterial itself (MPxSurfaceShadingNodeOverride / mayaPhongSurface) is not touched,
// so texture handling stays exactly as it is.

#include "mmd_render_override.h"   // MMDSceneRender (targets / camera override handling)

#include <maya/MViewport2Renderer.h>
#include <maya/MShaderManager.h>
#include <maya/MSelectionList.h>
#include <maya/MString.h>

class MMDEdgeScenePass : public MMDSceneRender
{
public:
    explicit MMDEdgeScenePass(const MString& name);
    ~MMDEdgeScenePass() override;

    // Create the shader instance once (call from setup()).
    bool initShader();
    void releaseShader();

    // Collect meshes that have a mmdMaterial with edgeEnable = true.
    // Throttled to every 0.5 s unless force is true.
    // Returns true when at least one target mesh exists.
    bool refreshTargets(bool force);

    // sizePx: base edge width in pixels. debugMode 1: show COLOR0 instead of edge color.
    void setEdgeParams(const float color[4], float sizePx, int debugMode);

    const MHWRender::MShaderInstance* shaderOverride() override;
    const MSelectionList* objectSetOverride() override;
    MHWRender::MSceneRender::MCullingOption cullingOverride() override;
    void preSceneRender(const MHWRender::MDrawContext& context) override;

private:
    MHWRender::MShaderInstance* mShader;
    MSelectionList mTargets;
    float  mEdgeColor[4];
    float  mEdgeSizePx;
    int    mDebugMode;
    double mLastRefreshSec;
    bool   mHasTargets;
};

#endif // MMD_EDGE_SCENE_PASS_H
