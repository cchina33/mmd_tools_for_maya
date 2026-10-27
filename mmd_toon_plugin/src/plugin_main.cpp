#include "mmd_toon_node.h"
#include "mmd_toon_override.h"

#include <maya/MFnPlugin.h>
#include <maya/MDrawRegistry.h>
#include <maya/MGlobal.h>

static const MString sRegistrantId("mmdToonShaderPluginRegistrant");

// プラグイン初期化処理
MStatus initializePlugin(MObject obj)
{
    MFnPlugin plugin(obj, "MMD Tools for Maya", "1.0.0", "Any");
    MStatus status;

    // MMDトゥーンシェーダーノードの登録
    status = plugin.registerNode(
        "mmdToonShader",
        MMDToonNode::id,
        MMDToonNode::creator,
        MMDToonNode::initialize,
        MPxNode::kDependNode,
        &MMDToonNode::classification
    );
    if (!status)
    {
        status.perror("Failed to register mmdToonShader node");
        return status;
    }

    // Viewport 2.0 シェーダーオーバーライドの登録
    status = MHWRender::MDrawRegistry::registerShaderOverrideCreator(
        MMDToonNode::classification,
        sRegistrantId,
        MMDToonOverride::Creator
    );
    if (!status)
    {
        status.perror("Failed to register MMDToonOverride");
        return status;
    }

    // Hypershade のノード作成ツリー (MmdToon > Material) 登録コールバック
    static const char* sRegisterCallbacksMel =
        "global proc string mmdToonShader_RenderNodeClassificationCallback() {\n"
        "    return \"rendernode/MmdToon\";\n"
        "}\n"
        "global proc string mmdToonShader_HyperShadePanelBuildCreateSubMenuCallback() {\n"
        "    return \"rendernode/MmdToon\";\n"
        "}\n"
        "global proc int mmdToonShader_HyperShadePanelPluginChangeCallback(string $classification, string $changeType) {\n"
        "    return startsWith($classification, \"rendernode/MmdToon\") ? 1 : 0;\n"
        "}\n"
        "global proc int mmdToonShader_CreateRenderNodePluginChangeCallback(string $classification) {\n"
        "    return startsWith($classification, \"rendernode/MmdToon\") ? 1 : 0;\n"
        "}\n"
        "global proc mmdToonShader_BuildRenderNodeTreeListerContentCallback(string $renderNodeTreeLister, string $postCommand, string $filterString) {\n"
        "    string $filterClassArray[] = stringToStringArray($filterString, \" \");\n"
        "    if (size($filterClassArray) == 0) {\n"
        "        addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdToon/Material\", \"rendernode/MmdToon/Material\", \"-asShader\", \"surfaceShader\");\n"
        "    } else {\n"
        "        for ($filterClass in $filterClassArray) {\n"
        "            if (startsWith(\"rendernode/MmdToon/Material\", $filterClass)) {\n"
        "                addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdToon/Material\", \"rendernode/MmdToon/Material\", \"-asShader\", \"surfaceShader\");\n"
        "                break;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n";

    MGlobal::executeCommand(sRegisterCallbacksMel);

    return MS::kSuccess;
}

// プラグイン登録解除処理
MStatus uninitializePlugin(MObject obj)
{
    MFnPlugin plugin(obj);
    MStatus status;

    // Viewport 2.0 シェーダーオーバーライドの解除
    status = MHWRender::MDrawRegistry::deregisterShaderOverrideCreator(
        MMDToonNode::classification,
        sRegistrantId
    );
    if (!status)
    {
        status.perror("Failed to deregister MMDToonOverride");
    }

    // ノードの登録解除
    status = plugin.deregisterNode(MMDToonNode::id);
    if (!status)
    {
        status.perror("Failed to deregister mmdToonShader node");
    }

    return status;
}
