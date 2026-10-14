#include <maya/MFnPlugin.h>
#include <maya/MStatus.h>
#include <maya/MGlobal.h>

#include "mmd_fast_baker_cmd.h"

MStatus initializePlugin(MObject obj)
{
    MStatus status;
    MFnPlugin plugin(obj, "MMD Tools for Maya", "1.0", "Any");

    // mmdFastBakeBone コマンドの登録
    status = plugin.registerCommand(
        MMDFastBakeBoneCmd::kName,
        MMDFastBakeBoneCmd::creator
    );
    if (!status)
    {
        status.perror("Failed to register command: mmdFastBakeBone");
        return status;
    }

    MGlobal::displayInfo("MMD Motion Plugin (mmd_motion.mll) loaded successfully.");
    return MS::kSuccess;
}

MStatus uninitializePlugin(MObject obj)
{
    MStatus status;
    MFnPlugin plugin(obj);

    // mmdFastBakeBone コマンドの登録解除
    status = plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
    if (!status)
    {
        status.perror("Failed to deregister command: mmdFastBakeBone");
        return status;
    }

    MGlobal::displayInfo("MMD Motion Plugin (mmd_motion.mll) uninitialized.");
    return MS::kSuccess;
}
