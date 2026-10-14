#ifndef MMD_FAST_BAKER_CMD_H
#define MMD_FAST_BAKER_CMD_H

#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MStatus.h>

// MMD物理ベイク超高速キーフレーム書き込みコマンド
// cmds.mmdFastBakeBone(bone_name, frames, tx, ty, tz, rx, ry, rz)
class MMDFastBakeBoneCmd : public MPxCommand
{
public:
    MMDFastBakeBoneCmd();
    virtual ~MMDFastBakeBoneCmd();

    virtual MStatus doIt(const MArgList& args) override;

    static void* creator();
    static const char* kName;
};

#endif // MMD_FAST_BAKER_CMD_H
