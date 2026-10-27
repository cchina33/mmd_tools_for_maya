#ifndef MMD_TOON_OVERRIDE_H
#define MMD_TOON_OVERRIDE_H

#include <maya/MPxShaderOverride.h>
#include <maya/MObject.h>
#include <maya/MString.h>
#include <maya/MColor.h>
#include <maya/MShaderManager.h>
#include <maya/MDrawContext.h>

class MMDToonOverride : public MHWRender::MPxShaderOverride
{
public:
    static MHWRender::MPxShaderOverride* Creator(const MObject& obj);

    virtual ~MMDToonOverride();

    // 対応レンダリングAPIの返却
    virtual MHWRender::DrawAPI supportedDrawAPIs() const override;

    // 初期化フェーズ
    virtual MString initialize(
        const MHWRender::MPxShaderOverride::MInitContext& initContext,
        MSharedPtr<MUserData>& data) override;

    // DG評価フェーズ（アトリビュート値の取得）
    virtual void updateDG(MObject object) override;

    // デバイス更新フェーズ（ライト情報やシェーダー変数の更新）
    virtual void updateDevice() override;

    // 描画実行フェーズ
    virtual bool draw(
        MHWRender::MDrawContext& context,
        const MHWRender::MRenderItemList& renderItemList) const override;

    // 描画シェーダーインスタンスの返却（Maya 2022+ 推奨シグネチャ）
    virtual MHWRender::MShaderInstance* shaderInstance(MHWRender::MDrawContext& context) const override;
    virtual MHWRender::MShaderInstance* shaderInstance() const override;

    // 透過シェーダー判定
    virtual bool isTransparent() override;

    // リビルド判定
    virtual bool rebuildAlways() override { return false; }

protected:
    MMDToonOverride(const MObject& obj);

    // シェーダーインスタンスの生成
    void initShader();

    // ノードおよびシェーダーインスタンス
    MObject fObject;
    MHWRender::MShaderInstance* fShaderInstance;

    // キャッシュされたパラメータ
    MColor fDiffuseColor;
    float  fDiffuseAlpha;
    MColor fAmbientColor;
    MColor fSpecularColor;
    float  fSpecularPower;
    MColor fTransparency;
    int    fSphereMode;
    int    fToonMode;
    int    fLightMode;
    int    fShadowMode;
    float  fShadowBias;
    bool   fIsTransparent;
};

#endif // MMD_TOON_OVERRIDE_H
