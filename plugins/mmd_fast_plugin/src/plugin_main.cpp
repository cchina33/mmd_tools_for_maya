#include "mmd_fast_baker_cmd.h"
#include "mmd_fast_pmx_cmd.h"
#include "mmd_fast_vmd_cmd.h"
#include "pmx_binary_parser.h"
#include "vmd_binary_parser.h"

#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MStatus.h>

MStatus initializePlugin(MObject obj)
{
    MStatus status;
    MFnPlugin plugin(obj, "MMD Tools for Maya", "2.0.0", "Any");

    status = plugin.registerCommand(MMDFastBakeBoneCmd::kName, MMDFastBakeBoneCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastBakeBone failed. 旧 mmd_motion がロードされている可能性があります: ") + status.errorString());
        return status;
    }

    status = plugin.registerCommand(MmdFastImportPmxMeshCmd::commandName(), MmdFastImportPmxMeshCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastImportPmxMesh failed: ") + status.errorString());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    status = plugin.registerCommand(MmdFastApplyPmxBlendShapesCmd::commandName(), MmdFastApplyPmxBlendShapesCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastApplyPmxBlendShapes failed: ") + status.errorString());
        plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    status = plugin.registerCommand(MmdFastApplyPmxSkinWeightsCmd::commandName(), MmdFastApplyPmxSkinWeightsCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastApplyPmxSkinWeights failed: ") + status.errorString());
        plugin.deregisterCommand(MmdFastApplyPmxBlendShapesCmd::commandName());
        plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    status = plugin.registerCommand(MmdFastImportVmdBoneCmd::commandName(), MmdFastImportVmdBoneCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastImportVmdBone failed: ") + status.errorString());
        plugin.deregisterCommand(MmdFastApplyPmxSkinWeightsCmd::commandName());
        plugin.deregisterCommand(MmdFastApplyPmxBlendShapesCmd::commandName());
        plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    status = plugin.registerCommand(MmdFastImportVmdMorphCmd::commandName(), MmdFastImportVmdMorphCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastImportVmdMorph failed: ") + status.errorString());
        plugin.deregisterCommand(MmdFastImportVmdBoneCmd::commandName());
        plugin.deregisterCommand(MmdFastApplyPmxSkinWeightsCmd::commandName());
        plugin.deregisterCommand(MmdFastApplyPmxBlendShapesCmd::commandName());
        plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    status = plugin.registerCommand(MmdFastImportVmdCameraCmd::commandName(), MmdFastImportVmdCameraCmd::creator);
    if (!status)
    {
        MGlobal::displayError(MString("[mmd_fast] registerCommand mmdFastImportVmdCamera failed: ") + status.errorString());
        plugin.deregisterCommand(MmdFastImportVmdMorphCmd::commandName());
        plugin.deregisterCommand(MmdFastImportVmdBoneCmd::commandName());
        plugin.deregisterCommand(MmdFastApplyPmxSkinWeightsCmd::commandName());
        plugin.deregisterCommand(MmdFastApplyPmxBlendShapesCmd::commandName());
        plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
        plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);
        return status;
    }

    MGlobal::displayInfo("[MMD Fast Plugin] Loaded mmd_fast.mll (Native C++ PMX/VMD/Bake Acceleration).");
    return MS::kSuccess;
}

MStatus uninitializePlugin(MObject obj)
{
    MStatus status;
    MFnPlugin plugin(obj);

    mmd_fast::PmxBinaryCache::clearCache();
    mmd_fast::VmdBinaryCache::clearCache();

    plugin.deregisterCommand(MmdFastImportVmdCameraCmd::commandName());
    plugin.deregisterCommand(MmdFastImportVmdMorphCmd::commandName());
    plugin.deregisterCommand(MmdFastImportVmdBoneCmd::commandName());
    plugin.deregisterCommand(MmdFastApplyPmxSkinWeightsCmd::commandName());
    plugin.deregisterCommand(MmdFastApplyPmxBlendShapesCmd::commandName());
    plugin.deregisterCommand(MmdFastImportPmxMeshCmd::commandName());
    status = plugin.deregisterCommand(MMDFastBakeBoneCmd::kName);

    return status;
}
