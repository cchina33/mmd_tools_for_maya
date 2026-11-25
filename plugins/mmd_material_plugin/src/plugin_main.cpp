#include "mmd_material_node.h"
#include "mmd_shader_override.h"
#include "mmd_toon_node.h"
#include "mmd_toon_override.h"
#include "mmd_render_override.h"
#include "mmd_render_cmd.h"

#include <maya/MFnPlugin.h>
#include <maya/MDrawRegistry.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MGlobal.h>

static const MString sMaterialRegistrantId("mmdMaterialPluginRegistrant");
static const MString sToonRegistrantId("mmdToonShaderPluginRegistrant");
static MMDRenderOverride* sMMDRenderOverride = nullptr;

// プラグイン初期化処理
MStatus initializePlugin(MObject obj)
{
    MFnPlugin plugin(obj, "MMD Tools for Maya", "1.0.0", "Any");
    MStatus status;

    // 既存互換: mmdMaterial ノードの登録
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

    // 既存互換: mmdMaterial 用 Viewport 2.0 シェーダーオーバーライドの登録
    status = MHWRender::MDrawRegistry::registerSurfaceShadingNodeOverrideCreator(
        MMDMaterialNode::classification,
        sMaterialRegistrantId,
        MMDShaderOverride::Creator
    );
    if (!status)
    {
        status.perror("Failed to register MMDShaderOverride");
        return status;
    }

    // メイン: mmdToonShader ノードの登録
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

    // メイン: mmdToonShader 用 Viewport 2.0 シェーダーオーバーライドの登録
    status = MHWRender::MDrawRegistry::registerSurfaceShadingNodeOverrideCreator(
        "drawdb/shader/surface/mmdToonShader",
        sToonRegistrantId,
        MMDToonOverride::Creator
    );
    if (!status)
    {
        status.perror("Failed to register MMDToonOverride");
        return status;
    }

    // 独自レンダーオーバーライド (MMDRenderOverride) の登録
    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (theRenderer)
    {
        sMMDRenderOverride = new MMDRenderOverride("mmdRenderOverride");
        status = theRenderer->registerOverride(sMMDRenderOverride);
        if (!status)
        {
            status.perror("Failed to register MMDRenderOverride");
            delete sMMDRenderOverride;
            sMMDRenderOverride = nullptr;
        }
    }

    // MRenderView ブリッジコマンド (mmdRender) の登録
    status = plugin.registerCommand(
        MMDRenderCmd::kCommandName,
        MMDRenderCmd::creator,
        MMDRenderCmd::newSyntax
    );
    if (!status)
    {
        status.perror("Failed to register mmdRender command");
        return status;
    }

    // Hypershade コールバック、AEテンプレート、および MMD レンダラー登録プロシージャ
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
        "        addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdToon/Material\", \"rendernode/MmdToon/Material\", \"-asShader\", \"surfaceShader\");\n"
        "    } else {\n"
        "        for ($filterClass in $filterClassArray) {\n"
        "            if (startsWith($filterClass, \"rendernode/MmdMat\") || startsWith(\"rendernode/MmdMat\", $filterClass) || $filterClass == \"shader/surface\") {\n"
        "                addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdMat/Material\", \"rendernode/MmdMat/Material\", \"-asShader\", \"surfaceShader\");\n"
        "                break;\n"
        "            }\n"
        "            if (startsWith($filterClass, \"rendernode/MmdToon\") || startsWith(\"rendernode/MmdToon\", $filterClass)) {\n"
        "                addToRenderNodeTreeLister($renderNodeTreeLister, $postCommand, \"MmdToon/Material\", \"rendernode/MmdToon/Material\", \"-asShader\", \"surfaceShader\");\n"
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
        "global proc AEmmdToonShaderTemplate(string $nodeName) {\n"
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
        "    editorTemplate -beginLayout \"MMD Shading Control\" -collapse 0;\n"
        "        editorTemplate -addControl \"sphereMode\";\n"
        "        editorTemplate -addControl \"toonMode\";\n"
        "        editorTemplate -addControl \"lightMode\";\n"
        "        editorTemplate -addControl \"shadowMode\";\n"
        "        editorTemplate -addControl \"shadowBias\";\n"
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
        "global proc mmdRenderInvokeProc(int $width, int $height, int $doShadows, int $doGlow, string $camera, string $option) {\n"
        "    if ($camera == \"\") {\n"
        "        string $panel = `getPanel -withFocus`;\n"
        "        if (`getPanel -typeOf $panel` == \"modelPanel\") {\n"
        "            $camera = `modelPanel -query -camera $panel`;\n"
        "        } else {\n"
        "            $camera = \"persp\";\n"
        "        }\n"
        "    }\n"
        "    if ($width <= 0) $width = `getAttr \"defaultResolution.width\"`;\n"
        "    if ($height <= 0) $height = `getAttr \"defaultResolution.height\"`;\n"
        "    print(\"[MMD Renderer] Starting render: camera=\" + $camera + \", resolution=\" + $width + \"x\" + $height + \"\\n\");\n"
        "    mmdRender -w $width -h $height -cam $camera;\n"
        "}\n"
        "global proc mmdBatchRenderInvokeProc(string $option) {\n"
        "    int $w = `getAttr \"defaultResolution.width\"`;\n"
        "    int $h = `getAttr \"defaultResolution.height\"`;\n"
        "    mmdRender -w $w -h $h -b true;\n"
        "}\n"
        "global proc mmdRenderer_Register() {\n"
        "    mmdRenderer_Unregister();\n"
        "    if (!`renderer -exists \"mmdRenderer\"`) {\n"
        "        renderer\n"
        "            -rendererUIName \"MMD Renderer\"\n"
        "            -renderProcedure \"mmdRenderInvokeProc\"\n"
        "            -batchRenderProcedure \"mmdBatchRenderInvokeProc\"\n"
        "            -commandRenderProcedure \"mmdBatchRenderInvokeProc\"\n"
        "            \"mmdRenderer\";\n"
        "        renderer -edit -addGlobalsTab \"Common\"\n"
        "            \"createMayaSoftwareCommonGlobalsTab\"\n"
        "            \"updateMayaSoftwareCommonGlobalsTab\"\n"
        "            \"mmdRenderer\";\n"
        "        print(\"[MMD Renderer] Registered MMD Renderer to Render Settings.\\n\");\n"
        "    }\n"
        "}\n"
        "global proc mmdRenderer_Unregister() {\n"
        "    if (`renderer -exists \"mmdRenderer\"`) {\n"
        "        renderer -unregisterRenderer \"mmdRenderer\";\n"
        "        print(\"[MMD Renderer] Unregistered MMD Renderer.\\n\");\n"
        "    }\n"
        "}\n"
        "mmdMaterial_RegisterCallbacks();\n"
        "mmdRenderer_Register();\n";

    MGlobal::executeCommand(sRegisterCallbacksMel);

    MGlobal::displayInfo("MMD Material & Toon Plugin loaded successfully with MMD Renderer.");
    return MS::kSuccess;
}

// プラグイン解放処理
MStatus uninitializePlugin(MObject obj)
{
    MFnPlugin plugin(obj);
    MStatus status;

    // MMD レンダラー登録解除
    MGlobal::executeCommand("catchQuiet(eval(\"mmdRenderer_Unregister();\"));");

    // MRenderView ブリッジコマンド (mmdRender) の登録解除
    status = plugin.deregisterCommand(MMDRenderCmd::kCommandName);
    if (!status)
    {
        status.perror("Failed to deregister mmdRender command");
    }

    // 独自レンダーオーバーライド (MMDRenderOverride) の登録解除
    MHWRender::MRenderer* theRenderer = MHWRender::MRenderer::theRenderer();
    if (theRenderer && sMMDRenderOverride)
    {
        theRenderer->deregisterOverride(sMMDRenderOverride);
        delete sMMDRenderOverride;
        sMMDRenderOverride = nullptr;
    }

    // Hypershade コールバックの登録解除
    MGlobal::executeCommand("catchQuiet(eval(\"mmdMaterial_UnregisterCallbacks();\"));");

    // mmdToonShader 用 Viewport 2.0 シェーダーオーバーライドの登録解除
    status = MHWRender::MDrawRegistry::deregisterSurfaceShadingNodeOverrideCreator(
        "drawdb/shader/surface/mmdToonShader",
        sToonRegistrantId
    );
    if (!status)
    {
        status.perror("Failed to deregister MMDToonOverride");
    }

    // mmdToonShader ノードの登録解除
    status = plugin.deregisterNode(MMDToonNode::id);
    if (!status)
    {
        status.perror("Failed to deregister mmdToonShader node");
    }

    // mmdMaterial 用 Viewport 2.0 シェーダーオーバーライドの登録解除
    status = MHWRender::MDrawRegistry::deregisterSurfaceShadingNodeOverrideCreator(
        MMDMaterialNode::classification,
        sMaterialRegistrantId
    );
    if (!status)
    {
        status.perror("Failed to deregister MMDShaderOverride");
    }

    // mmdMaterial ノードの登録解除
    status = plugin.deregisterNode(MMDMaterialNode::id);
    if (!status)
    {
        status.perror("Failed to deregister mmdMaterial node");
    }

    MGlobal::displayInfo("MMD Material & Toon Plugin unloaded.");
    return status;
}
