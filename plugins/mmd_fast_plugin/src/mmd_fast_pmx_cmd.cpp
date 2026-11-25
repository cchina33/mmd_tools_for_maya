#include "mmd_fast_pmx_cmd.h"
#include "pmx_binary_parser.h"

#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <maya/MStringArray.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MDagPathArray.h>
#include <maya/MFnTransform.h>
#include <maya/MFnMesh.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnNumericAttribute.h>
#include <maya/MFnSingleIndexedComponent.h>
#include <maya/MFnPointArrayData.h>
#include <maya/MFnComponentListData.h>
#include <maya/MFnSkinCluster.h>
#include <maya/MFloatPointArray.h>
#include <maya/MFloatArray.h>
#include <maya/MVectorArray.h>
#include <maya/MPointArray.h>
#include <maya/MColorArray.h>
#include <maya/MIntArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MPlug.h>

#include <vector>
#include <cmath>
#include <string>

// =====================================================================
// MmdFastImportPmxMeshCmd : PMXメッシュの一括高速生成
// =====================================================================
MStatus MmdFastImportPmxMeshCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 1)
    {
        MGlobal::displayError("[mmd_fast] mmdFastImportPmxMesh requires at least pmx_file_path.");
        return MS::kFailure;
    }

    MString pmxPathStr = args.asString(0, &status);
    MString reqNodeName = (args.length() >= 2) ? args.asString(1, &status) : MString("mmd_mesh");
    double scaleVal = (args.length() >= 3) ? args.asDouble(2, &status) : 0.08;
    float s = static_cast<float>(scaleVal);

    const wchar_t* wchars = pmxPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::PmxParsedModel* model = mmd_fast::PmxBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!model)
    {
        MGlobal::displayError(MString("[mmd_fast] PMX parse failed: ") + errMsg.c_str());
        return MS::kFailure;
    }

    int numVertices = static_cast<int>(model->vertices.size());
    if (numVertices <= 0)
    {
        MGlobal::displayError("[mmd_fast] PMX has no vertices.");
        return MS::kFailure;
    }

    // 材質ごとの面走査および頂点エッジ有効フラグの判定
    std::vector<int8_t> vertEdgeState(static_cast<size_t>(numVertices), -1);
    int totalRawTriangles = static_cast<int>(model->triangleIndices.size() / 3);

    MIntArray polygonCounts;
    MIntArray polygonConnects;
    std::vector<int32_t> validFacesPerMat;
    validFacesPerMat.reserve(model->materials.size());

    int triCursor = 0;
    for (const auto& mat : model->materials)
    {
        // PMX材質のエッジフラグに基づいてエッジ有無を判定
        // モーフ対象の初期透明材質でも頂点エッジ倍率が失われないよう保護
        bool matHasEdge = ((mat.drawFlags & 0x10) != 0);
        int32_t validInMat = 0;

        for (int f = 0; f < mat.faceCount && triCursor < totalRawTriangles; ++f, ++triCursor)
        {
            int32_t i0 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 0];
            int32_t i1 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 1];
            int32_t i2 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 2];

            int32_t indices[3] = { i0, i1, i2 };
            for (int k = 0; k < 3; ++k)
            {
                int32_t vi = indices[k];
                if (vi >= 0 && vi < numVertices)
                {
                    if (vertEdgeState[static_cast<size_t>(vi)] == -1)
                    {
                        vertEdgeState[static_cast<size_t>(vi)] = matHasEdge ? 1 : 0;
                    }
                    else
                    {
                        // 共有頂点ではエッジを持つ側の材質設定を維持
                        vertEdgeState[static_cast<size_t>(vi)] = (vertEdgeState[static_cast<size_t>(vi)] != 0 || matHasEdge) ? 1 : 0;
                    }
                }
            }

            // 縮退三角形（重複頂点を持つ面）をスキップ (Z反転に伴い巻き方向を反転)
            if (i0 != i1 && i1 != i2 && i0 != i2)
            {
                polygonCounts.append(3);
                polygonConnects.append(i0);
                polygonConnects.append(i2);
                polygonConnects.append(i1);
                ++validInMat;
            }
        }
        validFacesPerMat.push_back(validInMat);
    }

    // 材質定義の合計面数を超える残り三角形が存在する場合の保護処理
    for (; triCursor < totalRawTriangles; ++triCursor)
    {
        int32_t i0 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 0];
        int32_t i1 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 1];
        int32_t i2 = model->triangleIndices[static_cast<size_t>(triCursor) * 3 + 2];
        if (i0 != i1 && i1 != i2 && i0 != i2)
        {
            polygonCounts.append(3);
            polygonConnects.append(i0);
            polygonConnects.append(i2);
            polygonConnects.append(i1);
        }
    }

    int numValidFaces = static_cast<int>(polygonCounts.length());

    // 頂点座標・UV・法線・エッジ倍率カラー配列の一括構築
    MFloatPointArray vertexArray(numVertices);
    MFloatArray uArray(numVertices);
    MFloatArray vArray(numVertices);
    MVectorArray normalArray(numVertices);
    MIntArray vertexIndexList(numVertices);
    MColorArray edgeColorArray(numVertices);

    for (int v_i = 0; v_i < numVertices; ++v_i)
    {
        const auto& vtx = model->vertices[static_cast<size_t>(v_i)];
        vertexArray.set(v_i, vtx.pos[0] * s, vtx.pos[1] * s, -vtx.pos[2] * s);
        uArray[v_i] = vtx.uv[0];
        vArray[v_i] = 1.0f - vtx.uv[1];
        normalArray.set(MVector(vtx.normal[0], vtx.normal[1], -vtx.normal[2]), v_i);
        vertexIndexList[v_i] = v_i;

        float eScale = (vertEdgeState[static_cast<size_t>(v_i)] == 0) ? 0.0f : vtx.edgeScale;
        edgeColorArray.set(v_i, eScale, 1.0f, 0.0f, 1.0f);
    }

    // トランスフォームノードの生成
    MFnTransform transFn;
    MObject transObj = transFn.create(MObject::kNullObj, &status);
    if (status != MS::kSuccess)
    {
        MGlobal::displayError("[mmd_fast] Failed to create transform node.");
        return status;
    }
    transFn.setName(reqNodeName);
    MString actualNodeName = transFn.name();

    // メッシュシェイプの一括生成
    MFnMesh meshFn;
    MObject meshObj = meshFn.create(
        numVertices,
        numValidFaces,
        vertexArray,
        polygonCounts,
        polygonConnects,
        uArray,
        vArray,
        transObj,
        &status
    );
    if (status != MS::kSuccess || meshObj.isNull())
    {
        MGlobal::displayError("[mmd_fast] MFnMesh::create failed.");
        return MS::kFailure;
    }

    meshFn.setName(actualNodeName + "Shape");
    meshFn.assignUVs(polygonCounts, polygonConnects);
    meshFn.setVertexNormals(normalArray, vertexIndexList);

    // 頂点カラーセット mmd_edge_scale の一括設定
    MStatus colorStatus;
    MString colorSetName("mmd_edge_scale");
    MString actualColorSet = meshFn.createColorSetWithName(colorSetName, nullptr, nullptr, &colorStatus);
    if (colorStatus == MS::kSuccess)
    {
        meshFn.setCurrentColorSetName(actualColorSet);
        meshFn.setVertexColors(edgeColorArray, vertexIndexList);
    }

    // MMD_model 識別アトリビュートの付与
    MFnNumericAttribute numAttr;
    MObject mmdAttr = numAttr.create("MMD_model", "mmdm", MFnNumericData::kBoolean, true, &status);
    if (status == MS::kSuccess)
    {
        transFn.addAttribute(mmdAttr);
        MPlug mmdPlug = transFn.findPlug("MMD_model", false, &status);
        if (status == MS::kSuccess)
        {
            mmdPlug.setBool(true);
        }
    }

    // 戻り値配列の構築: [実ノード名, 材質0の有効面数, 材質1の有効面数, ...]
    MStringArray resultArray;
    resultArray.append(actualNodeName);
    for (int32_t vf : validFacesPerMat)
    {
        MString vfStr;
        vfStr += vf;
        resultArray.append(vfStr);
    }

    setResult(resultArray);
    return MS::kSuccess;
}

// =====================================================================
// MmdFastApplyPmxBlendShapesCmd : 頂点モーフ差分の一括登録
// =====================================================================
MStatus MmdFastApplyPmxBlendShapesCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 2)
    {
        MGlobal::displayError("[mmd_fast] mmdFastApplyPmxBlendShapes requires (pmx_path, blendshape_node, [scale]).");
        return MS::kFailure;
    }

    MString pmxPathStr = args.asString(0, &status);
    MString bsNodeName = args.asString(1, &status);
    double scaleVal = (args.length() >= 3) ? args.asDouble(2, &status) : 0.08;
    float s = static_cast<float>(scaleVal);

    const wchar_t* wchars = pmxPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::PmxParsedModel* model = mmd_fast::PmxBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!model)
    {
        MGlobal::displayError(MString("[mmd_fast] PMX parse failed: ") + errMsg.c_str());
        return MS::kFailure;
    }

    MSelectionList sel;
    if (sel.add(bsNodeName) != MS::kSuccess)
    {
        MGlobal::displayError(MString("[mmd_fast] BlendShape node not found: ") + bsNodeName);
        return MS::kFailure;
    }

    MObject bsObj;
    sel.getDependNode(0, bsObj);
    MFnDependencyNode fnBs(bsObj, &status);
    if (status != MS::kSuccess)
    {
        return status;
    }

    MPlug plugInputTarget = fnBs.findPlug("inputTarget", false, &status);
    if (status != MS::kSuccess)
    {
        return status;
    }
    MPlug plugInputTarget0 = plugInputTarget.elementByLogicalIndex(0, &status);
    MPlug plugTargetGroup = plugInputTarget0.child(0, &status);
    MPlug plugWeight = fnBs.findPlug("weight", false, &status);

    int32_t numVertices = static_cast<int32_t>(model->vertices.size());
    int registeredCount = 0;

    for (const auto& morph : model->vertexMorphs)
    {
        if (morph.offsets.empty())
        {
            continue;
        }

        int mIdx = morph.vertexMorphOrder;
        MPlug plugGrp = plugTargetGroup.elementByLogicalIndex(static_cast<unsigned int>(mIdx), &status);
        if (status != MS::kSuccess)
        {
            continue;
        }
        MPlug plugItemArray = plugGrp.child(0, &status);
        MPlug plugItem = plugItemArray.elementByLogicalIndex(6000, &status);
        if (status != MS::kSuccess)
        {
            continue;
        }

        MPlug plugPts;
        MPlug plugComps;
        bool hasPts = false;
        bool hasComps = false;

        unsigned int numChildren = plugItem.numChildren();
        for (unsigned int c = 0; c < numChildren; ++c)
        {
            MPlug ch = plugItem.child(c);
            MString chName = ch.name();
            if (chName.indexW("inputPointsTarget") >= 0)
            {
                plugPts = ch;
                hasPts = true;
            }
            else if (chName.indexW("inputComponentsTarget") >= 0)
            {
                plugComps = ch;
                hasComps = true;
            }
        }

        if (!hasPts || !hasComps)
        {
            continue;
        }

        MPointArray ptsArray;
        MFnSingleIndexedComponent fnComp;
        MObject compObj = fnComp.create(MFn::kMeshVertComponent, &status);
        if (status != MS::kSuccess)
        {
            continue;
        }

        for (const auto& off : morph.offsets)
        {
            if (off.vertexIndex >= 0 && off.vertexIndex < numVertices)
            {
                ptsArray.append(MPoint(off.offset[0] * s, off.offset[1] * s, -off.offset[2] * s, 1.0));
                fnComp.addElement(off.vertexIndex);
            }
        }

        if (ptsArray.length() == 0)
        {
            continue;
        }

        MFnPointArrayData fnPtsData;
        MObject ptsDataObj = fnPtsData.create(ptsArray, &status);
        if (status == MS::kSuccess)
        {
            plugPts.setValue(ptsDataObj);
        }

        MFnComponentListData fnCompListData;
        MObject compListObj = fnCompListData.create(&status);
        if (status == MS::kSuccess)
        {
            fnCompListData.add(compObj);
            plugComps.setValue(compListObj);
        }

        if (!plugWeight.isNull())
        {
            MPlug wElem = plugWeight.elementByLogicalIndex(static_cast<unsigned int>(mIdx), &status);
            if (status == MS::kSuccess)
            {
                wElem.setDouble(0.0);
            }
        }

        ++registeredCount;
    }

    setResult(registeredCount);
    return MS::kSuccess;
}

// =====================================================================
// MmdFastApplyPmxSkinWeightsCmd : スキニングウェイトの一括注入
// =====================================================================
MStatus MmdFastApplyPmxSkinWeightsCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 3)
    {
        MGlobal::displayError("[mmd_fast] mmdFastApplyPmxSkinWeights requires (pmx_path, mesh_node, skin_cluster_node).");
        return MS::kFailure;
    }

    MString pmxPathStr = args.asString(0, &status);
    MString meshNodeName = args.asString(1, &status);
    MString skinClusterName = args.asString(2, &status);

    const wchar_t* wchars = pmxPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::PmxParsedModel* model = mmd_fast::PmxBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!model)
    {
        MGlobal::displayError(MString("[mmd_fast] PMX parse failed: ") + errMsg.c_str());
        return MS::kFailure;
    }

    MSelectionList sel;
    if (sel.add(meshNodeName) != MS::kSuccess || sel.add(skinClusterName) != MS::kSuccess)
    {
        MGlobal::displayError("[mmd_fast] Target mesh or skinCluster node not found.");
        return MS::kFailure;
    }

    MDagPath meshDagPath;
    sel.getDagPath(0, meshDagPath);
    meshDagPath.extendToShape();

    MObject skinObj;
    sel.getDependNode(1, skinObj);
    MFnSkinCluster fnSkin(skinObj, &status);
    if (status != MS::kSuccess)
    {
        MGlobal::displayError("[mmd_fast] Failed to initialize MFnSkinCluster.");
        return status;
    }

    MDagPathArray infPaths;
    unsigned int numInfs = fnSkin.influenceObjects(infPaths, &status);
    if (status != MS::kSuccess || numInfs == 0)
    {
        MGlobal::displayError("[mmd_fast] skinCluster has no influence objects.");
        return MS::kFailure;
    }

    MIntArray infIndices(numInfs);
    for (unsigned int i = 0; i < numInfs; ++i)
    {
        infIndices[i] = static_cast<int>(i);
    }

    int numVertices = static_cast<int>(model->vertices.size());
    MFnSingleIndexedComponent fnComp;
    MObject compObj = fnComp.create(MFn::kMeshVertComponent, &status);
    for (int v_i = 0; v_i < numVertices; ++v_i)
    {
        fnComp.addElement(v_i);
    }

    unsigned int totalWeightCount = static_cast<unsigned int>(numVertices) * numInfs;
    MDoubleArray weights(totalWeightCount, 0.0);
    int maxBoneIdx = static_cast<int>(numInfs);

    for (int v_i = 0; v_i < numVertices; ++v_i)
    {
        const auto& vtx = model->vertices[static_cast<size_t>(v_i)];
        unsigned int baseOffset = static_cast<unsigned int>(v_i) * numInfs;

        int bIndices[4] = { -1, -1, -1, -1 };
        double bVals[4] = { 0.0, 0.0, 0.0, 0.0 };
        int count = 0;

        if (vtx.weightType == 0) // BDEF1
        {
            bIndices[0] = vtx.boneIndices[0];
            bVals[0] = 1.0;
            count = 1;
        }
        else if (vtx.weightType == 1 || vtx.weightType == 3) // BDEF2 / SDEF
        {
            bIndices[0] = vtx.boneIndices[0];
            bIndices[1] = vtx.boneIndices[1];
            double w0 = static_cast<double>(vtx.boneWeights[0]);
            bVals[0] = w0;
            bVals[1] = 1.0 - w0;
            count = 2;
        }
        else if (vtx.weightType == 2 || vtx.weightType == 4) // BDEF4 / QDEF
        {
            for (int k = 0; k < 4; ++k)
            {
                bIndices[k] = vtx.boneIndices[k];
                bVals[k] = static_cast<double>(vtx.boneWeights[k]);
            }
            count = 4;
        }
        else
        {
            bIndices[0] = 0;
            bVals[0] = 1.0;
            count = 1;
        }

        double sumW = 0.0;
        for (int k = 0; k < count; ++k)
        {
            int bi = bIndices[k];
            double bw = bVals[k];
            if (bi >= 0 && bi < maxBoneIdx && !std::isnan(bw) && bw > 0.0)
            {
                weights[baseOffset + static_cast<unsigned int>(bi)] += bw;
                sumW += bw;
            }
        }

        if (sumW <= 1e-6 || std::isnan(sumW))
        {
            weights[baseOffset + 0] = 1.0;
        }
        else if (std::abs(sumW - 1.0) > 1e-5)
        {
            double invSum = 1.0 / sumW;
            for (int k = 0; k < count; ++k)
            {
                int bi = bIndices[k];
                if (bi >= 0 && bi < maxBoneIdx)
                {
                    // 複数スロットに同一ボーンが指定された場合の重複除算を防ぐため対象インデックスのみ一度正規化
                    bool alreadyScaled = false;
                    for (int prev = 0; prev < k; ++prev)
                    {
                        if (bIndices[prev] == bi)
                        {
                            alreadyScaled = true;
                            break;
                        }
                    }
                    if (!alreadyScaled)
                    {
                        weights[baseOffset + static_cast<unsigned int>(bi)] *= invSum;
                    }
                }
            }
        }
    }

    status = fnSkin.setWeights(meshDagPath, compObj, infIndices, weights, false, nullptr);
    if (status != MS::kSuccess)
    {
        MGlobal::displayError("[mmd_fast] MFnSkinCluster::setWeights failed.");
        setResult(0);
        return status;
    }

    setResult(1);
    return MS::kSuccess;
}

