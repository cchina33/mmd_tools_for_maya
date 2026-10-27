#include "mmd_toon_node.h"

#include <maya/MFnNumericAttribute.h>
#include <maya/MFnEnumAttribute.h>
#include <maya/MFnTypedAttribute.h>
#include <maya/MFloatVector.h>
#include <maya/MDataHandle.h>

// ノード識別子定義
const MTypeId MMDToonNode::id(0x0013B280);
const MString MMDToonNode::classification("rendernode/MmdToon/Material:shader/surface:drawdb/shader/surface/mmdToonShader");

// 静的アトリビュート定義の実体
MObject MMDToonNode::aColor;
MObject MMDToonNode::aDiffuseColor;
MObject MMDToonNode::aDiffuseAlpha;
MObject MMDToonNode::aTransparency;
MObject MMDToonNode::aDiffuse;
MObject MMDToonNode::aAmbientColor;
MObject MMDToonNode::aIncandescence;
MObject MMDToonNode::aSpecularColor;
MObject MMDToonNode::aSpecularPower;
MObject MMDToonNode::aCosinePower;
MObject MMDToonNode::aSphereMode;
MObject MMDToonNode::aToonMode;
MObject MMDToonNode::aLightMode;
MObject MMDToonNode::aShadowMode;
MObject MMDToonNode::aShadowBias;
MObject MMDToonNode::aEdgeEnable;
MObject MMDToonNode::aEdgeColor;
MObject MMDToonNode::aEdgeSize;
MObject MMDToonNode::aColorTexture;
MObject MMDToonNode::aSphereTexture;
MObject MMDToonNode::aToonTexture;
MObject MMDToonNode::aNormalCamera;
MObject MMDToonNode::aOutColor;
MObject MMDToonNode::aOutTransparency;

MMDToonNode::MMDToonNode()
{
}

MMDToonNode::~MMDToonNode()
{
}

void* MMDToonNode::creator()
{
    return new MMDToonNode();
}

MStatus MMDToonNode::initialize()
{
    MFnNumericAttribute nAttr;
    MFnEnumAttribute eAttr;
    MStatus status;

    // 基本カラー
    aColor = nAttr.createColor("color", "c", &status);
    nAttr.setDefault(0.8f, 0.8f, 0.8f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aColor);

    // ディフューズカラー（MMD材質パラメータ同期用）
    aDiffuseColor = nAttr.createColor("diffuseColor", "dc", &status);
    nAttr.setDefault(0.8f, 0.8f, 0.8f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aDiffuseColor);

    // ディフューズアルファ
    aDiffuseAlpha = nAttr.create("diffuseAlpha", "da", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aDiffuseAlpha);

    // 透過度
    aTransparency = nAttr.createColor("transparency", "it", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aTransparency);

    // ディフューズ受光率
    aDiffuse = nAttr.create("diffuse", "diff", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(1.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aDiffuse);

    // アンビエントカラー（MMD本家では環境反射係数、自己発光防止のため初期値0）
    aAmbientColor = nAttr.createColor("ambientColor", "ambc", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aAmbientColor);

    // 自己発光カラー（加算スフィア等）
    aIncandescence = nAttr.createColor("incandescence", "inc", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aIncandescence);

    // スペキュラカラー
    aSpecularColor = nAttr.createColor("specularColor", "sc", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aSpecularColor);

    // スペキュラパワー（光沢度）
    aSpecularPower = nAttr.create("specularPower", "sp", MFnNumericData::kFloat, 5.0f, &status);
    nAttr.setMin(1.0f);
    nAttr.setMax(100.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aSpecularPower);

    // Cosine Power (Phong互換)
    aCosinePower = nAttr.create("cosinePower", "cp", MFnNumericData::kFloat, 10.0f, &status);
    nAttr.setMin(2.0f);
    nAttr.setMax(100.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aCosinePower);

    // スフィアモード (0: なし, 1: 乗算, 2: 加算)
    aSphereMode = eAttr.create("sphereMode", "sm", 0, &status);
    eAttr.addField("None", 0);
    eAttr.addField("Multiply", 1);
    eAttr.addField("Add", 2);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aSphereMode);

    // トゥーンモード (0: 無効, 1: MMD標準サンプリング)
    aToonMode = eAttr.create("toonMode", "tm", 1, &status);
    eAttr.addField("Disabled", 0);
    eAttr.addField("MMD Toon", 1);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aToonMode);

    // ライトモード (0: Mayaライト直接, 1: MMD標準輝度 0.604 換算)
    aLightMode = eAttr.create("lightMode", "lm", 1, &status);
    eAttr.addField("Maya Light", 0);
    eAttr.addField("MMD Reference", 1);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aLightMode);

    // シャドウモード (0: 無効, 1: MMD深度差判定, 2: 4点PCF)
    aShadowMode = eAttr.create("shadowMode", "shdm", 1, &status);
    eAttr.addField("Disabled", 0);
    eAttr.addField("MMD Depth", 1);
    eAttr.addField("PCF", 2);
    eAttr.setKeyable(true);
    eAttr.setStorable(true);
    addAttribute(aShadowMode);

    // シャドウバイアス
    aShadowBias = nAttr.create("shadowBias", "shdb", MFnNumericData::kFloat, 0.001f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(0.1f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aShadowBias);

    // エッジ（輪郭線）有効フラグ
    aEdgeEnable = nAttr.create("edgeEnable", "ee", MFnNumericData::kBoolean, true, &status);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aEdgeEnable);

    // エッジカラー
    aEdgeColor = nAttr.createColor("edgeColor", "ec", &status);
    nAttr.setDefault(0.0f, 0.0f, 0.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aEdgeColor);

    // エッジサイズ
    aEdgeSize = nAttr.create("edgeSize", "es", MFnNumericData::kFloat, 1.0f, &status);
    nAttr.setMin(0.0f);
    nAttr.setMax(10.0f);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    addAttribute(aEdgeSize);

    // テクスチャ接続用スロット
    aColorTexture = nAttr.createColor("colorTexture", "ctex", &status);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aColorTexture);

    aSphereTexture = nAttr.createColor("sphereTexture", "stex", &status);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aSphereTexture);

    aToonTexture = nAttr.createColor("toonTexture", "ttex", &status);
    nAttr.setKeyable(true);
    nAttr.setStorable(true);
    nAttr.setUsedAsColor(true);
    addAttribute(aToonTexture);

    // 法線入力
    aNormalCamera = nAttr.createPoint("normalCamera", "n", &status);
    nAttr.setKeyable(false);
    nAttr.setStorable(false);
    nAttr.setHidden(true);
    addAttribute(aNormalCamera);

    // 出力カラー
    aOutColor = nAttr.createColor("outColor", "oc", &status);
    nAttr.setWritable(false);
    nAttr.setStorable(false);
    addAttribute(aOutColor);

    // 出力透過度
    aOutTransparency = nAttr.createColor("outTransparency", "ot", &status);
    nAttr.setWritable(false);
    nAttr.setStorable(false);
    addAttribute(aOutTransparency);

    // 属性の関連付け（依存関係）
    attributeAffects(aColor, aOutColor);
    attributeAffects(aDiffuseColor, aOutColor);
    attributeAffects(aColorTexture, aOutColor);
    attributeAffects(aTransparency, aOutTransparency);
    attributeAffects(aDiffuseAlpha, aOutTransparency);

    return MS::kSuccess;
}

MStatus MMDToonNode::compute(const MPlug& plug, MDataBlock& block)
{
    if (plug == aOutColor || plug.parent() == aOutColor)
    {
        MDataHandle colorHandle = block.inputValue(aColor);
        MFloatVector colorVal = colorHandle.asFloatVector();

        MDataHandle outColorHandle = block.outputValue(aOutColor);
        outColorHandle.setMFloatVector(colorVal);
        outColorHandle.setClean();
        return MS::kSuccess;
    }
    else if (plug == aOutTransparency || plug.parent() == aOutTransparency)
    {
        MDataHandle transHandle = block.inputValue(aTransparency);
        MFloatVector transVal = transHandle.asFloatVector();

        MDataHandle outTransHandle = block.outputValue(aOutTransparency);
        outTransHandle.setMFloatVector(transVal);
        outTransHandle.setClean();
        return MS::kSuccess;
    }

    return MS::kUnknownParameter;
}
