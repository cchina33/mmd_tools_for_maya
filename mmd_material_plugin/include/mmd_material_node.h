#ifndef MMD_MATERIAL_NODE_H
#define MMD_MATERIAL_NODE_H

#include <maya/MPxNode.h>
#include <maya/MTypeId.h>
#include <maya/MString.h>
#include <maya/MObject.h>

// MMDオリジナルマテリアルノードクラス
class MMDMaterialNode : public MPxNode
{
public:
    MMDMaterialNode();
    ~MMDMaterialNode() override;

    static void* creator();
    static MStatus initialize();

    MStatus compute(const MPlug& plug, MDataBlock& block) override;

    // プラグイン識別ID
    static const MTypeId id;

    // 分類文字列（Viewport 2.0シェーダーオーバーライドとの関連付け）
    static const MString classification;

    // Maya標準サーフェスシェーダーアトリビュート
    static MObject aColor;
    static MObject aTransparency;
    static MObject aAmbientColor;
    static MObject aIncandescence;
    static MObject aSpecularColor;
    static MObject aDiffuse;
    static MObject aCosinePower;
    static MObject aNormalCamera;

    // MMD固有アトリビュート
    static MObject aDiffuseColor;
    static MObject aDiffuseAlpha;
    static MObject aSpecularPower;
    static MObject aSphereMode;
    static MObject aToonMode;

    // エッジ設定アトリビュート
    static MObject aEdgeEnable;
    static MObject aEdgeColor;
    static MObject aEdgeSize;

    // 出力
    static MObject aOutColor;
    static MObject aOutTransparency;
};

#endif // MMD_MATERIAL_NODE_H
