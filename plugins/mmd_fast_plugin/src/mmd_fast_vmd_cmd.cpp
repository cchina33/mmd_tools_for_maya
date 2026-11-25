#include "mmd_fast_vmd_cmd.h"
#include "vmd_binary_parser.h"

#include <maya/MGlobal.h>
#include <maya/MString.h>
#include <maya/MStringArray.h>
#include <maya/MIntArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MTime.h>
#include <maya/MTimeArray.h>
#include <maya/MAngle.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MFnTransform.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnAnimCurve.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MQuaternion.h>
#include <maya/MEulerRotation.h>

#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <thread>

namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kDegToRad = kPi / 180.0;
constexpr double kRadToDeg = 180.0 / kPi;

struct BezierPoints
{
    double x1;
    double y1;
    double x2;
    double y2;
};

struct SegmentTangent
{
    double outAngleDeg;
    double outWeight;
    double inAngleDeg;
    double inWeight;
    bool valid;
};

inline BezierPoints extractBoneBezier(const uint8_t* interp, int channelIdx)
{
    int c = channelIdx;
    BezierPoints bp;
    bp.x1 = static_cast<double>(interp[c]) / 127.0;
    bp.y1 = static_cast<double>(interp[4 + c]) / 127.0;
    bp.x2 = static_cast<double>(interp[8 + c]) / 127.0;
    bp.y2 = static_cast<double>(interp[12 + c]) / 127.0;
    return bp;
}

inline BezierPoints extractCameraBezier(const uint8_t* interp, int channelIdx)
{
    int offset = channelIdx * 4;
    BezierPoints bp;
    bp.x1 = static_cast<double>(interp[offset + 0]) / 127.0;
    bp.x2 = static_cast<double>(interp[offset + 1]) / 127.0;
    bp.y1 = static_cast<double>(interp[offset + 2]) / 127.0;
    bp.y2 = static_cast<double>(interp[offset + 3]) / 127.0;
    return bp;
}

inline double evalCameraBezier(const BezierPoints& bp, double t)
{
    if (t <= 0.0) return 0.0;
    if (t >= 1.0) return 1.0;

    double uLow = 0.0;
    double uHigh = 1.0;
    double u = t;

    for (int iter = 0; iter < 32; ++iter)
    {
        u = (uLow + uHigh) * 0.5;
        double oneMinusU = 1.0 - u;
        double cx = 3.0 * oneMinusU * oneMinusU * u * bp.x1
                  + 3.0 * oneMinusU * u * u * bp.x2
                  + u * u * u;
        if (std::abs(cx - t) < 1e-6)
        {
            break;
        }
        if (cx < t)
        {
            uLow = u;
        }
        else
        {
            uHigh = u;
        }
    }

    double oneMinusU = 1.0 - u;
    double cy = 3.0 * oneMinusU * oneMinusU * u * bp.y1
              + 3.0 * oneMinusU * u * u * bp.y2
              + u * u * u;
    return std::max(0.0, std::min(1.0, cy));
}

void computeSegmentTangents(
    const std::vector<uint32_t>& frames,
    const std::vector<double>& uiValues,
    const std::vector<BezierPoints>& beziers,
    std::vector<SegmentTangent>& outTangents)
{
    size_t n = frames.size();
    if (n < 2)
    {
        outTangents.clear();
        return;
    }

    outTangents.resize(n - 1);
    for (size_t i = 0; i < n - 1; ++i)
    {
        double dt = static_cast<double>(frames[i + 1]) - static_cast<double>(frames[i]);
        if (dt <= 0.0)
        {
            outTangents[i] = { 0.0, 1.0, 0.0, 1.0, false };
            continue;
        }

        double dv = uiValues[i + 1] - uiValues[i];
        const BezierPoints& bp = beziers[i + 1];

        double dxOut = std::max(1e-4, bp.x1 * dt);
        double dvOut = bp.y1 * dv;
        double outAngle = std::atan2(dvOut, dxOut) * kRadToDeg;
        double outWeight = std::max(1e-4, std::sqrt(dxOut * dxOut + dvOut * dvOut) / 3.0);

        double dxIn = std::max(1e-4, (1.0 - bp.x2) * dt);
        double dvIn = (1.0 - bp.y2) * dv;
        double inAngle = std::atan2(dvIn, dxIn) * kRadToDeg;
        double inWeight = std::max(1e-4, std::sqrt(dxIn * dxIn + dvIn * dvIn) / 3.0);

        outTangents[i] = { outAngle, outWeight, inAngle, inWeight, true };
    }
}

MStatus obtainOrResetAnimCurve(
    MPlug& plug,
    MFnAnimCurve::AnimCurveType curveType,
    MFnAnimCurve& outFnCurve)
{
    MStatus status;
    MObject animCurveObj = MObject::kNullObj;

    if (plug.isConnected())
    {
        MPlugArray connections;
        plug.connectedTo(connections, true, false);
        for (unsigned int i = 0; i < connections.length(); ++i)
        {
            MObject sourceNode = connections[i].node();
            if (sourceNode.hasFn(MFn::kAnimCurve))
            {
                animCurveObj = sourceNode;
                break;
            }
        }
    }

    if (animCurveObj.isNull())
    {
        animCurveObj = outFnCurve.create(plug, curveType, nullptr, &status);
        if (status != MS::kSuccess)
        {
            return status;
        }
    }
    else
    {
        outFnCurve.setObject(animCurveObj);
    }

    while (outFnCurve.numKeys() > 0)
    {
        outFnCurve.remove(0);
    }

    return MS::kSuccess;
}

MStatus injectCurveWithBezier(
    MPlug& plug,
    MFnAnimCurve::AnimCurveType curveType,
    const std::vector<uint32_t>& frames,
    const std::vector<double>& internalValues,
    const std::vector<SegmentTangent>& tangents)
{
    if (plug.isNull() || frames.empty())
    {
        return MS::kSuccess;
    }

    MFnAnimCurve fnCurve;
    MStatus status = obtainOrResetAnimCurve(plug, curveType, fnCurve);
    if (status != MS::kSuccess)
    {
        return status;
    }

    unsigned int numKeys = static_cast<unsigned int>(frames.size());
    MTimeArray timeArray;
    timeArray.setLength(numKeys);
    MDoubleArray valArray(numKeys);

    MTime::Unit uiUnit = MTime::uiUnit();
    for (unsigned int i = 0; i < numKeys; ++i)
    {
        timeArray.set(MTime(static_cast<double>(frames[i]), uiUnit), i);
        valArray.set(internalValues[i], i);
    }

    status = fnCurve.addKeys(
        &timeArray,
        &valArray,
        MFnAnimCurve::kTangentSmooth,
        MFnAnimCurve::kTangentSmooth
    );
    if (status != MS::kSuccess)
    {
        return status;
    }

    if (numKeys >= 2 && tangents.size() == static_cast<size_t>(numKeys - 1))
    {
        fnCurve.setIsWeighted(true);
        for (unsigned int i = 0; i < numKeys; ++i)
        {
            fnCurve.setTangentsLocked(i, false);
        }

        for (unsigned int i = 0; i < numKeys - 1; ++i)
        {
            const SegmentTangent& seg = tangents[i];
            if (!seg.valid)
            {
                continue;
            }
            fnCurve.setOutTangentType(i, MFnAnimCurve::kTangentFixed);
            fnCurve.setTangent(i, MAngle(seg.outAngleDeg, MAngle::kDegrees), seg.outWeight, false, nullptr, true);

            fnCurve.setInTangentType(i + 1, MFnAnimCurve::kTangentFixed);
            fnCurve.setTangent(i + 1, MAngle(seg.inAngleDeg, MAngle::kDegrees), seg.inWeight, true, nullptr, true);
        }
    }

    return MS::kSuccess;
}

MStatus injectCurveSmooth(
    MPlug& plug,
    MFnAnimCurve::AnimCurveType curveType,
    MTimeArray& timeArray,
    MDoubleArray& valArray)
{
    if (plug.isNull() || timeArray.length() == 0)
    {
        return MS::kSuccess;
    }

    MFnAnimCurve fnCurve;
    MStatus status = obtainOrResetAnimCurve(plug, curveType, fnCurve);
    if (status != MS::kSuccess)
    {
        return status;
    }

    return fnCurve.addKeys(
        &timeArray,
        &valArray,
        MFnAnimCurve::kTangentSmooth,
        MFnAnimCurve::kTangentSmooth
    );
}

struct BoneWorkItem
{
    const std::vector<mmd_fast::VmdBoneKey>* keys = nullptr;
    MObject jointObj;
    double initTx = 0.0;
    double initTy = 0.0;
    double initTz = 0.0;
    MQuaternion invJoQ;
    MQuaternion invRaQ;
    MEulerRotation::RotationOrder rotOrder = MEulerRotation::kXYZ;
    int movableMode = 0; // 0: 回転のみ, 1: 常時移動可, 2: 有意な移動値があるフレームのみ移動

    // 並列計算結果
    std::vector<uint32_t> rotFrames;
    std::vector<double> rxRad;
    std::vector<double> ryRad;
    std::vector<double> rzRad;
    std::vector<SegmentTangent> rxTangents;
    std::vector<SegmentTangent> ryTangents;
    std::vector<SegmentTangent> rzTangents;

    std::vector<uint32_t> transFrames;
    std::vector<double> txVals;
    std::vector<double> tyVals;
    std::vector<double> tzVals;
    std::vector<SegmentTangent> txTangents;
    std::vector<SegmentTangent> tyTangents;
    std::vector<SegmentTangent> tzTangents;
};

void evaluateBoneTrackRange(std::vector<BoneWorkItem>& items, size_t startIdx, size_t endIdx, double scale)
{
    for (size_t idx = startIdx; idx < endIdx; ++idx)
    {
        BoneWorkItem& item = items[idx];
        if (!item.keys || item.keys->empty())
        {
            continue;
        }

        const auto& keys = *item.keys;
        size_t numKeys = keys.size();

        item.rotFrames.reserve(numKeys);
        item.rxRad.reserve(numKeys);
        item.ryRad.reserve(numKeys);
        item.rzRad.reserve(numKeys);

        std::vector<double> rxDeg;
        std::vector<double> ryDeg;
        std::vector<double> rzDeg;
        std::vector<BezierPoints> rotBeziers;
        rxDeg.reserve(numKeys);
        ryDeg.reserve(numKeys);
        rzDeg.reserve(numKeys);
        rotBeziers.reserve(numKeys);

        std::vector<BezierPoints> txBeziers;
        std::vector<BezierPoints> tyBeziers;
        std::vector<BezierPoints> tzBeziers;

        MEulerRotation prevEuler(0.0, 0.0, 0.0, item.rotOrder);
        bool hasPrevEuler = false;

        for (size_t k = 0; k < numKeys; ++k)
        {
            const auto& bf = keys[k];

            // MMD左手系からMaya右手系へのクォータニオン変換 (-qx, -qy, qz, qw)
            MQuaternion qMaya(-bf.rot[0], -bf.rot[1], bf.rot[2], bf.rot[3]);
            MQuaternion localRotQ = item.invJoQ * qMaya * item.invRaQ;

            MEulerRotation euler = localRotQ.asEulerRotation();
            euler.reorderIt(item.rotOrder);
            if (hasPrevEuler)
            {
                euler = euler.closestSolution(prevEuler);
            }
            prevEuler = euler;
            hasPrevEuler = true;

            item.rotFrames.push_back(bf.frame);
            item.rxRad.push_back(euler.x);
            item.ryRad.push_back(euler.y);
            item.rzRad.push_back(euler.z);

            rxDeg.push_back(euler.x * kRadToDeg);
            ryDeg.push_back(euler.y * kRadToDeg);
            rzDeg.push_back(euler.z * kRadToDeg);
            rotBeziers.push_back(extractBoneBezier(bf.interpolation, 3));

            bool writeTrans = false;
            if (item.movableMode == 1)
            {
                writeTrans = true;
            }
            else if (item.movableMode == 2)
            {
                if (std::abs(bf.pos[0]) > 1e-4f || std::abs(bf.pos[1]) > 1e-4f || std::abs(bf.pos[2]) > 1e-4f)
                {
                    writeTrans = true;
                }
            }

            if (writeTrans)
            {
                double tx = item.initTx + static_cast<double>(bf.pos[0]) * scale;
                double ty = item.initTy + static_cast<double>(bf.pos[1]) * scale;
                double tz = item.initTz - static_cast<double>(bf.pos[2]) * scale;

                item.transFrames.push_back(bf.frame);
                item.txVals.push_back(tx);
                item.tyVals.push_back(ty);
                item.tzVals.push_back(tz);

                txBeziers.push_back(extractBoneBezier(bf.interpolation, 0));
                tyBeziers.push_back(extractBoneBezier(bf.interpolation, 1));
                tzBeziers.push_back(extractBoneBezier(bf.interpolation, 2));
            }
        }

        computeSegmentTangents(item.rotFrames, rxDeg, rotBeziers, item.rxTangents);
        computeSegmentTangents(item.rotFrames, ryDeg, rotBeziers, item.ryTangents);
        computeSegmentTangents(item.rotFrames, rzDeg, rotBeziers, item.rzTangents);

        if (item.transFrames.size() >= 2)
        {
            computeSegmentTangents(item.transFrames, item.txVals, txBeziers, item.txTangents);
            computeSegmentTangents(item.transFrames, item.tyVals, tyBeziers, item.tyTangents);
            computeSegmentTangents(item.transFrames, item.tzVals, tzBeziers, item.tzTangents);
        }
    }
}

} // namespace

// =====================================================================
// MmdFastImportVmdBoneCmd : VMDボーンモーションの並列計算＆一括注入
// =====================================================================
MStatus MmdFastImportVmdBoneCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 5)
    {
        MGlobal::displayError("[mmd_fast] mmdFastImportVmdBone requires (vmd_path, scale, bone_names, joint_paths, movable_modes).");
        return MS::kFailure;
    }

    unsigned int idx0 = 0;
    unsigned int idx1 = 1;
    unsigned int idx2 = 2;
    unsigned int idx3 = 3;
    unsigned int idx4 = 4;

    MString vmdPathStr = args.asString(idx0, &status);
    double scale = args.asDouble(idx1, &status);
    MStringArray boneNames = args.asStringArray(idx2, &status);
    MStringArray jointPaths = args.asStringArray(idx3, &status);
    MIntArray movableModes = args.asIntArray(idx4, &status);

    unsigned int numBones = boneNames.length();
    if (jointPaths.length() != numBones || movableModes.length() != numBones)
    {
        MGlobal::displayError("[mmd_fast] Array lengths mismatch in mmdFastImportVmdBone.");
        return MS::kFailure;
    }

    const wchar_t* wchars = vmdPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::VmdParsedMotion* motion = mmd_fast::VmdBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!motion)
    {
        MGlobal::displayError(MString("[mmd_fast] VMD parse failed: ") + errMsg.c_str());
        return MS::kFailure;
    }

    std::vector<BoneWorkItem> workItems;
    workItems.reserve(numBones);

    for (unsigned int i = 0; i < numBones; ++i)
    {
        std::string bNameUtf8(boneNames[i].asUTF8());
        auto it = motion->boneTracks.find(bNameUtf8);
        if (it == motion->boneTracks.end() || it->second.empty())
        {
            continue;
        }

        MSelectionList sel;
        if (sel.add(jointPaths[i]) != MS::kSuccess)
        {
            continue;
        }

        MObject jObj;
        sel.getDependNode(0, jObj);
        MFnDependencyNode fnDep(jObj, &status);
        if (status != MS::kSuccess)
        {
            continue;
        }

        BoneWorkItem item;
        item.keys = &(it->second);
        item.jointObj = jObj;
        item.movableMode = movableModes[i];

        // 初期位置の取得 (mmdInitialTranslate があれば優先利用、なければ現在の translate を利用)
        bool gotInitT = false;
        MPlug initTPlug = fnDep.findPlug("mmdInitialTranslate", false, &status);
        if (status == MS::kSuccess && !initTPlug.isNull() && initTPlug.numChildren() >= 3)
        {
            item.initTx = initTPlug.child(0).asDouble();
            item.initTy = initTPlug.child(1).asDouble();
            item.initTz = initTPlug.child(2).asDouble();
            gotInitT = true;
        }
        if (!gotInitT)
        {
            MPlug txP = fnDep.findPlug("translateX", false, &status);
            MPlug tyP = fnDep.findPlug("translateY", false, &status);
            MPlug tzP = fnDep.findPlug("translateZ", false, &status);
            if (!txP.isNull()) item.initTx = txP.asDouble();
            if (!tyP.isNull()) item.initTy = tyP.asDouble();
            if (!tzP.isNull()) item.initTz = tzP.asDouble();
        }

        // jointOrient の取得
        MPlug joPlug = fnDep.findPlug("jointOrient", false, &status);
        if (status == MS::kSuccess && !joPlug.isNull() && joPlug.numChildren() >= 3)
        {
            double jox = joPlug.child(0).asMAngle().asRadians();
            double joy = joPlug.child(1).asMAngle().asRadians();
            double joz = joPlug.child(2).asMAngle().asRadians();
            MEulerRotation joEuler(jox, joy, joz, MEulerRotation::kXYZ);
            item.invJoQ = joEuler.asQuaternion().inverse();
        }

        // rotateAxis の取得
        MPlug raPlug = fnDep.findPlug("rotateAxis", false, &status);
        if (status == MS::kSuccess && !raPlug.isNull() && raPlug.numChildren() >= 3)
        {
            double rax = raPlug.child(0).asMAngle().asRadians();
            double ray = raPlug.child(1).asMAngle().asRadians();
            double raz = raPlug.child(2).asMAngle().asRadians();
            MEulerRotation raEuler(rax, ray, raz, MEulerRotation::kXYZ);
            item.invRaQ = raEuler.asQuaternion().inverse();
        }

        // rotateOrder の取得
        MPlug roPlug = fnDep.findPlug("rotateOrder", false, &status);
        if (status == MS::kSuccess && !roPlug.isNull())
        {
            int roVal = roPlug.asInt();
            if (roVal >= 0 && roVal <= 5)
            {
                item.rotOrder = static_cast<MEulerRotation::RotationOrder>(roVal);
            }
        }

        workItems.push_back(std::move(item));
    }

    size_t totalWork = workItems.size();
    if (totalWork == 0)
    {
        MIntArray res;
        res.append(0);
        res.append(0);
        setResult(res);
        return MS::kSuccess;
    }

    // マルチスレッドでオイラー角変換・連続角維持・ベジェ接線パラメータを一括並列計算
    unsigned int hwThreads = std::thread::hardware_concurrency();
    if (hwThreads == 0) hwThreads = 4;
    size_t numThreads = std::min(static_cast<size_t>(hwThreads), totalWork);

    if (numThreads <= 1 || totalWork < 4)
    {
        evaluateBoneTrackRange(workItems, 0, totalWork, scale);
    }
    else
    {
        std::vector<std::thread> workers;
        workers.reserve(numThreads);
        size_t chunkSize = (totalWork + numThreads - 1) / numThreads;
        for (size_t t = 0; t < numThreads; ++t)
        {
            size_t startIdx = t * chunkSize;
            if (startIdx >= totalWork) break;
            size_t endIdx = std::min(startIdx + chunkSize, totalWork);
            workers.emplace_back(evaluateBoneTrackRange, std::ref(workItems), startIdx, endIdx, scale);
        }
        for (auto& th : workers)
        {
            if (th.joinable())
            {
                th.join();
            }
        }
    }

    // メインスレッドで Maya アニメーションカーブへ一括注入
    int appliedBones = 0;
    int totalKeys = 0;

    for (auto& item : workItems)
    {
        if (item.rotFrames.empty())
        {
            continue;
        }

        MFnDependencyNode fnDep(item.jointObj, &status);
        if (status != MS::kSuccess)
        {
            continue;
        }

        MPlug plugRx = fnDep.findPlug("rotateX", false, &status);
        MPlug plugRy = fnDep.findPlug("rotateY", false, &status);
        MPlug plugRz = fnDep.findPlug("rotateZ", false, &status);

        injectCurveWithBezier(plugRx, MFnAnimCurve::kAnimCurveTA, item.rotFrames, item.rxRad, item.rxTangents);
        injectCurveWithBezier(plugRy, MFnAnimCurve::kAnimCurveTA, item.rotFrames, item.ryRad, item.ryTangents);
        injectCurveWithBezier(plugRz, MFnAnimCurve::kAnimCurveTA, item.rotFrames, item.rzRad, item.rzTangents);

        if (!item.transFrames.empty())
        {
            MPlug plugTx = fnDep.findPlug("translateX", false, &status);
            MPlug plugTy = fnDep.findPlug("translateY", false, &status);
            MPlug plugTz = fnDep.findPlug("translateZ", false, &status);

            injectCurveWithBezier(plugTx, MFnAnimCurve::kAnimCurveTL, item.transFrames, item.txVals, item.txTangents);
            injectCurveWithBezier(plugTy, MFnAnimCurve::kAnimCurveTL, item.transFrames, item.tyVals, item.tyTangents);
            injectCurveWithBezier(plugTz, MFnAnimCurve::kAnimCurveTL, item.transFrames, item.tzVals, item.tzTangents);
        }

        ++appliedBones;
        totalKeys += static_cast<int>(item.rotFrames.size());
    }

    MIntArray result;
    result.append(appliedBones);
    result.append(totalKeys);
    setResult(result);
    return MS::kSuccess;
}

// =====================================================================
// MmdFastImportVmdMorphCmd : VMDモーフキーフレームの一括注入
// =====================================================================
MStatus MmdFastImportVmdMorphCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 3)
    {
        MGlobal::displayError("[mmd_fast] mmdFastImportVmdMorph requires (vmd_path, morph_names, target_plugs).");
        return MS::kFailure;
    }

    unsigned int idx0 = 0;
    unsigned int idx1 = 1;
    unsigned int idx2 = 2;

    MString vmdPathStr = args.asString(idx0, &status);
    MStringArray morphNames = args.asStringArray(idx1, &status);
    MStringArray targetPlugs = args.asStringArray(idx2, &status);

    unsigned int numMorphs = morphNames.length();
    if (targetPlugs.length() != numMorphs)
    {
        MGlobal::displayError("[mmd_fast] Array lengths mismatch in mmdFastImportVmdMorph.");
        return MS::kFailure;
    }

    const wchar_t* wchars = vmdPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::VmdParsedMotion* motion = mmd_fast::VmdBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!motion)
    {
        MGlobal::displayError(MString("[mmd_fast] VMD parse failed: ") + errMsg.c_str());
        return MS::kFailure;
    }

    int appliedMorphs = 0;
    int totalKeys = 0;
    MTime::Unit uiUnit = MTime::uiUnit();

    for (unsigned int i = 0; i < numMorphs; ++i)
    {
        std::string mNameUtf8(morphNames[i].asUTF8());
        auto it = motion->morphTracks.find(mNameUtf8);
        if (it == motion->morphTracks.end() || it->second.empty())
        {
            continue;
        }

        MSelectionList sel;
        if (sel.add(targetPlugs[i]) != MS::kSuccess)
        {
            continue;
        }

        MPlug plug;
        if (sel.getPlug(0, plug) != MS::kSuccess || plug.isNull())
        {
            continue;
        }

        const auto& keys = it->second;
        unsigned int numKeys = static_cast<unsigned int>(keys.size());
        MTimeArray times;
        times.setLength(numKeys);
        MDoubleArray vals(numKeys);

        for (unsigned int k = 0; k < numKeys; ++k)
        {
            times.set(MTime(static_cast<double>(keys[k].frame), uiUnit), k);
            double w = std::max(0.0, std::min(1.0, static_cast<double>(keys[k].weight)));
            vals.set(w, k);
        }

        if (injectCurveSmooth(plug, MFnAnimCurve::kAnimCurveTU, times, vals) == MS::kSuccess)
        {
            ++appliedMorphs;
            totalKeys += static_cast<int>(numKeys);
        }
    }

    MIntArray result;
    result.append(appliedMorphs);
    result.append(totalKeys);
    setResult(result);
    return MS::kSuccess;
}

// =====================================================================
// MmdFastImportVmdCameraCmd : VMDカメラの高速ベジェ展開＆一括注入
// =====================================================================
MStatus MmdFastImportVmdCameraCmd::doIt(const MArgList& args)
{
    MStatus status;
    if (args.length() < 6)
    {
        MGlobal::displayError("[mmd_fast] mmdFastImportVmdCamera requires (vmd_path, scale, aim_locator, cam_trans, cam_shape, aperture_mm).");
        return MS::kFailure;
    }

    MString vmdPathStr = args.asString(0, &status);
    double scale = args.asDouble(1, &status);
    MString aimLocatorName = args.asString(2, &status);
    MString camTransName = args.asString(3, &status);
    MString camShapeName = args.asString(4, &status);
    double apertureMm = args.asDouble(5, &status);

    const wchar_t* wchars = vmdPathStr.asWChar();
    std::wstring wPath(wchars ? wchars : L"");

    std::string errMsg;
    const mmd_fast::VmdParsedMotion* motion = mmd_fast::VmdBinaryCache::getOrParse(wPath, false, &errMsg);
    if (!motion || motion->cameraFrames.empty())
    {
        setResult(0);
        return MS::kSuccess;
    }

    MSelectionList sel;
    if (sel.add(aimLocatorName) != MS::kSuccess ||
        sel.add(camTransName) != MS::kSuccess ||
        sel.add(camShapeName) != MS::kSuccess)
    {
        MGlobal::displayError("[mmd_fast] Camera rig nodes not found.");
        return MS::kFailure;
    }

    MObject aimObj, transObj, shapeObj;
    sel.getDependNode(0, aimObj);
    sel.getDependNode(1, transObj);
    sel.getDependNode(2, shapeObj);

    MFnDependencyNode fnAim(aimObj);
    MFnDependencyNode fnTrans(transObj);
    MFnDependencyNode fnShape(shapeObj);

    MPlug plugAimTx = fnAim.findPlug("translateX", false);
    MPlug plugAimTy = fnAim.findPlug("translateY", false);
    MPlug plugAimTz = fnAim.findPlug("translateZ", false);
    MPlug plugAimRx = fnAim.findPlug("rotateX", false);
    MPlug plugAimRy = fnAim.findPlug("rotateY", false);
    MPlug plugAimRz = fnAim.findPlug("rotateZ", false);
    MPlug plugCamTz = fnTrans.findPlug("translateZ", false);
    MPlug plugFocal = fnShape.findPlug("focalLength", false);

    const auto& camFrames = motion->cameraFrames;
    size_t numKeyFrames = camFrames.size();

    std::vector<uint32_t> evalFrames;
    std::vector<double> txVec, tyVec, tzVec;
    std::vector<double> rxRadVec, ryRadVec, rzRadVec;
    std::vector<double> distVec, flVec;

    if (numKeyFrames == 1)
    {
        const auto& cf = camFrames[0];
        evalFrames.push_back(cf.frame);
        txVec.push_back(static_cast<double>(cf.pos[0]) * scale);
        tyVec.push_back(static_cast<double>(cf.pos[1]) * scale);
        tzVec.push_back(-static_cast<double>(cf.pos[2]) * scale);
        rxRadVec.push_back(static_cast<double>(cf.rot[0]));
        ryRadVec.push_back(static_cast<double>(cf.rot[1]));
        rzRadVec.push_back(-static_cast<double>(cf.rot[2]));
        distVec.push_back(-static_cast<double>(cf.distance) * scale);

        double fovRad = (cf.fov > 0) ? (static_cast<double>(cf.fov) * kDegToRad) : (30.0 * kDegToRad);
        double fl = (apertureMm * 0.5) / std::tan(fovRad * 0.5);
        flVec.push_back(fl);
    }
    else
    {
        size_t estimatedSamples = static_cast<size_t>(camFrames.back().frame - camFrames.front().frame + 2);
        evalFrames.reserve(estimatedSamples);
        txVec.reserve(estimatedSamples);
        tyVec.reserve(estimatedSamples);
        tzVec.reserve(estimatedSamples);
        rxRadVec.reserve(estimatedSamples);
        ryRadVec.reserve(estimatedSamples);
        rzRadVec.reserve(estimatedSamples);
        distVec.reserve(estimatedSamples);
        flVec.reserve(estimatedSamples);

        for (size_t i = 0; i < numKeyFrames - 1; ++i)
        {
            const auto& prevCf = camFrames[i];
            const auto& nextCf = camFrames[i + 1];
            uint32_t fStart = prevCf.frame;
            uint32_t fEnd = nextCf.frame;
            double dt = static_cast<double>(fEnd) - static_cast<double>(fStart);

            BezierPoints bx = extractCameraBezier(nextCf.interpolation, 0);
            BezierPoints by = extractCameraBezier(nextCf.interpolation, 1);
            BezierPoints bz = extractCameraBezier(nextCf.interpolation, 2);
            BezierPoints brot = extractCameraBezier(nextCf.interpolation, 3);
            BezierPoints bdist = extractCameraBezier(nextCf.interpolation, 4);
            BezierPoints bfov = extractCameraBezier(nextCf.interpolation, 5);

            double pRx = static_cast<double>(prevCf.rot[0]);
            double pRy = static_cast<double>(prevCf.rot[1]);
            double pRz = -static_cast<double>(prevCf.rot[2]);
            double nRx = static_cast<double>(nextCf.rot[0]);
            double nRy = static_cast<double>(nextCf.rot[1]);
            double nRz = -static_cast<double>(nextCf.rot[2]);

            double pDist = static_cast<double>(prevCf.distance);
            double nDist = static_cast<double>(nextCf.distance);
            double pFov = static_cast<double>(prevCf.fov);
            double nFov = static_cast<double>(nextCf.fov);

            std::vector<uint32_t> sectionFrames;
            if (dt <= 1.0)
            {
                sectionFrames.push_back(fStart);
                if (i == numKeyFrames - 2 && fEnd != fStart)
                {
                    sectionFrames.push_back(fEnd);
                }
            }
            else
            {
                uint32_t rangeEnd = (i == numKeyFrames - 2) ? (fEnd + 1) : fEnd;
                for (uint32_t f = fStart; f < rangeEnd; ++f)
                {
                    sectionFrames.push_back(f);
                }
            }

            for (uint32_t f : sectionFrames)
            {
                if (!evalFrames.empty() && evalFrames.back() == f)
                {
                    // 同一フレーム重複時は末尾を上書きするためにポップ
                    evalFrames.pop_back();
                    txVec.pop_back();
                    tyVec.pop_back();
                    tzVec.pop_back();
                    rxRadVec.pop_back();
                    ryRadVec.pop_back();
                    rzRadVec.pop_back();
                    distVec.pop_back();
                    flVec.pop_back();
                }

                double t = (dt > 0.0) ? (static_cast<double>(f - fStart) / dt) : 0.0;
                t = std::max(0.0, std::min(1.0, t));

                double wx = evalCameraBezier(bx, t);
                double wy = evalCameraBezier(by, t);
                double wz = evalCameraBezier(bz, t);
                double wrot = evalCameraBezier(brot, t);
                double wdist = evalCameraBezier(bdist, t);
                double wfov = evalCameraBezier(bfov, t);

                double tx = (static_cast<double>(prevCf.pos[0]) + wx * static_cast<double>(nextCf.pos[0] - prevCf.pos[0])) * scale;
                double ty = (static_cast<double>(prevCf.pos[1]) + wy * static_cast<double>(nextCf.pos[1] - prevCf.pos[1])) * scale;
                double tz = -(static_cast<double>(prevCf.pos[2]) + wz * static_cast<double>(nextCf.pos[2] - prevCf.pos[2])) * scale;

                double rxRad = pRx + wrot * (nRx - pRx);
                double ryRad = pRy + wrot * (nRy - pRy);
                double rzRad = pRz + wrot * (nRz - pRz);

                double camDist = -(pDist + wdist * (nDist - pDist)) * scale;

                double curFov = pFov + wfov * (nFov - pFov);
                double fovRad = (curFov > 0.0) ? (curFov * kDegToRad) : (30.0 * kDegToRad);
                double fl = (apertureMm * 0.5) / std::tan(fovRad * 0.5);

                evalFrames.push_back(f);
                txVec.push_back(tx);
                tyVec.push_back(ty);
                tzVec.push_back(tz);
                rxRadVec.push_back(rxRad);
                ryRadVec.push_back(ryRad);
                rzRadVec.push_back(rzRad);
                distVec.push_back(camDist);
                flVec.push_back(fl);
            }
        }
    }

    unsigned int numSamples = static_cast<unsigned int>(evalFrames.size());
    if (numSamples == 0)
    {
        setResult(0);
        return MS::kSuccess;
    }

    MTimeArray times;
    times.setLength(numSamples);
    MDoubleArray arrTx(numSamples), arrTy(numSamples), arrTz(numSamples);
    MDoubleArray arrRx(numSamples), arrRy(numSamples), arrRz(numSamples);
    MDoubleArray arrDist(numSamples), arrFl(numSamples);

    MTime::Unit uiUnit = MTime::uiUnit();
    for (unsigned int i = 0; i < numSamples; ++i)
    {
        times.set(MTime(static_cast<double>(evalFrames[i]), uiUnit), i);
        arrTx.set(txVec[i], i);
        arrTy.set(tyVec[i], i);
        arrTz.set(tzVec[i], i);
        arrRx.set(rxRadVec[i], i);
        arrRy.set(ryRadVec[i], i);
        arrRz.set(rzRadVec[i], i);
        arrDist.set(distVec[i], i);
        arrFl.set(flVec[i], i);
    }

    injectCurveSmooth(plugAimTx, MFnAnimCurve::kAnimCurveTL, times, arrTx);
    injectCurveSmooth(plugAimTy, MFnAnimCurve::kAnimCurveTL, times, arrTy);
    injectCurveSmooth(plugAimTz, MFnAnimCurve::kAnimCurveTL, times, arrTz);
    injectCurveSmooth(plugAimRx, MFnAnimCurve::kAnimCurveTA, times, arrRx);
    injectCurveSmooth(plugAimRy, MFnAnimCurve::kAnimCurveTA, times, arrRy);
    injectCurveSmooth(plugAimRz, MFnAnimCurve::kAnimCurveTA, times, arrRz);
    injectCurveSmooth(plugCamTz, MFnAnimCurve::kAnimCurveTL, times, arrDist);
    injectCurveSmooth(plugFocal, MFnAnimCurve::kAnimCurveTU, times, arrFl);

    setResult(static_cast<int>(numSamples));
    return MS::kSuccess;
}
