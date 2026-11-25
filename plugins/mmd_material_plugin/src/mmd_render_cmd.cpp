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
#include <maya/MImage.h>
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

    // Render View の存在確認（バッチまたは standalone モード時は警告のみ）
    const bool hasRenderEditor = MRenderView::doesRenderEditorExist();
    if (!hasRenderEditor)
    {
        MGlobal::displayWarning("[MMD Renderer] Render View window does not exist (batch or hidden).");
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

    // オフスクリーンレンダリング開始前に DG 評価とエッジ頂点カラーの更新を事前実行
    mmdOverride->preSyncEdgePass();

    // MRenderer に mmdRenderOverride を設定し、Maya 標準の ogsRender（Depth Peeling および
    // 頂点カラーストリーム COLOR0 を正規評価するオフスクリーンパイプライン）で画像を生成
    theRenderer->setRenderOverrideName("mmdRenderOverride");

    int prevFmt = 32;
    MGlobal::executeCommand("getAttr \"defaultRenderGlobals.imageFormat\"", prevFmt);
    MGlobal::executeCommand("setAttr \"defaultRenderGlobals.imageFormat\" 32");

    MString ogsCmd = MString("ogsRender -camera \"") + cameraShapeName + "\" -width " + static_cast<int>(mWidth) + " -height " + static_cast<int>(mHeight);

    MString renderedImgPath;
    MStatus ogsStatus = MGlobal::executeCommand(ogsCmd, renderedImgPath);

    MGlobal::executeCommand(MString("setAttr \"defaultRenderGlobals.imageFormat\" ") + prevFmt);
    theRenderer->setRenderOverrideName("");

    MImage renderedImg;
    bool loadedFromOgs = false;
    if (ogsStatus == MS::kSuccess && renderedImgPath.length() > 0)
    {
        if (renderedImg.readFromFile(renderedImgPath) == MS::kSuccess)
        {
            unsigned int rw = 0, rh = 0;
            renderedImg.getSize(rw, rh);
            if (rw == mWidth && rh == mHeight && renderedImg.pixels() != nullptr)
            {
                loadedFromOgs = true;
            }
        }
    }

    // デバッグ・バッチ検証用: optionVar "mmdRenderDumpPath" が設定されていれば画像を保存
    if (loadedFromOgs && MGlobal::optionVarExists("mmdRenderDumpPath"))
    {
        MString dumpPath = MGlobal::optionVarStringValue("mmdRenderDumpPath");
        if (dumpPath.length() > 0)
        {
            renderedImg.writeToFile(dumpPath, "png");
        }
    }

    if (!loadedFromOgs)
    {
        MGlobal::displayError("[MMD Renderer] Failed to render image via ogsRender.");
        return MS::kFailure;
    }

    // Render View が存在する場合のみ UI 転送を実行
    if (hasRenderEditor)
    {
        status = MRenderView::startRender(mWidth, mHeight, false, true);
        if (!status)
        {
            MGlobal::displayError("[MMD Renderer] Failed to start Render View rendering session.");
            return status;
        }

        // MImage::readFromFile のピクセル配列は左下原点 (bottom-up) のため、そのまま MRenderView へ転送
        const unsigned char* imgBytes = renderedImg.pixels();
        std::vector<RV_PIXEL> pixels(mWidth * mHeight);
        const size_t totalPixels = static_cast<size_t>(mWidth) * static_cast<size_t>(mHeight);
        for (size_t i = 0; i < totalPixels; ++i)
        {
            pixels[i].r = static_cast<float>(imgBytes[i * 4 + 0]);
            pixels[i].g = static_cast<float>(imgBytes[i * 4 + 1]);
            pixels[i].b = static_cast<float>(imgBytes[i * 4 + 2]);
            pixels[i].a = static_cast<float>(imgBytes[i * 4 + 3]);
        }

        status = MRenderView::updatePixels(0, mWidth - 1, 0, mHeight - 1, pixels.data());
        if (!status)
        {
            MGlobal::displayWarning("[MMD Renderer] Failed to update some pixels in Render View.");
        }

        MRenderView::refresh(0, mWidth - 1, 0, mHeight - 1);
        MRenderView::endRender();
    }

    MGlobal::displayInfo(MString("[MMD Renderer] Render complete: ") + mWidth + "x" + mHeight);
    return MS::kSuccess;
}
