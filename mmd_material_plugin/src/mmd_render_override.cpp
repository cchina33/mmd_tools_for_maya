#include "mmd_render_override.h"
#include "mmd_edge_scene_pass.h"

#include <maya/MGlobal.h>
#include <maya/MSelectionList.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MPlug.h>
#include <maya/MRenderTargetManager.h>

// --------------------------------------------------------------------
// MMDClearOperation 実装
// --------------------------------------------------------------------

MMDClearOperation::MMDClearOperation(const MString& name)
    : MHWRender::MClearOperation(name)
    , mTargets(nullptr)
    , mTargetCount(0)
{
}

MMDClearOperation::~MMDClearOperation()
{
    mTargets = nullptr;
}

MHWRender::MRenderTarget* const* MMDClearOperation::targetOverrideList(unsigned int &listSize)
{
    if (mTargets && mTargetCount > 0)
    {
        listSize = mTargetCount;
        return mTargets;
    }
    return nullptr;
}

void MMDClearOperation::setTargets(MHWRender::MRenderTarget** targets, unsigned int count)
{
    mTargets = targets;
    mTargetCount = count;
}

// --------------------------------------------------------------------
// MMDSceneRender 実装
// --------------------------------------------------------------------

MMDSceneRender::MMDSceneRender(const MString& name, MHWRender::MSceneRender::MSceneFilterOption filter)
    : MHWRender::MSceneRender(name)
    , mFilter(filter)
    , mTargets(nullptr)
    , mTargetCount(0)
    , mHasCameraOverride(false)
{
    // 不透明描画の際は、個別のクリアオペレーションを使用するため自身のクリアは無効化
    mClearOperation.setMask(MHWRender::MClearOperation::kClearNone);
}

MMDSceneRender::~MMDSceneRender()
{
    mTargets = nullptr;
}

MHWRender::MSceneRender::MSceneFilterOption MMDSceneRender::renderFilterOverride()
{
    return mFilter;
}

MHWRender::MRenderTarget* const* MMDSceneRender::targetOverrideList(unsigned int &listSize)
{
    if (mTargets && mTargetCount > 0)
    {
        listSize = mTargetCount;
        return mTargets;
    }
    return nullptr;
}

const MHWRender::MCameraOverride* MMDSceneRender::cameraOverride()
{
    if (mHasCameraOverride && mCameraOverride.mCameraPath.isValid())
    {
        return &mCameraOverride;
    }
    return nullptr;
}

bool MMDSceneRender::enableSRGBWrite()
{
    return true;
}

void MMDSceneRender::setTargets(MHWRender::MRenderTarget** targets, unsigned int count)
{
    mTargets = targets;
    mTargetCount = count;
}

void MMDSceneRender::setCamera(const MDagPath& cameraPath)
{
    if (cameraPath.isValid())
    {
        mCameraOverride.mCameraPath = cameraPath;
        mHasCameraOverride = true;
    }
    else
    {
        mHasCameraOverride = false;
    }
}

// --------------------------------------------------------------------
// MMDRenderOverride 実装
// --------------------------------------------------------------------

MMDRenderOverride::MMDRenderOverride(const MString& name)
    : MHWRender::MRenderOverride(name)
    , mUIName("MMD Viewport Renderer")
    , mCurrentOperation(-1)
    , mClearOp(nullptr)
    , mEdgePass(nullptr)
    , mSceneRenderOpaque(nullptr)
    , mSceneRenderTransparent(nullptr)
    , mHudOp(nullptr)
    , mPresentOp(nullptr)
    , mColorTarget(nullptr)
    , mDepthTarget(nullptr)
    , mTargetWidth(0)
    , mTargetHeight(0)
    , mOffscreenMode(false)
{
    mActiveTargets[0] = nullptr;
    mActiveTargets[1] = nullptr;

    // 背景および深度バッファクリアオペレーションの生成
    mClearOp = new MMDClearOperation("mmdClearOp");
    mClearOp->setMask(MHWRender::MClearOperation::kClearAll);
    float clearColor[4] = { 1.0f, 1.0f, 1.0f, 1.0f };   // MMD 同様の白背景
    mClearOp->setClearColor(clearColor);
    mClearOp->setClearDepth(1.0f);
    mRenderOperations.push_back(mClearOp);

    // エッジ (裏面) パス: 表面描画より先に描き、表面で上書きして外周だけを残す
    mEdgePass = new MMDEdgeScenePass("mmdEdgePass");
    mRenderOperations.push_back(mEdgePass);

    // 不透明メッシュおよびエッジの描画オペレーション
    mSceneRenderOpaque = new MMDSceneRender("mmdSceneRenderOpaque", MHWRender::MSceneRender::kRenderOpaqueShadedItems);
    mRenderOperations.push_back(mSceneRenderOpaque);

    // 多層透過メッシュの描画オペレーション
    mSceneRenderTransparent = new MMDSceneRender("mmdSceneRenderTransparent", MHWRender::MSceneRender::kRenderTransparentShadedItems);
    mRenderOperations.push_back(mSceneRenderTransparent);

    // ビューポートHUD表示オペレーション
    mHudOp = new MHWRender::MHUDRender();
    mRenderOperations.push_back(mHudOp);

    // 画面出力（プレゼント）オペレーション
    mPresentOp = new MHWRender::MPresentTarget("mmdPresentOp");
    mRenderOperations.push_back(mPresentOp);
}

MMDRenderOverride::~MMDRenderOverride()
{
    releaseRenderTargets();

    if (mEdgePass)
    {
        mEdgePass->releaseShader();
        delete mEdgePass;
        mEdgePass = nullptr;
    }

    delete mClearOp;
    mClearOp = nullptr;

    delete mSceneRenderOpaque;
    mSceneRenderOpaque = nullptr;

    delete mSceneRenderTransparent;
    mSceneRenderTransparent = nullptr;

    delete mHudOp;
    mHudOp = nullptr;

    delete mPresentOp;
    mPresentOp = nullptr;

    mRenderOperations.clear();
}

MHWRender::DrawAPI MMDRenderOverride::supportedDrawAPIs() const
{
    // DirectX 11 および OpenGL Core Profile に対応
    return MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile;
}

MString MMDRenderOverride::uiName() const
{
    return mUIName;
}

bool MMDRenderOverride::startOperationIterator()
{
    mCurrentOperation = 0;
    while (mCurrentOperation < static_cast<int>(mRenderOperations.size()))
    {
        MHWRender::MRenderOperation* op = mRenderOperations[mCurrentOperation];
        if (op && op->enabled())
        {
            return true;
        }
        mCurrentOperation++;
    }
    return false;
}

MHWRender::MRenderOperation* MMDRenderOverride::renderOperation()
{
    if (mCurrentOperation >= 0 && mCurrentOperation < static_cast<int>(mRenderOperations.size()))
    {
        return mRenderOperations[mCurrentOperation];
    }
    return nullptr;
}

bool MMDRenderOverride::nextRenderOperation()
{
    mCurrentOperation++;
    while (mCurrentOperation < static_cast<int>(mRenderOperations.size()))
    {
        MHWRender::MRenderOperation* op = mRenderOperations[mCurrentOperation];
        if (op && op->enabled())
        {
            return true;
        }
        mCurrentOperation++;
    }
    return false;
}

void MMDRenderOverride::setOffscreenMode(bool enable, const MDagPath& cameraPath)
{
    mOffscreenMode = enable;
    mCameraPath = cameraPath;
}

MStatus MMDRenderOverride::setup(const MString& destination)
{
    // 描画開始前に透過アルゴリズムとカラーマネジメント設定を強制適用
    enforceDepthPeelingAndColorManagement();

    if (mOffscreenMode && mColorTarget && mDepthTarget)
    {
        mActiveTargets[0] = mColorTarget;
        mActiveTargets[1] = mDepthTarget;

        mClearOp->setTargets(mActiveTargets, 2);
        mSceneRenderOpaque->setTargets(mActiveTargets, 2);
        mSceneRenderOpaque->setCamera(mCameraPath);

        mSceneRenderTransparent->setTargets(mActiveTargets, 2);
        mSceneRenderTransparent->setCamera(mCameraPath);

        if (mHudOp)
        {
            mHudOp->setEnabled(false);
        }
        if (mPresentOp)
        {
            mPresentOp->setEnabled(false);
        }
    }
    else
    {
        mClearOp->setTargets(nullptr, 0);
        mSceneRenderOpaque->setTargets(nullptr, 0);
        mSceneRenderOpaque->setCamera(MDagPath());

        mSceneRenderTransparent->setTargets(nullptr, 0);
        mSceneRenderTransparent->setCamera(MDagPath());

        if (mHudOp)
        {
            mHudOp->setEnabled(true);
        }
        if (mPresentOp)
        {
            mPresentOp->setEnabled(true);
        }
    }

    // エッジパス (mmdMaterial 側のシェーディングには触れない別パス)
    if (mEdgePass)
    {
        const bool offscreen = (mOffscreenMode && mColorTarget && mDepthTarget);
        mEdgePass->setTargets(offscreen ? mActiveTargets : nullptr, offscreen ? 2u : 0u);
        mEdgePass->setCamera(offscreen ? mCameraPath : MDagPath());

        // optionVar: mmdEdgeEnable(int) / mmdEdgeSize(float, px) / mmdEdgeDebug(int)
        const bool on = !MGlobal::optionVarExists("mmdEdgeEnable")
                        || MGlobal::optionVarIntValue("mmdEdgeEnable") != 0;
        const float sizePx = MGlobal::optionVarExists("mmdEdgeSize")
                        ? static_cast<float>(MGlobal::optionVarDoubleValue("mmdEdgeSize")) : 1.5f;
        const int debugMode = MGlobal::optionVarExists("mmdEdgeDebug")
                        ? MGlobal::optionVarIntValue("mmdEdgeDebug") : 0;
        const float edgeColor[4] = { 0.0f, 0.0f, 0.0f, 1.0f };

        mEdgePass->setEdgeParams(edgeColor, sizePx, debugMode);
        const bool hasMesh = mEdgePass->refreshTargets(offscreen);   // オフスクリーン時は強制更新
        mEdgePass->setEnabled(on && hasMesh && mEdgePass->initShader());
    }

    return MS::kSuccess;
}

MStatus MMDRenderOverride::cleanup()
{
    mCurrentOperation = -1;

    if (mEdgePass)
    {
        mEdgePass->setTargets(nullptr, 0);
        mEdgePass->setCamera(MDagPath());
    }

    mClearOp->setTargets(nullptr, 0);
    mSceneRenderOpaque->setTargets(nullptr, 0);
    mSceneRenderOpaque->setCamera(MDagPath());

    mSceneRenderTransparent->setTargets(nullptr, 0);
    mSceneRenderTransparent->setCamera(MDagPath());

    if (mHudOp)
    {
        mHudOp->setEnabled(true);
    }
    if (mPresentOp)
    {
        mPresentOp->setEnabled(true);
    }

    return MS::kSuccess;
}

void MMDRenderOverride::enforceDepthPeelingAndColorManagement()
{
    // hardwareRenderingGlobals ノードの透過設定を取得して調整
    MSelectionList sel;
    sel.add("hardwareRenderingGlobals");
    if (!sel.isEmpty())
    {
        MObject node;
        sel.getDependNode(0, node);
        MFnDependencyNode fnNode(node);

        // 透過アルゴリズムを Object Sorting (1) に設定
        // オフスクリーン描画時やマルチパス合成時、Depth Peeling (3) だとレンダーターゲットの中間バッファ分離が破綻し、
        // 不透明描画（肌テクスチャ）が消えて背景色（白）で抜けてしまう現象が発生します。
        // Object Sorting (1) を適用することで、肌の上に目や眉などの透過テクスチャが正常にアルファブレンド合成されます。
        MPlug transPlug = fnNode.findPlug("transparencyAlgorithm", true);
        if (!transPlug.isNull())
        {
            short curVal = 0;
            transPlug.getValue(curVal);
            if (curVal != 1)
            {
                transPlug.setValue(static_cast<short>(1));
            }
        }

        // 透過品質（ソート品質）を設定
        MPlug transQualPlug = fnNode.findPlug("transparencyQuality", true);
        if (!transQualPlug.isNull())
        {
            float curQual = 0.0f;
            transQualPlug.getValue(curQual);
            if (curQual < 0.95f)
            {
                transQualPlug.setValue(1.0f);
            }
        }
    }
}

void MMDRenderOverride::updateRenderTargets(unsigned int width, unsigned int height)
{
    if (mColorTarget && mTargetWidth == width && mTargetHeight == height)
    {
        return;
    }

    releaseRenderTargets();

    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (!theRenderer)
    {
        return;
    }

    const MHWRender::MRenderTargetManager* targetMgr = theRenderer->getRenderTargetManager();
    if (!targetMgr)
    {
        return;
    }

    mTargetWidth = width;
    mTargetHeight = height;

    // カラーターゲット (RGBA8 フォーマット) の生成
    MHWRender::MRenderTargetDescription colorDesc(
        "mmdColorTarget",
        width,
        height,
        1,
        MHWRender::kR8G8B8A8_UNORM,
        0,
        false
    );
    mColorTarget = targetMgr->acquireRenderTarget(colorDesc);

    // 深度バッファターゲット (D24S8 フォーマット) の生成
    MHWRender::MRenderTargetDescription depthDesc(
        "mmdDepthTarget",
        width,
        height,
        1,
        MHWRender::kD24S8,
        0,
        false
    );
    mDepthTarget = targetMgr->acquireRenderTarget(depthDesc);
}

void MMDRenderOverride::releaseRenderTargets()
{
    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (!theRenderer)
    {
        return;
    }

    const MHWRender::MRenderTargetManager* targetMgr = theRenderer->getRenderTargetManager();
    if (!targetMgr)
    {
        return;
    }

    if (mColorTarget)
    {
        targetMgr->releaseRenderTarget(mColorTarget);
        mColorTarget = nullptr;
    }
    if (mDepthTarget)
    {
        targetMgr->releaseRenderTarget(mDepthTarget);
        mDepthTarget = nullptr;
    }

    mTargetWidth = 0;
    mTargetHeight = 0;
}
