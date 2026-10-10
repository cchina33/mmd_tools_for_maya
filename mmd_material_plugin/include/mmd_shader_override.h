#ifndef MMD_SHADER_OVERRIDE_H
#define MMD_SHADER_OVERRIDE_H

#include <maya/MPxSurfaceShadingNodeOverride.h>
#include <maya/MObject.h>
#include <maya/MString.h>

// Viewport 2.0 描画用サーフェスシェーダーオーバーライドクラス
class MMDShaderOverride : public MHWRender::MPxSurfaceShadingNodeOverride
{
public:
    static MHWRender::MPxSurfaceShadingNodeOverride* Creator(const MObject& obj);

    MMDShaderOverride(const MObject& obj);
    ~MMDShaderOverride() override;

    MHWRender::DrawAPI supportedDrawAPIs() const override;

    MString fragmentName() const override;
    void getCustomMappings(MHWRender::MAttributeParameterMappingList& mappings) override;

    MString primaryColorParameter() const override;
    MString transparencyParameter() const override;
    MString bumpAttribute() const override;

private:
    MObject fObject;
};

#endif // MMD_SHADER_OVERRIDE_H
