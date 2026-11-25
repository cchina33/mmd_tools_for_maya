#ifndef MMD_FAST_VMD_CMD_H
#define MMD_FAST_VMD_CMD_H

#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MStatus.h>

// VMDボーンモーション一括注入コマンド (mmdFastImportVmdBone)
// 引数: (vmd_file_path, scale, bone_names_array, joint_paths_array, movable_modes_array)
// 戻り値: MIntArray [適用されたボーン数, 書き込まれた総キーフレーム数]
class MmdFastImportVmdBoneCmd : public MPxCommand
{
public:
    MmdFastImportVmdBoneCmd() = default;
    ~MmdFastImportVmdBoneCmd() override = default;

    static void* creator() { return new MmdFastImportVmdBoneCmd(); }
    static const char* commandName() { return "mmdFastImportVmdBone"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// VMDモーフ（表情）モーション一括注入コマンド (mmdFastImportVmdMorph)
// 引数: (vmd_file_path, morph_names_array, target_plugs_array)
// 戻り値: MIntArray [適用されたモーフ数, 書き込まれた総キーフレーム数]
class MmdFastImportVmdMorphCmd : public MPxCommand
{
public:
    MmdFastImportVmdMorphCmd() = default;
    ~MmdFastImportVmdMorphCmd() override = default;

    static void* creator() { return new MmdFastImportVmdMorphCmd(); }
    static const char* commandName() { return "mmdFastImportVmdMorph"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

// VMDカメラモーション高速ベジェサンプリング＆一括注入コマンド (mmdFastImportVmdCamera)
// 引数: (vmd_file_path, scale, aim_locator_node, cam_transform_node, cam_shape_node, aperture_mm)
// 戻り値: 書き込まれた総サンプルフレーム数 (int)
class MmdFastImportVmdCameraCmd : public MPxCommand
{
public:
    MmdFastImportVmdCameraCmd() = default;
    ~MmdFastImportVmdCameraCmd() override = default;

    static void* creator() { return new MmdFastImportVmdCameraCmd(); }
    static const char* commandName() { return "mmdFastImportVmdCamera"; }

    MStatus doIt(const MArgList& args) override;
    bool isUndoable() const override { return false; }
};

#endif // MMD_FAST_VMD_CMD_H

