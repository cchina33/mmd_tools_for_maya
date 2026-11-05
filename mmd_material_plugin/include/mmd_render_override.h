#ifndef MMD_RENDER_OVERRIDE_H
#define MMD_RENDER_OVERRIDE_H

#include <maya/MViewport2Renderer.h>
#include <maya/MRenderTarget.h>
#include <maya/MString.h>
#include <maya/MDagPath.h>
#include <vector>

// オフスクリーンターゲット対応の背景クリアオペレーション
class MMDClearOperation : public MHWRender::MClearOperation
{
public:
    MMDClearOperation(const MString& name);
    virtual ~MMDClearOperation() override;

    virtual MHWRender::MRenderTarget* const* targetOverrideList(unsigned int &listSize) override;
    void setTargets(MHWRender::MRenderTarget** targets, unsigned int count);

private:
    MHWRender::MRenderTarget** mTargets;
    unsigned int mTargetCount;
};

// MMD独自シーン描画オペレーション (不透明・透過・エッジの描画フィルタ制御、オフスクリーンおよびカメラ制御)
class MMDSceneRender : public MHWRender::MSceneRender
{
public:
    MMDSceneRender(const MString& name, MHWRender::MSceneRender::MSceneFilterOption filter);
    virtual ~MMDSceneRender() override;

    virtual MHWRender::MSceneRender::MSceneFilterOption renderFilterOverride() override;
    virtual MHWRender::MRenderTarget* const* targetOverrideList(unsigned int &listSize) override;
    virtual const MHWRender::MCameraOverride* cameraOverride() override;
    virtual bool enableSRGBWrite() override;

    void setTargets(MHWRender::MRenderTarget** targets, unsigned int count);
    void setCamera(const MDagPath& cameraPath);

private:
    MHWRender::MSceneRender::MSceneFilterOption mFilter;
    MHWRender::MRenderTarget** mTargets;
    unsigned int mTargetCount;
    MHWRender::MCameraOverride mCameraOverride;
    bool mHasCameraOverride;
};

class MMDEdgeScenePass;   // mmd_edge_scene_pass.h (前方宣言)

// Viewport 2.0 ベースの MMD 独自レンダーオーバーライド
// 多層透過（Depth Peeling）および sRGB 色空間の保持、オフスクリーン描画を統括
class MMDRenderOverride : public MHWRender::MRenderOverride
{
public:
    MMDRenderOverride(const MString& name);
    virtual ~MMDRenderOverride() override;

    virtual MHWRender::DrawAPI supportedDrawAPIs() const override;

    virtual bool startOperationIterator() override;
    virtual MHWRender::MRenderOperation* renderOperation() override;
    virtual bool nextRenderOperation() override;

    virtual MStatus setup(const MString& destination) override;
    virtual MStatus cleanup() override;

    virtual MString uiName() const override;

    // オフスクリーン描画および Render View 転送用レンダーターゲット管理
    MHWRender::MRenderTarget* getColorTarget() const { return mColorTarget; }
    MHWRender::MRenderTarget* getDepthTarget() const { return mDepthTarget; }
    void updateRenderTargets(unsigned int width, unsigned int height);
    void releaseRenderTargets();

    // オフスクリーンレンダリングモードおよび対象カメラの設定
    void setOffscreenMode(bool enable, const MDagPath& cameraPath);
    bool isOffscreenMode() const { return mOffscreenMode; }

private:
    MString mUIName;
    int mCurrentOperation;
    std::vector<MHWRender::MRenderOperation*> mRenderOperations;

    // レンダリングパイプラインを構成するオペレーション群
    MMDClearOperation* mClearOp;
    MMDEdgeScenePass* mEdgePass;   // エッジ (裏面) パス: 表面より先に描画
    MMDSceneRender* mSceneRenderOpaque;
    MMDSceneRender* mSceneRenderTransparent;
    MHWRender::MHUDRender* mHudOp;
    MHWRender::MPresentTarget* mPresentOp;

    // オフスクリーンレンダーターゲットバッファ
    MHWRender::MRenderTarget* mColorTarget;
    MHWRender::MRenderTarget* mDepthTarget;
    MHWRender::MRenderTarget* mActiveTargets[2];
    unsigned int mTargetWidth;
    unsigned int mTargetHeight;

    // オフスクリーン制御パラメータ
    bool mOffscreenMode;
    MDagPath mCameraPath;

    // 多層透過および色空間のロック処理
    void enforceDepthPeelingAndColorManagement();
};

#endif // MMD_RENDER_OVERRIDE_H
