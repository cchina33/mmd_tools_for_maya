#ifndef MMD_TOON_SHADER_CODE_H
#define MMD_TOON_SHADER_CODE_H

// Viewport 2.0 (OpenGL Core Profile / DirectX 11) 用 OGSFX シェーダーコード
// 参照実装の解析式に基づく正確なライティング、Toon補間、セルフシャドウ統合

static const char* g_mmdToonOGSFX = R"(
#version 330

// --- ユニフォームバッファ定義 ---
uniform mat4 gWorldViewProj : WorldViewProjection;
uniform mat4 gWorldView     : WorldView;
uniform mat4 gWorld         : World;
uniform mat4 gViewInv       : ViewInverse;
uniform mat4 gShadowViewProj : ShadowViewProjection;

// マテリアル定数
uniform vec3  gDiffuseColor  = vec3(0.8, 0.8, 0.8);
uniform float gDiffuseAlpha  = 1.0;
uniform vec3  gAmbientColor  = vec3(0.0, 0.0, 0.0);
uniform vec3  gSpecularColor = vec3(0.0, 0.0, 0.0);
uniform float gSpecularPower = 5.0;
uniform vec3  gTransparency  = vec3(0.0, 0.0, 0.0);

uniform int   gSphereMode     = 0; // 0:なし, 1:乗算, 2:加算
uniform int   gToonMode       = 1; // 0:無効, 1:MMD標準
uniform int   gLightMode      = 1; // 0:Maya直接, 1:MMD基準輝度換算
uniform bool  gShadowEnabled  = true;
uniform float gShadowBias     = 0.001;

// ライトパラメータ
uniform vec3  gLightDir      : Light0Direction = vec3(0.0, -1.0, 0.0);
uniform vec4  gLightColor    : Light0Color     = vec4(1.0, 1.0, 1.0, 1.0);
uniform vec4  gLightAmbient  : Light0Ambient   = vec4(0.2, 0.2, 0.2, 1.0);
uniform float gLightIntensity: Light0Intensity = 1.0;

// テクスチャおよびサンプラー
uniform texture2D gColorTex;
uniform sampler2D gColorSampler = sampler_state {
    Texture = <gColorTex>;
    WrapS = ClampToEdge;
    WrapT = ClampToEdge;
};

uniform texture2D gSphereTex;
uniform sampler2D gSphereSampler = sampler_state {
    Texture = <gSphereTex>;
    WrapS = ClampToEdge;
    WrapT = ClampToEdge;
};

uniform texture2D gToonTex;
uniform sampler2D gToonSampler = sampler_state {
    Texture = <gToonTex>;
    WrapS = ClampToEdge;
    WrapT = ClampToEdge;
};

uniform texture2D gShadowMapTex;
uniform sampler2D gShadowSampler = sampler_state {
    Texture = <gShadowMapTex>;
    WrapS = ClampToEdge;
    WrapT = ClampToEdge;
};

// 頂点シェーダー入力
attribute attributeIn {
    vec3 position : POSITION;
    vec3 normal   : NORMAL;
    vec2 uv       : TEXCOORD0;
};

// 頂点シェーダー出力 / フラグメント入力
attribute vertexOut {
    vec3 vWorldPos;
    vec3 vWorldNormal;
    vec3 vViewNormal;
    vec2 vUV;
    vec2 vSphereUV;
    vec4 vShadowCoord;
};

// 頂点シェーダー
GLSLShader VS {
    void main() {
        gl_Position = gWorldViewProj * vec4(position, 1.0);
        vWorldPos = (gWorld * vec4(position, 1.0)).xyz;
        vWorldNormal = normalize((gWorld * vec4(normal, 0.0)).xyz);
        vViewNormal = normalize((gWorldView * vec4(normal, 0.0)).xyz);
        vUV = uv;

        // スフィアマップ用UV算出 (視線空間法線 X, Y のリマップ)
        vSphereUV = vec2(vViewNormal.x * 0.5 + 0.5, vViewNormal.y * -0.5 + 0.5);

        // シャドウ射影座標算出
        vShadowCoord = gShadowViewProj * vec4(vWorldPos, 1.0);
    }
}

// フラグメントシェーダー
GLSLShader PS {
    out vec4 outFragColor;

    void main() {
        // メインカラーテクスチャの取得
        vec4 texCol = texture(gColorSampler, vUV);

        // 法線および視線ベクトルの正規化
        vec3 N = normalize(vWorldNormal);
        vec3 V = normalize(gViewInv[3].xyz - vWorldPos);
        vec3 L = normalize(gLightDir);

        // ライトカラーと環境光の評価 (MMD基準輝度モード時は換算)
        vec3 lCol = gLightColor.rgb * gLightIntensity;
        if (gLightMode == 1) {
            // MMD初期ライト輝度 (154/255 ≒ 0.604) を基準として適正スケール
            lCol = min(lCol, vec3(0.604));
        }
        vec3 lAmb = gLightAmbient.rgb;

        // 基本受光色 (EgColor) の事前飽和クランプ (白飛びの徹底抑止)
        vec3 egColor = clamp(gDiffuseColor * lCol + gAmbientColor * lCol + gAmbientColor * lAmb, 0.0, 1.0);
        vec3 baseColor = egColor * texCol.rgb;

        // トゥーン受光係数 (comp_toon) の計算
        float nDotL = max(dot(N, -L), 0.0);
        float compToon = clamp(nDotL * 3.0, 0.0, 1.0);

        // トゥーン最暗色 (最下端) のサンプリング
        vec4 toonDark = texture(gToonSampler, vec2(0.5, 0.05));

        // セルフシャドウ遮蔽率 (comp_shadow) の判定
        float compShadow = 1.0;
        if (gShadowEnabled) {
            vec3 proj = vShadowCoord.xyz / vShadowCoord.w;
            proj = proj * 0.5 + 0.5;
            if (proj.x >= 0.0 && proj.x <= 1.0 && proj.y >= 0.0 && proj.y <= 1.0 && proj.z >= 0.0 && proj.z <= 1.0) {
                float shadowDepth = texture(gShadowSampler, proj.xy).r;
                float currentDepth = proj.z - gShadowBias;
                float diff = max(currentDepth - shadowDepth, 0.0);
                compShadow = 1.0 - clamp(diff * 1500.0 - 0.3, 0.0, 1.0);
            }
        }

        // トゥーンとセルフシャドウの統合補間 (最小値を採用し二重影による黒濁りを抑止)
        float comp = (gToonMode == 1) ? min(compToon, compShadow) : compShadow;

        // トゥーン陰影カラーの合成 (影領域では基本色がトゥーン最暗色に綺麗に置き換わる)
        vec3 blendedColor = baseColor * (comp + toonDark.rgb * (1.0 - comp));

        // スペキュラハイライト (影領域では comp により自然に消滅)
        vec3 H = normalize(-L + V);
        float nDotH = max(dot(N, H), 0.0);
        vec3 specular = gSpecularColor * pow(nDotH, max(gSpecularPower, 1.0)) * comp;
        vec3 finalRgb = blendedColor + specular;

        // スフィアマップの合成
        if (gSphereMode == 1) { // 乗算 (.sph)
            vec4 sphCol = texture(gSphereSampler, vSphereUV);
            finalRgb *= sphCol.rgb;
        } else if (gSphereMode == 2) { // 加算 (.spa)
            vec4 sphCol = texture(gSphereSampler, vSphereUV);
            finalRgb += sphCol.rgb;
        }

        // 最終透過度
        float finalAlpha = texCol.a * gDiffuseAlpha * (1.0 - gTransparency.r);

        outFragColor = vec4(finalRgb, finalAlpha);
    }
}

// テクニック定義
technique Main {
    pass P0 {
        VertexShader (in attributeIn, out vertexOut) = VS;
        PixelShader (in vertexOut, out fragmentOut) = PS;
    }
}
)";

#endif // MMD_TOON_SHADER_CODE_H
