#ifndef MMD_FAST_PMX_CMD_H
#define MMD_FAST_PMX_CMD_H

#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MStatus.h>

// PMXモデルメッシュ一括生成コマンド (mmdFastImportPmxMesh)
// 引数: (pmx_file_path, mesh_node_name, scale)
// 戻り値: MStringArray [生成されたメッシュノード名, 材質0の有効面数, 材質1の有効面数, ...]
class MmdFastImportPmxMeshCmd : public MPxCommand
{
public:
    MmdFastImportPmxMeshCmd() = default;
    ~MmdFastImportPmxMeshCmd() override = default;

    static void* creator() { return new MmdFastImportPmxMeshCmd(); }
    static const char* commandName() { return "mmdFastImportPmxMesh"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// PMXブレンドシェイプ（頂点モーフ）一括注入コマンド (mmdFastApplyPmxBlendShapes)
// 引数: (pmx_file_path, blendshape_node_name, scale)
// 戻り値: 登録された頂点モーフ数 (int)
class MmdFastApplyPmxBlendShapesCmd : public MPxCommand
{
public:
    MmdFastApplyPmxBlendShapesCmd() = default;
    ~MmdFastApplyPmxBlendShapesCmd() override = default;

    static void* creator() { return new MmdFastApplyPmxBlendShapesCmd(); }
    static const char* commandName() { return "mmdFastApplyPmxBlendShapes"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// PMXスキニングウェイト一括適用コマンド (mmdFastApplyPmxSkinWeights)
// 引数: (pmx_file_path, mesh_node_name, skin_cluster_name)
// 戻り値: 適用成否 (int: 1=成功, 0=失敗)
class MmdFastApplyPmxSkinWeightsCmd : public MPxCommand
{
public:
    MmdFastApplyPmxSkinWeightsCmd() = default;
    ~MmdFastApplyPmxSkinWeightsCmd() override = default;

    static void* creator() { return new MmdFastApplyPmxSkinWeightsCmd(); }
    static const char* commandName() { return "mmdFastApplyPmxSkinWeights"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

#endif // MMD_FAST_PMX_CMD_H

