#include "mmd_material_node.h"
#include "mmd_shader_override.h"

#include <maya/MFnPlugin.h>
#include <maya/MDrawRegistry.h>
#include <maya/MGlobal.h>

static const MString sRegistrantId("mmdMaterialPluginRegistrant");

// プラグイン初期化処理
MStatus initializePlugin(MObject obj)
{
    MFnPlugin plugin(obj, "MMD Tools for Maya", "1.0.0", "Any");
    MStatus status;

    // MMDマテリアルノードの登録
    status = plugin.registerNode(
        "mmdMaterial",
        MMDMaterialNode::id,
        MMDMaterialNode::creator,
        MMDMaterialNode::initialize,
        MPxNode::kDependNode,
        &MMDMaterialNode::classification
    );
    if (!status)
    {
        status.perror("Failed to register mmdMaterial node");
        return status;
    }

    // Viewport 2.0 サーフェスシェーダーオーバーライドの登録
    status = MHWRender::MDrawRegistry::registerSurfaceShadingNodeOverrideCreator(
        MMDMaterialNode::classification,
        sRegistrantId,
        MMDShaderOverride::Creator
    );
    if (!status)
    {
        status.perror("Failed to register MMDShaderOverride");
        return status;
    }

    // Hypershade のノード作成ツリー (MmdMat > Material) 登録コールバックの自動実行
    static const char* sRegisterCallbacksMel =
        "global proc string mmdMaterial_RenderNodeClassificationCallback() {\n"
        "    return \"rendernode/MmdMat\";\n"
        "}\n"
        "global proc string mmdMaterial_HyperShadePanelBuildCreateSubMenuCallback() {\n"
        "    return \"rendernode/MmdMat\";\n"
        "}\n"
        "global proc int mmdMaterial_HyperShadePanelPluginChangeCallback(string $classification, string $changeType) {\n"
        "    return startsWith($classification, \"rendernode/MmdMat\") ? 1 : 0;\n"
        "}\n"
        "global proc int mmdMaterial_CreateRenderNodePluginChangeCallback(string $classification) {\n"
        "    return startsWith($classification, \"rendernode/MmdMat\") ? 1 : 0;\n"
        "}\n"
        "global proc mmdMaterial_BuildRenderNodeTreeListerContentCallback(string $renderNodeTreeLister, string $postCommand, string $filterString) {\n"
        "    string $filterClassArray[] = stringToStringArray($filterString, \" \");\n"
        "    if (size($filterClassArray) == 0) {\n"
        "        addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdMat/Material\", \"rendernode/MmdMat/Material\", \"-asShader\", \"surfaceShader\");\n"
        "    } else {\n"
        "        for ($filterClass in $filterClassArray) {\n"
        "            if (startsWith($filterClass, \"rendernode/MmdMat\") || startsWith(\"rendernode/MmdMat\", $filterClass) || $filterClass == \"shader/surface\") {\n"
        "                addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdMat/Material\", \"rendernode/MmdMat/Material\", \"-asShader\", \"surfaceShader\");\n"
        "                break;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
        "global proc mmdMaterial_RegisterCallbacks() {\n"
        "    mmdMaterial_UnregisterCallbacks();\n"
        "    callbacks -hook \"renderNodeClassification\" -addCallback \"mmdMaterial_RenderNodeClassificationCallback\" -owner \"MmdMaterial\";\n"
        "    callbacks -hook \"buildRenderNodeTreeListerContent\" -addCallback \"mmdMaterial_BuildRenderNodeTreeListerContentCallback\" -owner \"MmdMaterial\";\n"
        "    callbacks -hook \"hyperShadePanelBuildCreateSubMenu\" -addCallback \"mmdMaterial_HyperShadePanelBuildCreateSubMenuCallback\" -owner \"MmdMaterial\";\n"
        "    callbacks -hook \"hyperShadePanelPluginChange\" -addCallback \"mmdMaterial_HyperShadePanelPluginChangeCallback\" -owner \"MmdMaterial\";\n"
        "    callbacks -hook \"createRenderNodePluginChange\" -addCallback \"mmdMaterial_CreateRenderNodePluginChangeCallback\" -owner \"MmdMaterial\";\n"
        "}\n"
        "global proc mmdMaterial_UnregisterCallbacks() {\n"
        "    catchQuiet(`callbacks -hook \"renderNodeClassification\" -removeCallback \"mmdMaterial_RenderNodeClassificationCallback\" -owner \"MmdMaterial\"`);\n"
        "    catchQuiet(`callbacks -hook \"buildRenderNodeTreeListerContent\" -removeCallback \"mmdMaterial_BuildRenderNodeTreeListerContentCallback\" -owner \"MmdMaterial\"`);\n"
        "    catchQuiet(`callbacks -hook \"hyperShadePanelBuildCreateSubMenu\" -removeCallback \"mmdMaterial_HyperShadePanelBuildCreateSubMenuCallback\" -owner \"MmdMaterial\"`);\n"
        "    catchQuiet(`callbacks -hook \"hyperShadePanelPluginChange\" -removeCallback \"mmdMaterial_HyperShadePanelPluginChangeCallback\" -owner \"MmdMaterial\"`);\n"
        "    catchQuiet(`callbacks -hook \"createRenderNodePluginChange\" -removeCallback \"mmdMaterial_CreateRenderNodePluginChangeCallback\" -owner \"MmdMaterial\"`);\n"
        "}\n"
        "global proc AEmmdMaterialTemplate(string $nodeName) {\n"
        "    editorTemplate -beginScrollLayout;\n"
        "    editorTemplate -beginLayout \"MMD Basic Color\" -collapse 0;\n"
        "        editorTemplate -addControl \"color\";\n"
        "        editorTemplate -addControl \"transparency\";\n"
        "        editorTemplate -addControl \"diffuse\";\n"
        "        editorTemplate -addControl \"ambientColor\";\n"
        "        editorTemplate -addSeparator;\n"
        "        editorTemplate -addControl \"diffuseColor\";\n"
        "        editorTemplate -addControl \"diffuseAlpha\";\n"
        "    editorTemplate -endLayout;\n"
        "    editorTemplate -beginLayout \"MMD Specular\" -collapse 0;\n"
        "        editorTemplate -addControl \"specularColor\";\n"
        "        editorTemplate -addControl \"specularPower\";\n"
        "        editorTemplate -addControl \"cosinePower\";\n"
        "        editorTemplate -addControl \"incandescence\";\n"
        "    editorTemplate -endLayout;\n"
        "    editorTemplate -beginLayout \"MMD Sphere and Toon\" -collapse 0;\n"
        "        editorTemplate -addControl \"sphereMode\";\n"
        "        editorTemplate -addControl \"toonMode\";\n"
        "    editorTemplate -endLayout;\n"
        "    editorTemplate -beginLayout \"MMD Edge Outline\" -collapse 0;\n"
        "        editorTemplate -addControl \"edgeEnable\";\n"
        "        editorTemplate -addControl \"edgeColor\";\n"
        "        editorTemplate -addControl \"edgeSize\";\n"
        "    editorTemplate -endLayout;\n"
        "    AEdependNodeTemplate $nodeName;\n"
        "    editorTemplate -addExtraControls;\n"
        "    editorTemplate -endScrollLayout;\n"
        "}\n"
        "mmdMaterial_RegisterCallbacks();\n";


    MGlobal::executeCommand(sRegisterCallbacksMel);


    MGlobal::displayInfo("MMD Material Plugin loaded successfully with Hypershade callbacks.");
    return MS::kSuccess;
}

// プラグイン解放処理
MStatus uninitializePlugin(MObject obj)
{
    MFnPlugin plugin(obj);
    MStatus status;

    // Hypershade コールバックの登録解除
    MGlobal::executeCommand("catchQuiet(eval(\"mmdMaterial_UnregisterCallbacks();\"));");

    // Viewport 2.0 サーフェスシェーダーオーバーライドの登録解除
    status = MHWRender::MDrawRegistry::deregisterSurfaceShadingNodeOverrideCreator(
        MMDMaterialNode::classification,
        sRegistrantId
    );
    if (!status)
    {
        status.perror("Failed to deregister MMDShaderOverride");
    }

    // MMDマテリアルノードの登録解除
    status = plugin.deregisterNode(MMDMaterialNode::id);
    if (!status)
    {
        status.perror("Failed to deregister mmdMaterial node");
    }

    MGlobal::displayInfo("MMD Material Plugin unloaded.");
    return status;
}

