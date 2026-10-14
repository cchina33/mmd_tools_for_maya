#include "mmd_fast_baker_cmd.h"

#include <maya/MGlobal.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnTransform.h>
#include <maya/MPlug.h>
#include <maya/MPlugArray.h>
#include <maya/MTime.h>
#include <maya/MTimeArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MFnAnimCurve.h>
#include <maya/MAngle.h>

const char* MMDFastBakeBoneCmd::kName = "mmdFastBakeBone";

MMDFastBakeBoneCmd::MMDFastBakeBoneCmd()
{
}

MMDFastBakeBoneCmd::~MMDFastBakeBoneCmd()
{
}

void* MMDFastBakeBoneCmd::creator()
{
    return new MMDFastBakeBoneCmd();
}

namespace {

// 特定Plugのアニメーションカーブへ一括キーフレーム注入を行うヘルパー
MStatus applyKeysToPlug(
    MPlug& plug,
    MTimeArray& times,
    MDoubleArray& values,
    MFnAnimCurve::AnimCurveType curveType)
{
    MStatus status;
    MObject animCurveObj = MObject::kNullObj;

    // 既存の接続アニメーションカーブを検出
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

    MFnAnimCurve fnCurve;
    if (animCurveObj.isNull())
    {
        // アニメーションカーブを新規作成してPlugに接続
        animCurveObj = fnCurve.create(plug, curveType, nullptr, &status);
        if (!status)
        {
            return status;
        }
    }
    else
    {
        fnCurve.setObject(animCurveObj);
    }

    // 既存のキーフレームが存在する場合はクリア
    while (fnCurve.numKeys() > 0)
    {
        fnCurve.remove(0);
    }

    // MFnAnimCurve::addKeys により全フレームをネイティブ一括書き込み
    return fnCurve.addKeys(
        &times,
        &values,
        MFnAnimCurve::kTangentLinear,
        MFnAnimCurve::kTangentLinear
    );
}

} // namespace

MStatus MMDFastBakeBoneCmd::doIt(const MArgList& args)
{
    // 引数検証: boneName, frames, tx, ty, tz, rx, ry, rz の8引数
    if (args.length() < 8)
    {
        displayError("mmdFastBakeBone requires 8 arguments: (boneName, frames, tx, ty, tz, rx, ry, rz)");
        return MS::kFailure;
    }

    MStatus status;
    unsigned int idx0 = 0;
    MString boneName = args.asString(idx0, &status);
    if (!status) return status;

    unsigned int idx1 = 1;
    MDoubleArray frames = args.asDoubleArray(idx1, &status);
    if (!status) return status;

    unsigned int idx2 = 2;
    MDoubleArray tx = args.asDoubleArray(idx2, &status);
    if (!status) return status;

    unsigned int idx3 = 3;
    MDoubleArray ty = args.asDoubleArray(idx3, &status);
    if (!status) return status;

    unsigned int idx4 = 4;
    MDoubleArray tz = args.asDoubleArray(idx4, &status);
    if (!status) return status;

    unsigned int idx5 = 5;
    MDoubleArray rx = args.asDoubleArray(idx5, &status);
    if (!status) return status;

    unsigned int idx6 = 6;
    MDoubleArray ry = args.asDoubleArray(idx6, &status);
    if (!status) return status;

    unsigned int idx7 = 7;
    MDoubleArray rz = args.asDoubleArray(idx7, &status);
    if (!status) return status;

    unsigned int numFrames = frames.length();
    if (numFrames == 0)
    {
        return MS::kSuccess;
    }

    // 対象ボーンノードの検索
    MSelectionList selList;
    status = selList.add(boneName);
    if (!status || selList.isEmpty())
    {
        displayError(MString("Target bone node not found: ") + boneName);
        return MS::kFailure;
    }

    MDagPath dagPath;
    status = selList.getDagPath(0, dagPath);
    if (!status)
    {
        displayError(MString("Failed to get DAG path for: ") + boneName);
        return MS::kFailure;
    }

    MFnTransform fnTransform(dagPath, &status);
    if (!status)
    {
        displayError(MString("Target node is not a transform: ") + boneName);
        return MS::kFailure;
    }

    // 時間配列の作成 (MTimeArray)
    MTimeArray timeArray;
    timeArray.setLength(numFrames);
    for (unsigned int i = 0; i < numFrames; ++i)
    {
        timeArray.set(MTime(frames[i], MTime::uiUnit()), i);
    }

    // 各アトリビュートPlugの取得
    MPlug plugTx = fnTransform.findPlug("translateX", true, &status);
    MPlug plugTy = fnTransform.findPlug("translateY", true, &status);
    MPlug plugTz = fnTransform.findPlug("translateZ", true, &status);
    MPlug plugRx = fnTransform.findPlug("rotateX", true, &status);
    MPlug plugRy = fnTransform.findPlug("rotateY", true, &status);
    MPlug plugRz = fnTransform.findPlug("rotateZ", true, &status);

    // 平行移動 (kAnimCurveTL) の一括注入
    if (tx.length() == numFrames && !plugTx.isNull())
    {
        applyKeysToPlug(plugTx, timeArray, tx, MFnAnimCurve::kAnimCurveTL);
    }
    if (ty.length() == numFrames && !plugTy.isNull())
    {
        applyKeysToPlug(plugTy, timeArray, ty, MFnAnimCurve::kAnimCurveTL);
    }
    if (tz.length() == numFrames && !plugTz.isNull())
    {
        applyKeysToPlug(plugTz, timeArray, tz, MFnAnimCurve::kAnimCurveTL);
    }

    // 回転 (kAnimCurveTA: Time to Angular) の一括注入
    // 入力値は度数単位（Degrees）を受け取り、Maya内部単位（Radians）に変換して注入
    MDoubleArray rxAngle(numFrames);
    MDoubleArray ryAngle(numFrames);
    MDoubleArray rzAngle(numFrames);

    for (unsigned int i = 0; i < numFrames; ++i)
    {
        MAngle ax(rx[i], MAngle::kDegrees);
        MAngle ay(ry[i], MAngle::kDegrees);
        MAngle az(rz[i], MAngle::kDegrees);
        rxAngle.set(ax.asUnits(MAngle::kRadians), i);
        ryAngle.set(ay.asUnits(MAngle::kRadians), i);
        rzAngle.set(az.asUnits(MAngle::kRadians), i);
    }

    if (rx.length() == numFrames && !plugRx.isNull())
    {
        applyKeysToPlug(plugRx, timeArray, rxAngle, MFnAnimCurve::kAnimCurveTA);
    }
    if (ry.length() == numFrames && !plugRy.isNull())
    {
        applyKeysToPlug(plugRy, timeArray, ryAngle, MFnAnimCurve::kAnimCurveTA);
    }
    if (rz.length() == numFrames && !plugRz.isNull())
    {
        applyKeysToPlug(plugRz, timeArray, rzAngle, MFnAnimCurve::kAnimCurveTA);
    }

    return MS::kSuccess;
}
