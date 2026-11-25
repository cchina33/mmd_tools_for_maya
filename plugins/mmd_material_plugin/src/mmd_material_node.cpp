#include "mmd_material_node.h"

#include <maya/MFnNumericAttribute.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFnEnumAttribute.h>
#include <maya/MFnStringData.h>
#include <maya/MPlug.h>
#include <maya/MDataBlock.h>
#include <maya/MDataHandle.h>
#include <maya/MFloatVector.h>

// プラグイン固有ノードID（ユーザー領域ID）
const MTypeId MMDMaterialNode::id(0x0013B200);

// Viewport 2.0 分類、Hypershade 分類 (MmdMat > Material)、および スウォッチ分類
const MString MMDMaterialNode::classification("rendernode/MmdMat/Material:shader/surface:swatch/mayaShader:drawdb/shader/surface/mmdMaterial");



// アトリビュート定義
MObject MMDMaterialNode::aColor;
MObject MMDMaterialNode::aTransparency;
MObject MMDMaterialNode::aAmbientColor;
MObject MMDMaterialNode::aIncandescence;
MObject MMDMaterialNode::aSpecularColor;
MObject MMDMaterialNode::aDiffuse;
MObject MMDMaterialNode::aCosinePower;
MObject MMDMaterialNode::aNormalCamera;

MObject MMDMaterialNode::aDiffuseColor;
MObject MMDMaterialNode::aDiffuseAlpha;
MObject MMDMaterialNode::aSpecularPower;
MObject MMDMaterialNode::aSphereMode;
MObject MMDMaterialNode::aToonMode;

MObject MMDMaterialNode::aEdgeEnable;
MObject MMDMaterialNode::aEdgeColor;
MObject MMDMaterialNode::aEdgeSize;

MObject MMDMaterialNode::aOutColor;
MObject MMDMaterialNode::aOutTransparency;

MMDMaterialNode::MMDMaterialNode()
{
}

MMDMaterialNode::~MMDMaterialNode()
{
}

void* MMDMaterialNode::creator()
{
    return new MMDMaterialNode();
}

MStatus MMDMaterialNode::initialize()
{
    MFnNumericAttribute nAttr;
    MFnEnumAttribute eAttr;
    MStatus status;

    // 基本カラー (Color / Diffuse Texture接続用)
    aColor = nAttr.createColor("color", "c", &status);
    nAttr.setDefault(1.0f, 1.0f, 1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aColor);

    // 透過度 (Transparency)
    aTransparency = nAttr.createColor("transparency", "it", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aTransparency);

    // 環境光色 (Ambient)
    aAmbientColor = nAttr.createColor("ambientColor", "ac", &status);
    nAttr.setDefault(0.5f, 0.5f, 0.5f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aAmbientColor);

    // 発光 / 加算スフィア接続用 (Incandescence)
    aIncandescence = nAttr.createColor("incandescence", "ic", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aIncandescence);

    // 反射色 (Specular)
    aSpecularColor = nAttr.createColor("specularColor", "sc", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aSpecularColor);

    // 拡散反射係数 (Diffuse)
    aDiffuse = nAttr.create("diffuse", "dc", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aDiffuse);

    // 光沢度 (Cosine Power)
    aCosinePower = nAttr.create("cosinePower", "cp", MFnNumericData::kFloat, 5.0f, &status);
    nAttr.setMin(2.0f);
    nAttr.setMax(100.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aCosinePower);

    // カメラ法線 (Normal Camera)
    aNormalCamera = nAttr.createPoint("normalCamera", "n", &status);
    nAttr.setKeyable(false);
    nAttr.setStorable(false);
    nAttr.setHidden(true);
    addAttribute(aNormalCamera);

    // 後方互換性用 MMD 属性 (diffuseColor, diffuseAlpha, specularPower)
    aDiffuseColor = nAttr.createColor("diffuseColor", "dfc", &status);
    nAttr.setDefault(1.0f, 1.0f, 1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aDiffuseColor);

    aDiffuseAlpha = nAttr.create("diffuseAlpha", "da", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aDiffuseAlpha);

    aSpecularPower = nAttr.create("specularPower", "sp", MFnNumericData::kFloat, 5.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setSoftMax(100.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aSpecularPower);

    // スフィアマップモード
    aSphereMode = eAttr.create("sphereMode", "sm", 0, &status);
    eAttr.addField("None", 0);
    eAttr.addField("Multiply (.sph)", 1);
    eAttr.addField("Add (.spa)", 2);
    eAttr.addField("Subtract", 3);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aSphereMode);

    // Toonモード
    aToonMode = eAttr.create("toonMode", "tm", 1, &status);
    eAttr.addField("Disabled", 0);
    eAttr.addField("Standard MMD", 1);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aToonMode);

    // エッジ設定
    aEdgeEnable = nAttr.create("edgeEnable", "ee", MFnNumericData::kBoolean, true, &status);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aEdgeEnable);

    aEdgeColor = nAttr.createColor("edgeColor", "ec", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aEdgeColor);

    aEdgeSize = nAttr.create("edgeSize", "es", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aEdgeSize);

    // 出力カラー
    aOutColor = nAttr.createColor("outColor", "oc", &status);
    nAttr.setKeyable(false);
    nAttr.setStorable(false);
    nAttr.setReadable(true);
    nAttr.setWritable(false);
    addAttribute(aOutColor);

    // 出力透過度
    aOutTransparency = nAttr.createColor("outTransparency", "ot", &status);
    nAttr.setKeyable(false);
    nAttr.setStorable(false);
    nAttr.setReadable(true);
    nAttr.setWritable(false);
    addAttribute(aOutTransparency);

    // 属性依存関係
    attributeAffects(aColor, aOutColor);
    attributeAffects(aDiffuseColor, aOutColor);
    attributeAffects(aAmbientColor, aOutColor);
    attributeAffects(aIncandescence, aOutColor);
    attributeAffects(aTransparency, aOutTransparency);

    return MS::kSuccess;
}

MStatus MMDMaterialNode::compute(const MPlug& plug, MDataBlock& block)
{
    // 出力カラー計算
    if (plug == aOutColor || plug.parent() == aOutColor)
    {
        MDataHandle colorHandle = block.inputValue(aColor);
        MFloatVector col = colorHandle.asFloatVector();

        MDataHandle incHandle = block.inputValue(aIncandescence);
        MFloatVector inc = incHandle.asFloatVector();

        MFloatVector finalColor = col + inc;

        MDataHandle outColorHandle = block.outputValue(aOutColor);
        outColorHandle.setMFloatVector(finalColor);
        block.setClean(plug);
        return MS::kSuccess;
    }
    // 出力透過度計算
    else if (plug == aOutTransparency || plug.parent() == aOutTransparency)
    {
        MDataHandle transHandle = block.inputValue(aTransparency);
        MFloatVector trans = transHandle.asFloatVector();

        MDataHandle outTransHandle = block.outputValue(aOutTransparency);
        outTransHandle.setMFloatVector(trans);
        block.setClean(plug);
        return MS::kSuccess;
    }

    return MS::kUnknownParameter;
}
