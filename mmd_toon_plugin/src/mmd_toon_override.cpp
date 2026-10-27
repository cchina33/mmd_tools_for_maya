#include "mmd_toon_override.h"
#include "mmd_toon_node.h"
#include "mmd_toon_shader_code.h"

#include <maya/MViewport2Renderer.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MPlug.h>
#include <maya/MDataHandle.h>
#include <maya/MGlobal.h>

MHWRender::MPxShaderOverride* MMDToonOverride::Creator(const MObject& obj)
{
    return new MMDToonOverride(obj);
}

MMDToonOverride::MMDToonOverride(const MObject& obj)
    : MHWRender::MPxShaderOverride(obj)
    , fObject(obj)
    , fShaderInstance(nullptr)
    , fDiffuseColor(0.8f, 0.8f, 0.8f, 1.0f)
    , fDiffuseAlpha(1.0f)
    , fAmbientColor(0.0f, 0.0f, 0.0f, 1.0f)
    , fSpecularColor(0.0f, 0.0f, 0.0f, 1.0f)
    , fSpecularPower(5.0f)
    , fTransparency(0.0f, 0.0f, 0.0f, 1.0f)
    , fSphereMode(0)
    , fToonMode(1)
    , fLightMode(1)
    , fShadowMode(1)
    , fShadowBias(0.001f)
    , fIsTransparent(false)
{
}

MMDToonOverride::~MMDToonOverride()
{
    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (theRenderer)
    {
        const MHWRender::MShaderManager* shaderMgr = theRenderer->getShaderManager();
        if (shaderMgr && fShaderInstance)
        {
            shaderMgr->releaseShader(fShaderInstance);
            fShaderInstance = nullptr;
        }
    }
}

MHWRender::DrawAPI MMDToonOverride::supportedDrawAPIs() const
{
    // OpenGL Core Profile、DirectX 11、およびOpenGL Legacyに対応
    return MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile;
}

void MMDToonOverride::initShader()
{
    if (fShaderInstance)
    {
        return;
    }

    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (!theRenderer)
    {
        return;
    }

    const MHWRender::MShaderManager* shaderMgr = theRenderer->getShaderManager();
    if (!shaderMgr)
    {
        return;
    }

    // OGSFX バッファからのシェーダーインスタンス生成
    unsigned int bufferSize = static_cast<unsigned int>(strlen(g_mmdToonOGSFX));
    fShaderInstance = shaderMgr->getEffectsBufferShader(
        g_mmdToonOGSFX,
        bufferSize,
        "Main"
    );

    // OGSFX 生成に失敗した場合は安定した標準フラグメントへ安全にフォールバック
    if (!fShaderInstance)
    {
        fShaderInstance = shaderMgr->getFragmentShader("mayaPhongSurface", "Main", true);
    }
}

MString MMDToonOverride::initialize(
    const MHWRender::MPxShaderOverride::MInitContext& initContext,
    MSharedPtr<MUserData>& data)
{
    initShader();

    if (fShaderInstance)
    {
        // シェーダーが必要とするジオメトリストリーム（位置、法線、UV等）を自動構成
        setGeometryRequirements(*fShaderInstance);
    }

    return MString("Main");
}

void MMDToonOverride::updateDG(MObject object)
{
    if (object.isNull())
    {
        object = fObject;
    }

    MStatus status;
    MFnDependencyNode depNode(object, &status);
    if (!status)
    {
        return;
    }

    // 基本カラー
    MPlug cPlug = depNode.findPlug("color", true, &status);
    if (status == MS::kSuccess && cPlug.numChildren() >= 3)
    {
        fDiffuseColor.r = cPlug.child(0).asFloat();
        fDiffuseColor.g = cPlug.child(1).asFloat();
        fDiffuseColor.b = cPlug.child(2).asFloat();
        fDiffuseColor.a = 1.0f;
    }

    // ディフューズアルファ
    MPlug daPlug = depNode.findPlug("diffuseAlpha", true, &status);
    if (status == MS::kSuccess)
    {
        fDiffuseAlpha = daPlug.asFloat();
    }

    // アンビエントカラー（MMD本家では環境反射係数、自己発光防止のため初期値0）
    MPlug ambPlug = depNode.findPlug("ambientColor", true, &status);
    if (status == MS::kSuccess && ambPlug.numChildren() >= 3)
    {
        fAmbientColor.r = ambPlug.child(0).asFloat();
        fAmbientColor.g = ambPlug.child(1).asFloat();
        fAmbientColor.b = ambPlug.child(2).asFloat();
        fAmbientColor.a = 1.0f;
    }

    // スペキュラカラー
    MPlug scPlug = depNode.findPlug("specularColor", true, &status);
    if (status == MS::kSuccess && scPlug.numChildren() >= 3)
    {
        fSpecularColor.r = scPlug.child(0).asFloat();
        fSpecularColor.g = scPlug.child(1).asFloat();
        fSpecularColor.b = scPlug.child(2).asFloat();
        fSpecularColor.a = 1.0f;
    }

    // スペキュラパワー
    MPlug spPlug = depNode.findPlug("specularPower", true, &status);
    if (status == MS::kSuccess)
    {
        fSpecularPower = spPlug.asFloat();
    }

    // 透過度
    MPlug transPlug = depNode.findPlug("transparency", true, &status);
    if (status == MS::kSuccess && transPlug.numChildren() >= 3)
    {
        fTransparency.r = transPlug.child(0).asFloat();
        fTransparency.g = transPlug.child(1).asFloat();
        fTransparency.b = transPlug.child(2).asFloat();
        fTransparency.a = 1.0f;
    }

    fIsTransparent = (fTransparency.r > 0.01f || fTransparency.g > 0.01f || fTransparency.b > 0.01f || fDiffuseAlpha < 0.99f);

    // スフィアモード
    MPlug smPlug = depNode.findPlug("sphereMode", true, &status);
    if (status == MS::kSuccess)
    {
        fSphereMode = smPlug.asInt();
    }

    // トゥーンモード
    MPlug tmPlug = depNode.findPlug("toonMode", true, &status);
    if (status == MS::kSuccess)
    {
        fToonMode = tmPlug.asInt();
    }

    // ライトモード
    MPlug lmPlug = depNode.findPlug("lightMode", true, &status);
    if (status == MS::kSuccess)
    {
        fLightMode = lmPlug.asInt();
    }

    // シャドウモード
    MPlug shdmPlug = depNode.findPlug("shadowMode", true, &status);
    if (status == MS::kSuccess)
    {
        fShadowMode = shdmPlug.asInt();
    }

    // シャドウバイアス
    MPlug shdbPlug = depNode.findPlug("shadowBias", true, &status);
    if (status == MS::kSuccess)
    {
        fShadowBias = shdbPlug.asFloat();
    }
}

void MMDToonOverride::updateDevice()
{
    if (!fShaderInstance)
    {
        return;
    }

    // シェーダーインスタンスのUniform変数を更新
    const float diffCol[3] = { fDiffuseColor.r, fDiffuseColor.g, fDiffuseColor.b };
    fShaderInstance->setParameter("gDiffuseColor", diffCol);

    fShaderInstance->setParameter("gDiffuseAlpha", fDiffuseAlpha);

    const float ambCol[3] = { fAmbientColor.r, fAmbientColor.g, fAmbientColor.b };
    fShaderInstance->setParameter("gAmbientColor", ambCol);

    const float specCol[3] = { fSpecularColor.r, fSpecularColor.g, fSpecularColor.b };
    fShaderInstance->setParameter("gSpecularColor", specCol);

    fShaderInstance->setParameter("gSpecularPower", fSpecularPower);

    const float transCol[3] = { fTransparency.r, fTransparency.g, fTransparency.b };
    fShaderInstance->setParameter("gTransparency", transCol);

    fShaderInstance->setParameter("gSphereMode", fSphereMode);
    fShaderInstance->setParameter("gToonMode", fToonMode);
    fShaderInstance->setParameter("gLightMode", fLightMode);
    fShaderInstance->setParameter("gShadowEnabled", (fShadowMode > 0));
    fShaderInstance->setParameter("gShadowBias", fShadowBias);

    // 透過フラグの設定
    fShaderInstance->setIsTransparent(fIsTransparent);
}

bool MMDToonOverride::draw(
    MHWRender::MDrawContext& context,
    const MHWRender::MRenderItemList& renderItemList) const
{
    if (fShaderInstance)
    {
        const unsigned int passCount = fShaderInstance->getPassCount(context);
        for (unsigned int i = 0; i < passCount; ++i)
        {
            fShaderInstance->activatePass(context, i);
            MHWRender::MPxShaderOverride::drawGeometry(context);
        }
    }
    return true;
}

MHWRender::MShaderInstance* MMDToonOverride::shaderInstance(MHWRender::MDrawContext& context) const
{
    return fShaderInstance;
}

MHWRender::MShaderInstance* MMDToonOverride::shaderInstance() const
{
    return fShaderInstance;
}

bool MMDToonOverride::isTransparent()
{
    return fIsTransparent;
}

