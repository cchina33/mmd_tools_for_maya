#ifndef MMD_RENDER_CMD_H
#define MMD_RENDER_CMD_H

#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MArgDatabase.h>
#include <maya/MString.h>

// MMD独自レンダラーのRender Viewブリッジコマンド (mmdRender)
// オフスクリーンレンダーターゲットの描画結果を取得し、MRenderViewへ劣化なく転送する
class MMDRenderCmd : public MPxCommand
{
public:
    MMDRenderCmd();
    virtual ~MMDRenderCmd() override;

    static void* creator();
    static MSyntax newSyntax();

    virtual MStatus doIt(const MArgList& args) override;

    static const char* kCommandName;

private:
    MStatus parseArgs(const MArgList& args);

    unsigned int mWidth;
    unsigned int mHeight;
    MString mCameraName;
    bool mBatchMode;
};

#endif // MMD_RENDER_CMD_H

