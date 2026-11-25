#ifndef MMD_EDGE_SCENE_PASS_H
#define MMD_EDGE_SCENE_PASS_H

// MMD edge pass that is CALLED from MMDRenderOverride.
// mmdMaterial itself (MPxSurfaceShadingNodeOverride / mayaPhongSurface) is not touched,
// so texture handling stays exactly as it is.

#include "mmd_render_override.h"   // MMDSceneRender (targets / camera override handling)

#include <maya/MViewport2Renderer.h>
#include <maya/MShaderManager.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPathArray.h>
#include <maya/MString.h>
#include <map>
#include <string>
#include <vector>

class MMDEdgeScenePass : public MMDSceneRender
{
public:
    explicit MMDEdgeScenePass(const MString& name);
    ~MMDEdgeScenePass() override;

    // シェーダーインスタンスを生成（setup() から呼び出し）
    bool initShader();
    void releaseShader();

    // edgeEnable が有効な mmdMaterial を持つメッシュを収集し、材質モーフによる
    // 透過・エッジ変化を頂点カラーセット mmd_edge_scale に動的反映する
    bool refreshTargets(bool force);

    // sizePx: 基準エッジ幅（ピクセル単位）、debugMode: デバッグ表示フラグ
    void setEdgeParams(const float color[4], float sizePx, int debugMode);

    const MHWRender::MShaderInstance* shaderOverride() override;
    const MSelectionList* objectSetOverride() override;
    MHWRender::MSceneRender::MCullingOption cullingOverride() override;
    void preSceneRender(const MHWRender::MDrawContext& context) override;

private:
    struct MeshEdgeCache
    {
        std::vector<float> srcVertexScales;
        std::vector<float> lastSgScales;
    };

    void syncMeshEdgeColors(const MDagPath& path, bool force);

    MHWRender::MShaderInstance* mShader;
    MSelectionList mTargets;
    MDagPathArray  mTargetPaths;
    std::map<std::string, MeshEdgeCache> mMeshCaches;
    float  mEdgeColor[4];
    float  mEdgeSizePx;
    int    mDebugMode;
    double mLastRefreshSec;
    bool   mHasTargets;
};

#endif // MMD_EDGE_SCENE_PASS_H
