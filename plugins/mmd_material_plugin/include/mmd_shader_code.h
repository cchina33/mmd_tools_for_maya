#ifndef MMD_SHADER_CODE_H
#define MMD_SHADER_CODE_H

// MMDオリジナルマテリアル Viewport 2.0用 DirectX 11 HLSLシェーダーコード埋め込み
// 外部ファイル読み込み失敗を防ぐための内部バッファ定義

static const char* g_mmdShaderHLSL = R"(
cbuffer UpdatePerObject : register(b0)
{
    float4x4 gWorldViewProj : WorldViewProjection;
    float4x4 gWorldView     : WorldView;
    float4x4 gWorld         : World;
    float4x4 gViewInv       : ViewInverse;
};

cbuffer UpdateMaterial : register(b1)
{
    float3 gDiffuseColor;
    float  gDiffuseAlpha;
    float3 gSpecularColor;
    float  gSpecularPower;
    float3 gAmbientColor;
    int    gSphereMode; // 0: なし, 1: 乗算(.sph), 2: 加算(.spa), 3: 減算
    int    gToonMode;   // 0: 無効, 1: MMD標準サンプリング
    bool   gUseColorTexture;
    bool   gUseSphereTexture;
    bool   gUseToonTexture;
};

cbuffer UpdateLights : register(b2)
{
    float3 gLightDir     : Light0Direction < string Object = "Light 0"; string Type = "Direction"; >;
    float4 gLightColor   : Light0Color     < string Object = "Light 0"; string Type = "Color"; >;
    float4 gLightAmbient : Light0Ambient   < string Object = "Light 0"; string Type = "Ambient"; >;
};

// ラスタライザステート（両面描画）
RasterizerState SolidCullNone
{
    CullMode = NONE;
    FillMode = SOLID;
};

// ブレンドステート
BlendState AlphaBlending
{
    BlendEnable[0] = TRUE;
    SrcBlend = SRC_ALPHA;
    DestBlend = INV_SRC_ALPHA;
    BlendOp = ADD;
    SrcBlendAlpha = ONE;
    DestBlendAlpha = ZERO;
    BlendOpAlpha = ADD;
    RenderTargetWriteMask[0] = 0x0F;
};

// テクスチャおよびサンプラー定義
Texture2D gColorTexture
<
    string ResourceName = "";
    string UIName = "Color Texture";
    string ResourceType = "2D";
>;

Texture2D gSphereTexture
<
    string ResourceName = "";
    string UIName = "Sphere Texture";
    string ResourceType = "2D";
>;

Texture2D gToonTexture
<
    string ResourceName = "";
    string UIName = "Toon Texture";
    string ResourceType = "2D";
>;

SamplerState gWrapSampler
{
    Filter = MIN_MAG_MIP_LINEAR;
    AddressU = WRAP;
    AddressV = WRAP;
};

SamplerState gClampSampler
{
    Filter = MIN_MAG_MIP_LINEAR;
    AddressU = CLAMP;
    AddressV = CLAMP;
};

// 頂点シェーダー入出力構造体
struct VS_INPUT
{
    float3 Position : POSITION;
    float3 Normal   : NORMAL;
    float2 UV       : TEXCOORD0;
};

struct PS_INPUT
{
    float4 Position   : SV_Position;
    float3 WorldPos   : POSITION0;
    float3 WorldNormal: NORMAL;
    float3 ViewNormal : TEXCOORD1;
    float2 UV         : TEXCOORD0;
};

// 頂点シェーダー
PS_INPUT VS_Main(VS_INPUT IN)
{
    PS_INPUT OUT;

    float4 pos4 = float4(IN.Position, 1.0f);
    OUT.Position = mul(pos4, gWorldViewProj);
    OUT.WorldPos = mul(pos4, gWorld).xyz;

    // ワールド空間法線の計算
    OUT.WorldNormal = mul(float4(IN.Normal, 0.0f), gWorld).xyz;

    // ビュー空間法線の計算（スフィアマップ用）
    OUT.ViewNormal = mul(float4(IN.Normal, 0.0f), gWorldView).xyz;

    // UV座標（MayaのV軸反転に対応）
    OUT.UV = float2(IN.UV.x, 1.0f - IN.UV.y);

    return OUT;
}

// ピクセルシェーダー
float4 PS_Main(PS_INPUT IN) : SV_Target
{
    // 法線の正規化
    float3 N = normalize(IN.WorldNormal);
    float3 N_view = normalize(IN.ViewNormal);

    // 視線方向の計算（カメラ位置からピクセルへ）
    float3 cameraPos = gViewInv[3].xyz;
    float3 V = normalize(cameraPos - IN.WorldPos);

    // 平行光ベクトルの計算
    float3 L = normalize(-gLightDir);

    // ライト強度の安全策（無効時はデフォルト白光）
    float3 lightCol = gLightColor.rgb;
    if (length(lightCol) < 0.001f)
    {
        lightCol = float3(1.0f, 1.0f, 1.0f);
    }

    // 基本テクスチャカラーのサンプリング
    float4 texColor = float4(1.0f, 1.0f, 1.0f, 1.0f);
    if (gUseColorTexture)
    {
        texColor = gColorTexture.Sample(gWrapSampler, IN.UV);
    }

    // アンビエント合成値
    float3 amb = gAmbientColor + gLightAmbient.rgb;

    // Toonカラーの計算
    float3 toonColor = float3(1.0f, 1.0f, 1.0f);
    float NdotL = dot(N, L);

    if (gUseToonTexture)
    {
        // MMD本家準拠のサンプリング座標計算
        float toonCoordV = 0.5f - 0.5f * NdotL;
        toonCoordV = clamp(toonCoordV, 0.01f, 0.99f);
        toonColor = gToonTexture.Sample(gClampSampler, float2(0.5f, toonCoordV)).rgb;
    }
    else
    {
        // Toonマップ未指定時のフォールバック階調
        float toonStep = smoothstep(-0.05f, 0.05f, NdotL);
        toonColor = lerp(float3(0.5f, 0.5f, 0.5f), float3(1.0f, 1.0f, 1.0f), toonStep);
    }

    // 基本陰影の合成
    float3 baseColor = (gDiffuseColor * texColor.rgb * lightCol) * toonColor + amb;

    // スフィアマップの計算
    if (gUseSphereTexture && gSphereMode > 0)
    {
        // ビュー法線に基づくスフィアUV座標
        float sphereU = 0.5f + 0.5f * N_view.x;
        float sphereV = 0.5f - 0.5f * N_view.y;
        sphereU = clamp(sphereU, 0.001f, 0.999f);
        sphereV = clamp(sphereV, 0.001f, 0.999f);

        float3 sphereColor = gSphereTexture.Sample(gClampSampler, float2(sphereU, sphereV)).rgb;

        // 乗算スフィア (.sph)
        if (gSphereMode == 1)
        {
            baseColor *= sphereColor;
        }
        // 加算スフィア (.spa)
        else if (gSphereMode == 2)
        {
            baseColor += sphereColor;
        }
        // 減算スフィア
        else if (gSphereMode == 3)
        {
            baseColor = max(float3(0.0f, 0.0f, 0.0f), baseColor - (float3(1.0f, 1.0f, 1.0f) - sphereColor));
        }
    }

    // スペキュラ（ハイライト）の計算（Blinn-Phong）
    float3 H = normalize(L + V);
    float NdotH = max(0.0f, dot(N, H));
    float specPower = max(1.0f, gSpecularPower);
    float specFactor = pow(NdotH, specPower);

    // 陰影面ではスペキュラを弱める制御
    if (NdotL <= 0.0f)
    {
        specFactor = 0.0f;
    }

    float3 specColor = gSpecularColor * lightCol * specFactor;

    // 最終カラー合成
    float3 finalRGB = baseColor + specColor;
    float finalAlpha = gDiffuseAlpha * texColor.a;

    return float4(finalRGB, finalAlpha);
}

// テクニック定義
technique11 Main
{
    pass P0
    {
        SetRasterizerState(SolidCullNone);
        SetBlendState(AlphaBlending, float4(0.0f, 0.0f, 0.0f, 0.0f), 0xFFFFFFFF);
        SetVertexShader(CompileShader(vs_5_0, VS_Main()));
        SetPixelShader(CompileShader(ps_5_0, PS_Main()));
    }
}
)";

#endif // MMD_SHADER_CODE_H
