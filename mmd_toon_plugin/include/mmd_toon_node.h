#ifndef MMD_TOON_NODE_H
#define MMD_TOON_NODE_H

#include <maya/MPxNode.h>
#include <maya/MTypeId.h>
#include <maya/MString.h>
#include <maya/MObject.h>

class MMDToonNode : public MPxNode
{
public:
    MMDToonNode();
    virtual ~MMDToonNode();

    static void* creator();
    static MStatus initialize();

    virtual MStatus compute(const MPlug& plug, MDataBlock& block) override;

    // ノード識別情報
    static const MTypeId id;
    static const MString classification;

    // 基本カラー属性
    static MObject aColor;
    static MObject aDiffuseColor;
    static MObject aDiffuseAlpha;
    static MObject aTransparency;
    static MObject aDiffuse;

    // アンビエントおよび自己発光
    static MObject aAmbientColor;
    static MObject aIncandescence;

    // スペキュラ属性
    static MObject aSpecularColor;
    static MObject aSpecularPower;
    static MObject aCosinePower;

    // トゥーン・スフィア制御属性
    static MObject aSphereMode;
    static MObject aToonMode;
    static MObject aLightMode;
    static MObject aShadowMode;
    static MObject aShadowBias;

    // 輪郭線属性
    static MObject aEdgeEnable;
    static MObject aEdgeColor;
    static MObject aEdgeSize;

    // テクスチャ接続スロット
    static MObject aColorTexture;
    static MObject aSphereTexture;
    static MObject aToonTexture;

    // 法線属性
    static MObject aNormalCamera;

    // 出力属性
    static MObject aOutColor;
    static MObject aOutTransparency;
};

#endif // MMD_TOON_NODE_H
