#include "mmd_shader_override.h"

MHWRender::MPxSurfaceShadingNodeOverride* MMDShaderOverride::Creator(const MObject& obj)
{
    return new MMDShaderOverride(obj);
}

MMDShaderOverride::MMDShaderOverride(const MObject& obj)
    : MHWRender::MPxSurfaceShadingNodeOverride(obj)
    , fObject(obj)
{
}

MMDShaderOverride::~MMDShaderOverride()
{
}

MHWRender::DrawAPI MMDShaderOverride::supportedDrawAPIs() const
{
    // DirectX 11 および OpenGL の両方に対応
    return MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile;
}

MString MMDShaderOverride::fragmentName() const
{
    // MMDのシェーディング特性（Phong/Blinn-Phong反射）に適合するサーフェスフラグメントを使用
    return "mayaPhongSurface";
}

void MMDShaderOverride::getCustomMappings(MHWRender::MAttributeParameterMappingList& mappings)
{
    // カラー属性のマッピング
    MHWRender::MAttributeParameterMapping diffuseMapping("diffuse", "diffuseReflectivity", true, true);
    mappings.append(diffuseMapping);

    MHWRender::MAttributeParameterMapping powerMapping("cosinePower", "power", true, true);
    mappings.append(powerMapping);
}

MString MMDShaderOverride::primaryColorParameter() const
{
    // プライマリカラー属性
    return "color";
}

MString MMDShaderOverride::transparencyParameter() const
{
    // 透過度属性
    return "transparency";
}

MString MMDShaderOverride::bumpAttribute() const
{
    // 法線属性
    return "normalCamera";
}
