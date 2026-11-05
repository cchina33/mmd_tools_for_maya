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
    DepthBias = 500;
    SlopeScaledDepthBias = 1.2f;
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
    OUT.VtxColor = IN.Color;

    float vtxScale = (IN.Color.g > 0.5f) ? IN.Color.r : 1.0f;
    if (vtxScale <= 0.0f || gEdgeSize <= 0.0f || IN.Color.a <= 0.05f)
    {
        OUT.Position = float4(0.0f, 0.0f, -2.0f, 1.0f);
        return OUT;
    }

    float4 viewPos    = mul(float4(IN.Position, 1.0f), gWorldView);
    float3 viewNormal = normalize(mul(float4(IN.Normal, 0.0f), gWorldView).xyz);

    float px         = gEdgeSize * vtxScale;
    float depth      = max(abs(viewPos.z), 0.1f);
    float unitDepth  = (gProj._m33 > 0.5f) ? 1.0f : depth;
    float projY      = max(abs(gProj._m11), 0.001f);
    float worldPerPx = 2.0f * unitDepth / (max(gScreenSize.y, 1.0f) * projY);

    viewPos.xy += viewNormal.xy * (px * worldPerPx);
    viewPos.z  -= px * worldPerPx * 0.4f;

    float4 clipPos = mul(viewPos, gProj);
    // クリップ空間での微小深度オフセット (奥方向へ押し出し表面との競合を防止)
    clipPos.z += 0.0008f * clipPos.w;
    OUT.Position = clipPos;
    return OUT;
}

float4 PS_Edge(PS_EDGE_INPUT IN, bool isFront : SV_IsFrontFace) : SV_Target
{
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
        VS_OUT.vVtxColor = edgeScale;

        float vtxScale = (edgeScale.g > 0.5) ? edgeScale.r : 1.0;
        if (vtxScale <= 0.0 || gEdgeSize <= 0.0 || edgeScale.a <= 0.05) {
            gl_Position = vec4(0.0, 0.0, -2.0, 1.0);
            return;
        }

        vec4 viewPos    = gWorldView * vec4(position, 1.0);
        vec3 viewNormal = normalize((gWorldView * vec4(normal, 0.0)).xyz);

        float px         = gEdgeSize * vtxScale;
        float depth      = max(abs(viewPos.z), 0.1);
        float unitDepth  = (gProj[3][3] > 0.5) ? 1.0 : depth;
        float projY      = max(abs(gProj[1][1]), 0.001);
        float worldPerPx = 2.0 * unitDepth / (max(gScreenSize.y, 1.0) * projY);

        viewPos.xy += viewNormal.xy * (px * worldPerPx);
        viewPos.z  -= px * worldPerPx * 0.4;

        vec4 clipPos = gProj * viewPos;
        // クリップ空間での微小深度オフセット (奥方向へ押し出し表面との競合を防止)
        clipPos.z += 0.0008 * clipPos.w;
        gl_Position = clipPos;
    }
}

GLSLShader PS_Edge {
    void main() {
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
