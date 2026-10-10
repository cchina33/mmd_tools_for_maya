// MMDオリジナルマテリアル Viewport 2.0用 DirectX 11 HLSLシェーダー
// MMD (MikuMikuDance) 本家シェーディングモデル完全互換

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
    // MMDエッジ（輪郭線）パラメータ
    bool   gEdgeEnable;
    float4 gEdgeColor;
    float  gEdgeSize;
};

cbuffer UpdateLights : register(b2)
{
    float3 gLightDir     : Light0Direction < string Object = "Light 0"; string Type = "Direction"; >;
    float4 gLightColor   : Light0Color     < string Object = "Light 0"; string Type = "Color"; >;
    float4 gLightAmbient : Light0Ambient   < string Object = "Light 0"; string Type = "Ambient"; >;
};

// ラスタライザステート: パス1用 (裏面カリング / 表面のみ描画)
RasterizerState SolidCullBack
{
    CullMode = BACK;
    FillMode = SOLID;
};

// ラスタライザステート: パス2用 (表面カリング / 裏面のみ描画 / Inverted Hull)
RasterizerState SolidCullFront
{
    CullMode = FRONT;
    FillMode = SOLID;
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
    float4 Color    : COLOR0; // 頂点カラー (mmd_edge_scale: エッジ倍率)
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

    // 基本陰影の合成 (MMD固定機能パイプライン完全互換)
    // テクスチャカラー全体に対し、ディフューズ受光色(Toon含む)と環境光(アンビエント)を乗算
    float3 diffuseTerm = gDiffuseColor * lightCol * toonColor;
    float3 ambientTerm = amb;
    float3 baseColor = texColor.rgb * (diffuseTerm + ambientTerm);

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

// MMDエッジ専用 頂点シェーダー出力構造体
struct PS_EDGE_INPUT
{
    float4 Position : SV_Position;
};

// MMDエッジ専用 頂点シェーダー (反転法線押し出し / Inverted Hull)
PS_EDGE_INPUT VS_Edge(VS_INPUT IN)
{
    PS_EDGE_INPUT OUT;

    // エッジ無効またはサイズ0の場合は無効化
    if (!gEdgeEnable || gEdgeSize <= 0.0f)
    {
        OUT.Position = float4(0.0f, 0.0f, 0.0f, 0.0f);
        return OUT;
    }

    // 頂点ごとのエッジ倍率 (mmd_edge_scale のR値。未設定時はデフォルト 1.0)
    float vertexEdgeScale = IN.Color.r;
    if (IN.Color.a == 0.0f && length(IN.Color.rgb) == 0.0f)
    {
        vertexEdgeScale = 1.0f;
    }

    // 頂点倍率が0.0の場合は押し出しなし
    if (vertexEdgeScale <= 0.0f)
    {
        OUT.Position = float4(0.0f, 0.0f, 0.0f, 0.0f);
        return OUT;
    }

    // 実効押し出し量の算出: Offset = MaterialEdgeSize * VertexEdgeScale * BaseScale
    const float baseScale = 0.0015f;
    float offset = gEdgeSize * vertexEdgeScale * baseScale;

    // クリップ空間座標およびクリップ空間法線の計算
    float4 clipPos = mul(float4(IN.Position, 1.0f), gWorldViewProj);
    float4 clipNormal = mul(float4(IN.Normal, 0.0f), gWorldViewProj);

    // クリップ空間でのパースペクティブ補正押し出し (ClipPosition.w を掛けて画面上のピクセル太さを一定保持)
    float2 norm2D = normalize(clipNormal.xy);
    clipPos.xy += norm2D * offset * clipPos.w;

    OUT.Position = clipPos;
    return OUT;
}

// MMDエッジ専用 ピクセルシェーダー (ライティングなしのPMXエッジ色単色出力)
float4 PS_Edge(PS_EDGE_INPUT IN) : SV_Target
{
    if (!gEdgeEnable)
    {
        discard;
    }
    return gEdgeColor;
}

// MMD Viewport 2.0 統合テクニック (Inverted Hull 2パス構成)
technique11 Main
{
    // パス1: メッシュ本体の通常描画 (裏面カリングで表面のみ描画)
    pass P_Surface
    {
        SetRasterizerState(SolidCullBack);
        SetBlendState(AlphaBlending, float4(0.0f, 0.0f, 0.0f, 0.0f), 0xFFFFFFFF);
        SetVertexShader(CompileShader(vs_5_0, VS_Main()));
        SetPixelShader(CompileShader(ps_5_0, PS_Main()));
    }

    // パス2: エッジ専用描画 (表面カリングで裏面のみ描画 / Inverted Hull)
    pass P_Edge
    {
        SetRasterizerState(SolidCullFront);
        SetBlendState(AlphaBlending, float4(0.0f, 0.0f, 0.0f, 0.0f), 0xFFFFFFFF);
        SetVertexShader(CompileShader(vs_5_0, VS_Edge()));
        SetPixelShader(CompileShader(ps_5_0, PS_Edge()));
    }
}
