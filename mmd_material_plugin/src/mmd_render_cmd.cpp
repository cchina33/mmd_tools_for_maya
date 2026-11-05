#include "mmd_render_cmd.h"
#include "mmd_render_override.h"

#include <maya/MGlobal.h>
#include <maya/MRenderView.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MRenderTargetManager.h>
#include <maya/MDagPath.h>
#include <maya/MItDag.h>
#include <maya/MFnCamera.h>
#include <maya/MSelectionList.h>
#include <maya/M3dView.h>
#include <maya/MStringArray.h>
#include <vector>

const char* MMDRenderCmd::kCommandName = "mmdRender";

MMDRenderCmd::MMDRenderCmd()
    : mWidth(1280)
    , mHeight(720)
    , mCameraName("")
    , mBatchMode(false)
{
}

MMDRenderCmd::~MMDRenderCmd()
{
}

void* MMDRenderCmd::creator()
{
    return new MMDRenderCmd();
}

MSyntax MMDRenderCmd::newSyntax()
{
    MSyntax syntax;

    // 解像度幅フラグ
    syntax.addFlag("-w", "-width", MSyntax::kLong);
    // 解像度高さフラグ
    syntax.addFlag("-h", "-height", MSyntax::kLong);
    // レンダリングカメラフラグ
    syntax.addFlag("-cam", "-camera", MSyntax::kString);
    // バッチモードフラグ
    syntax.addFlag("-b", "-batch", MSyntax::kBoolean);

    return syntax;
}

MStatus MMDRenderCmd::parseArgs(const MArgList& args)
{
    MStatus status;
    MArgDatabase argData(syntax(), args, &status);
    if (!status)
    {
        return status;
    }

    if (argData.isFlagSet("-w"))
    {
        int w = 1280;
        argData.getFlagArgument("-w", 0, w);
        if (w > 0) mWidth = static_cast<unsigned int>(w);
    }

    if (argData.isFlagSet("-h"))
    {
        int h = 720;
        argData.getFlagArgument("-h", 0, h);
        if (h > 0) mHeight = static_cast<unsigned int>(h);
    }

    if (argData.isFlagSet("-cam"))
    {
        argData.getFlagArgument("-cam", 0, mCameraName);
    }

    if (argData.isFlagSet("-b"))
    {
        argData.getFlagArgument("-b", 0, mBatchMode);
    }

    return MS::kSuccess;
}

MStatus MMDRenderCmd::doIt(const MArgList& args)
{
    MStatus status = parseArgs(args);
    if (!status)
    {
        return status;
    }

    // Render View ウィンドウの存在確認
    if (!MRenderView::doesRenderEditorExist())
    {
        MGlobal::displayWarning("[MMD Renderer] Render View window does not exist (batch or hidden).");
        if (mBatchMode)
        {
            return MS::kSuccess;
        }
    }

    // レンダリング対象カメラの探索と解決
    MDagPath cameraPath;
    if (mCameraName.length() > 0)
    {
        MSelectionList sel;
        sel.add(mCameraName);
        if (!sel.isEmpty())
        {
            sel.getDagPath(0, cameraPath);
            if (!cameraPath.hasFn(MFn::kCamera))
            {
                cameraPath.extendToShape();
            }
        }
    }

    // カメラ名未指定または見つからない場合は標準の persp カメラを探索
    if (!cameraPath.isValid() || !cameraPath.hasFn(MFn::kCamera))
    {
        MItDag it(MItDag::kDepthFirst, MFn::kCamera);
        while (!it.isDone())
        {
            MDagPath curPath;
            it.getPath(curPath);
            MFnCamera fnCam(curPath);
            if (fnCam.name() == "perspShape" || fnCam.name() == "persp")
            {
                cameraPath = curPath;
                break;
            }
            it.next();
        }
    }

    if (!cameraPath.isValid())
    {
        MGlobal::displayError("[MMD Renderer] Valid rendering camera not found.");
        return MS::kFailure;
    }

    // Render View に対象カメラを設定
    MRenderView::setCurrentCamera(cameraPath);

    // Viewport 2.0 レンダラーおよび MMDRenderOverride の取得
    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (!theRenderer)
    {
        MGlobal::displayError("[MMD Renderer] Failed to initialize Viewport 2.0 renderer.");
        return MS::kFailure;
    }

    const MHWRender::MRenderOverride* rOverride = theRenderer->findRenderOverride("mmdRenderOverride");
    if (!rOverride)
    {
        MGlobal::displayError("[MMD Renderer] mmdRenderOverride not found. Please ensure plugin is loaded.");
        return MS::kFailure;
    }

    MMDRenderOverride* mmdOverride = const_cast<MMDRenderOverride*>(dynamic_cast<const MMDRenderOverride*>(rOverride));
    if (!mmdOverride)
    {
        MGlobal::displayError("[MMD Renderer] Failed to cast MMDRenderOverride class instance.");
        return MS::kFailure;
    }

    // 指定解像度に合わせてオフスクリーンレンダーターゲットを確保・リサイズ
    mmdOverride->updateRenderTargets(mWidth, mHeight);

    MHWRender::MRenderTarget* colorTarget = mmdOverride->getColorTarget();
    MHWRender::MRenderTarget* depthTarget = mmdOverride->getDepthTarget();

    if (!colorTarget || !depthTarget)
    {
        MGlobal::displayError("[MMD Renderer] Failed to allocate offscreen render targets.");
        return MS::kFailure;
    }

    // カメラ Shape 名の取得
    MFnCamera fnCamera(cameraPath);
    MString cameraShapeName = fnCamera.name();

    // 画面上に表示されている可視 3D パネルの探索（フォールバック用）
    MString visiblePanel = "modelPanel4";
    MStringArray panels;
    MGlobal::executeCommand("getPanel -type modelPanel", panels);
    for (unsigned int i = 0; i < panels.length(); ++i)
    {
        int isVis = 0;
        MGlobal::executeCommand(MString("panel -query -visible \"") + panels[i] + "\"", isVis);
        if (isVis != 0)
        {
            visiblePanel = panels[i];
            break;
        }
    }

    // オフスクリーンレンダリングモードおよびカメラを設定
    mmdOverride->setOffscreenMode(true, cameraPath);

    // 出力ターゲットサイズおよびレンダラーオーバーライドを設定
    theRenderer->setOutputTargetOverrideSize(mWidth, mHeight);
    theRenderer->setRenderOverrideName("mmdRenderOverride");

    // オフスクリーンターゲットへのレンダリングを実行（カラーおよび深度の2面を供給）
    MHWRender::MRenderTarget* targets[2] = { colorTarget, depthTarget };
    const unsigned int targetCount = (depthTarget != nullptr) ? 2 : 1;
    bool renderOk = false;
    MString successfulSource = "";

    // 描画ソースの候補を順次試行
    MString sourcesToTry[5] = {
        MString("batch:") + cameraShapeName,
        MString("batch:") + cameraPath.partialPathName(),
        MString("viewport:") + visiblePanel,
        visiblePanel,
        MString("modelPanel4")
    };

    for (int sIdx = 0; sIdx < 5; ++sIdx)
    {
        const MString& trySource = sourcesToTry[sIdx];
        if (theRenderer->render(trySource, targets, targetCount))
        {
            renderOk = true;
            successfulSource = trySource;
            break;
        }
    }

    // 2面での描画に失敗した場合はカラー単面で再試行
    if (!renderOk)
    {
        MHWRender::MRenderTarget* singleTarget[1] = { colorTarget };
        for (int sIdx = 0; sIdx < 5; ++sIdx)
        {
            const MString& trySource = sourcesToTry[sIdx];
            if (theRenderer->render(trySource, singleTarget, 1))
            {
                renderOk = true;
                successfulSource = trySource;
                break;
            }
        }
    }

    // レンダラー設定を通常状態へ復帰
    theRenderer->setRenderOverrideName("");
    theRenderer->unsetOutputTargetOverrideSize();
    mmdOverride->setOffscreenMode(false, MDagPath());

    if (!renderOk)
    {
        MGlobal::displayWarning("[MMD Renderer] Render failed on all candidate sources.");
    }
    else
    {
        MGlobal::displayInfo(MString("[MMD Renderer] Render succeeded using source: ") + successfulSource);
    }

    // レンダーターゲットから GPU ピクセルバッファを読み戻し
    int rowPitch = 0;
    size_t slicePitch = 0;
    void* rawData = colorTarget->rawData(rowPitch, slicePitch);
    if (!rawData)
    {
        MGlobal::displayError("[MMD Renderer] Failed to acquire pixel buffer from render target.");
        return MS::kFailure;
    }

    // Render View の描画セッション開始
    status = MRenderView::startRender(mWidth, mHeight, false, true);
    if (!status)
    {
        MHWRender::MRenderTarget::freeRawData(rawData);
        MGlobal::displayError("[MMD Renderer] Failed to start Render View rendering session.");
        return status;
    }

    // ピクセルデータの上下反転（DirectXテクスチャ空間 -> MRenderView座標系）および配列生成
    const unsigned char* bytePtr = static_cast<const unsigned char*>(rawData);
    std::vector<RV_PIXEL> pixels(mWidth * mHeight);

    for (unsigned int y = 0; y < mHeight; ++y)
    {
        // DirectX の上端行 (y) を Render View の下端行 (mHeight - 1 - y) にマッピング
        unsigned int srcY = y;
        unsigned int dstY = mHeight - 1 - y;
        const unsigned char* srcRow = bytePtr + (srcY * rowPitch);

        for (unsigned int x = 0; x < mWidth; ++x)
        {
            unsigned int srcIdx = x * 4;
            unsigned int dstIdx = dstY * mWidth + x;

            // RGBA 各チャンネルを 0.0〜255.0 の float 値へ展開
            pixels[dstIdx].r = static_cast<float>(srcRow[srcIdx + 0]);
            pixels[dstIdx].g = static_cast<float>(srcRow[srcIdx + 1]);
            pixels[dstIdx].b = static_cast<float>(srcRow[srcIdx + 2]);
            pixels[dstIdx].a = static_cast<float>(srcRow[srcIdx + 3]);
        }
    }

    // 描画ピクセルデータのサンプリング検証（非ゼロピクセルの有無確認）
    size_t nonZeroCount = 0;
    for (size_t i = 0; i < pixels.size(); ++i)
    {
        if (pixels[i].r > 0.0f || pixels[i].g > 0.0f || pixels[i].b > 0.0f || pixels[i].a > 0.0f)
        {
            nonZeroCount++;
        }
    }
    if (nonZeroCount == 0)
    {
        MGlobal::displayWarning("[MMD Renderer] Warning: Render target buffer is zeroed (no pixels written).");
    }
    else
    {
        MGlobal::displayInfo(MString("[MMD Renderer] Active pixels drawn: ") + static_cast<int>(nonZeroCount));
    }

    // Render View へピクセルデータを一括転送
    status = MRenderView::updatePixels(0, mWidth - 1, 0, mHeight - 1, pixels.data());
    if (!status)
    {
        MGlobal::displayWarning("[MMD Renderer] Failed to update some pixels in Render View.");
    }

    // 描画領域の画面再描画を確定
    MRenderView::refresh(0, mWidth - 1, 0, mHeight - 1);

    // Render View のレンダリング終了
    MRenderView::endRender();

    // GPU ピクセルバッファの解放
    MHWRender::MRenderTarget::freeRawData(rawData);

    MGlobal::displayInfo(MString("[MMD Renderer] Render complete: ") + mWidth + "x" + mHeight);
    return MS::kSuccess;
}
