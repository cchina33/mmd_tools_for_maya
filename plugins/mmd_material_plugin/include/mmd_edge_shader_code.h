#ifndef MMD_EDGE_SHADER_CODE_H
#define MMD_EDGE_SHADER_CODE_H

// ============================================================================
// MMD edge (inverted hull) shaders used as a shaderOverride of MSceneRender.
//
//  - Width is specified in PIXELS (gEdgeSize * per-vertex scale), independent
//    of FOV / distance. Works for perspective and orthographic cameras.
//  - View-space normal xy is used WITHOUT normalization, so faces pointing at
//    the camera are not pushed out; only silhouette parts grow.
//  - The hull is pushed away from the camera a little (Maya looks down -Z).
//  - Per-vertex scale encoding in COLOR0 (color set "mmd_edge_scale"):
//        g > 0.5 : baked.  r = scale (0 = no edge for this vertex)
//        g <= 0.5: not baked / stream missing -> scale 1.0
//  - gEdgeDebug = 1 : draw the vertex color instead of the edge color.
//                     (black rim = COLOR0 stream is NOT delivered)
// ============================================================================

// ----------------------------------------------------------------------------
// DirectX 11
// ----------------------------------------------------------------------------
static const char* g_mmdEdgeShaderHLSL = R"EDGE(
cbuffer UpdatePerObject : register(b0)
{
    float4x4 gWorldView  : WorldView;
    float4x4 gProj       : Projection;
    float2   gScreenSize : ViewportPixelSize;
};

cbuffer UpdateEdgeMaterial : register(b1)
{
    float4 gEdgeColor;
    float  gEdgeSize;
    int    gEdgeDebug;
};

RasterizerState EdgeRaster
{
    CullMode = FRONT;
    FillMode = SOLID;
    FrontCounterClockwise = TRUE;
    DepthBias = 50;
    SlopeScaledDepthBias = 1.0f;
};

DepthStencilState EdgeDepth
{
    DepthEnable = TRUE;
    DepthWriteMask = ALL;
    DepthFunc = LESS_EQUAL;
};

BlendState EdgeBlend
{
    BlendEnable[0] = FALSE;
    RenderTargetWriteMask[0] = 0x0F;
};

struct VS_INPUT
{
    float3 Position : POSITION;
    float3 Normal   : NORMAL;
    float4 Color    : COLOR0;
};

struct PS_EDGE_INPUT
{
    float4 Position : SV_Position;
    float4 VtxColor : TEXCOORD0;
};

PS_EDGE_INPUT VS_Edge(VS_INPUT IN)
{
    PS_EDGE_INPUT OUT;

    float vtxScale = (IN.Color.g > 0.5f) ? IN.Color.r : 1.0f;
    bool isActive = (vtxScale > 0.001f && gEdgeSize > 0.001f && IN.Color.a > 0.05f);
    OUT.VtxColor = isActive ? float4(vtxScale, 1.0f, 0.0f, 1.0f) : float4(0.0f, 1.0f, 0.0f, 0.0f);

    float4 viewPos    = mul(float4(IN.Position, 1.0f), gWorldView);
    float3 viewNormal = normalize(mul(float4(IN.Normal, 0.0f), gWorldView).xyz);

    float px         = isActive ? (gEdgeSize * vtxScale) : 0.0f;
    float depth      = max(abs(viewPos.z), 0.1f);
    float unitDepth  = (gProj._m33 > 0.5f) ? 1.0f : depth;
    float projY      = max(abs(gProj._m11), 0.001f);
    float worldPerPx = 2.0f * unitDepth / (max(gScreenSize.y, 1.0f) * projY);

    viewPos.xy += viewNormal.xy * (px * worldPerPx);
    // ビュースペースでの微小深度オフセット (カメラ距離に比例させ遠距離でのFarクリップ消失を防止)
    viewPos.z  -= px * worldPerPx * 0.5f;

    float4 clipPos = mul(viewPos, gProj);
    OUT.Position = clipPos;
    return OUT;
}

float4 PS_Edge(PS_EDGE_INPUT IN, bool isFront : SV_IsFrontFace) : SV_Target
{
    if (IN.VtxColor.a < 0.99f || IN.VtxColor.r <= 0.001f || gEdgeSize <= 0.001f)
    {
        discard;
    }
    if (gEdgeDebug == 1)
    {
        return float4(IN.VtxColor.rgb, 1.0f);
    }
    if (isFront)
    {
        discard;
    }
    return float4(gEdgeColor.rgb, 1.0f);
}

technique11 Main
{
    pass P_Edge
    {
        SetRasterizerState(EdgeRaster);
        SetBlendState(EdgeBlend, float4(0.0f, 0.0f, 0.0f, 0.0f), 0xFFFFFFFF);
        SetDepthStencilState(EdgeDepth, 0);
        SetVertexShader(CompileShader(vs_5_0, VS_Edge()));
        SetPixelShader(CompileShader(ps_5_0, PS_Edge()));
    }
}
)EDGE";

// ----------------------------------------------------------------------------
// OpenGL Core Profile (OGSFX)
// ----------------------------------------------------------------------------
static const char* g_mmdEdgeShaderOGSFX = R"EDGE(#version 330

uniform mat4 gWorldView  : WorldView;
uniform mat4 gProj       : Projection;
uniform vec2 gScreenSize : ViewportPixelSize;

uniform vec4  gEdgeColor;
uniform float gEdgeSize;
uniform int   gEdgeDebug;

attribute attributeIn {
    vec3 position  : POSITION;
    vec3 normal    : NORMAL;
    vec4 edgeScale : COLOR0;
};

attribute vertexOutEdge {
    vec4 vVtxColor;
};

attribute fragmentOut {
    vec4 outFragColor : COLOR0;
};

GLSLShader VS_Edge {
    void main() {
        float vtxScale = (edgeScale.g > 0.5) ? edgeScale.r : 1.0;
        bool isActive = (vtxScale > 0.001 && gEdgeSize > 0.001 && edgeScale.a > 0.05);
        VS_OUT.vVtxColor = isActive ? vec4(vtxScale, 1.0, 0.0, 1.0) : vec4(0.0, 1.0, 0.0, 0.0);

        vec4 viewPos    = gWorldView * vec4(position, 1.0);
        vec3 viewNormal = normalize((gWorldView * vec4(normal, 0.0)).xyz);

        float px         = isActive ? (gEdgeSize * vtxScale) : 0.0;
        float depth      = max(abs(viewPos.z), 0.1);
        float unitDepth  = (gProj[3][3] > 0.5) ? 1.0 : depth;
        float projY      = max(abs(gProj[1][1]), 0.001);
        float worldPerPx = 2.0 * unitDepth / (max(gScreenSize.y, 1.0) * projY);

        viewPos.xy += viewNormal.xy * (px * worldPerPx);
        // ビュースペースでの微小深度オフセット (カメラ距離に比例させ遠距離でのFarクリップ消失を防止)
        viewPos.z  -= px * worldPerPx * 0.5;

        vec4 clipPos = gProj * viewPos;
        gl_Position = clipPos;
    }
}

GLSLShader PS_Edge {
    void main() {
        if (PS_IN.vVtxColor.a < 0.99 || PS_IN.vVtxColor.r <= 0.001 || gEdgeSize <= 0.001) {
            discard;
        }
        if (gEdgeDebug == 1) {
            outFragColor = vec4(PS_IN.vVtxColor.rgb, 1.0);
            return;
        }
        if (gl_FrontFacing) {
            discard;
        }
        outFragColor = vec4(gEdgeColor.rgb, 1.0);
    }
}

technique Main {
    pass P_Edge {
        VertexShader (in attributeIn, out vertexOutEdge VS_OUT) = VS_Edge;
        PixelShader  (in vertexOutEdge PS_IN, out fragmentOut)  = PS_Edge;
    }
}
)EDGE";

#endif // MMD_EDGE_SHADER_CODE_H
