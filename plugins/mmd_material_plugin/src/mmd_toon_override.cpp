#include "mmd_toon_override.h"

MHWRender::MPxSurfaceShadingNodeOverride* MMDToonOverride::Creator(const MObject& obj)
{
    return new MMDToonOverride(obj);
}

MMDToonOverride::MMDToonOverride(const MObject& obj)
    : MHWRender::MPxSurfaceShadingNodeOverride(obj)
    , fObject(obj)
{
}

MMDToonOverride::~MMDToonOverride()
{
}

MHWRender::DrawAPI MMDToonOverride::supportedDrawAPIs() const
{
    // OpenGL Core Profile、DirectX 11、およびOpenGL Legacyに対応
    return MHWRender::kOpenGL | MHWRender::kDirectX11 | MHWRender::kOpenGLCoreProfile;
}

MString MMDToonOverride::fragmentName() const
{
    // 上流のToon・スフィアDGノードグラフとViewport 2.0デプスマップシャドウを統合評価するサーフェスフラグメントを使用
    return "mayaPhongSurface";
}

void MMDToonOverride::getCustomMappings(MHWRender::MAttributeParameterMappingList& mappings)
{
    // 受光率とスペキュラ光沢度のマッピング
    MHWRender::MAttributeParameterMapping diffuseMapping("diffuse", "diffuseReflectivity", true, true);
    mappings.append(diffuseMapping);

    MHWRender::MAttributeParameterMapping powerMapping("cosinePower", "power", true, true);
    mappings.append(powerMapping);

    // 輪郭線（エッジ）属性のマッピング
    MHWRender::MAttributeParameterMapping edgeEnableMapping("edgeEnable", "edgeEnable", true, true);
    mappings.append(edgeEnableMapping);

    MHWRender::MAttributeParameterMapping edgeColorMapping("edgeColor", "edgeColor", true, true);
    mappings.append(edgeColorMapping);

    MHWRender::MAttributeParameterMapping edgeSizeMapping("edgeSize", "edgeSize", true, true);
    mappings.append(edgeSizeMapping);
}

MString MMDToonOverride::primaryColorParameter() const
{
    // プライマリカラー属性
    return "color";
}

MString MMDToonOverride::transparencyParameter() const
{
    // 透過度属性
    return "transparency";
}

MString MMDToonOverride::bumpAttribute() const
{
    // 法線属性
    return "normalCamera";
}
