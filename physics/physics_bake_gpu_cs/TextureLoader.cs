using System;
using System.Collections.Generic;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Media.Media3D;
using MmdPhysicsBridge;

namespace PhysicsSimulationBakeViewer
{
    /// <summary>
    /// PMXモデルのテクスチャ読み込み、パス解決、およびWPF 3Dマテリアル生成を行うヘルパークラス
    /// </summary>
    public static class TextureLoader
    {
        // 読み込み済みテクスチャブラシのキャッシュ（フルパス -> Brush）
        private static readonly Dictionary<string, ImageBrush> _textureCache = new(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// キャッシュをクリアします。
        /// </summary>
        public static void ClearCache()
        {
            _textureCache.Clear();
        }

        /// <summary>
        /// PMXファイル配置ディレクトリを基準にテクスチャファイルの絶対パスを解決します。
        /// </summary>
        public static string? ResolveTexturePath(string modelDirectory, string rawTexturePath)
        {
            if (string.IsNullOrWhiteSpace(rawTexturePath)) return null;

            // スフィアマップ複合指定 (例: "body.png*body.sph") の場合、メインテクスチャを抽出
            string mainPath = rawTexturePath;
            if (mainPath.Contains('*'))
            {
                var parts = mainPath.Split('*');
                mainPath = parts[0].Trim();
            }

            if (string.IsNullOrWhiteSpace(mainPath)) return null;

            // URLエンコードの解除 (多言語パス対応)
            try
            {
                mainPath = Uri.UnescapeDataString(mainPath);
            }
            catch
            {
                // デコードに失敗した場合はそのまま使用
            }

            // Unicode正規化 (NFD -> NFC 結合文字列の統一)
            mainPath = mainPath.Normalize(System.Text.NormalizationForm.FormC);

            // スフィアマップ (*.sph, *.spa) は単独指定の場合は除外
            string ext = Path.GetExtension(mainPath).ToLowerInvariant();
            if (ext == ".sph" || ext == ".spa") return null;

            // パス区切り文字の正規化
            mainPath = mainPath.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);

            // フルパスの合成
            string combinedPath = Path.IsPathRooted(mainPath)
                ? mainPath
                : Path.Combine(modelDirectory, mainPath);

            if (File.Exists(combinedPath))
            {
                return Path.GetFullPath(combinedPath);
            }

            // 大文字・小文字の不一致や相対ディレクトリのフォールバック探索
            string? fileName = Path.GetFileName(mainPath);
            if (!string.IsNullOrEmpty(fileName))
            {
                // 同一ディレクトリ内の同名ファイル探索
                string dir = Path.GetDirectoryName(combinedPath) ?? modelDirectory;
                if (Directory.Exists(dir))
                {
                    foreach (var f in Directory.GetFiles(dir))
                    {
                        if (string.Equals(Path.GetFileName(f), fileName, StringComparison.OrdinalIgnoreCase))
                        {
                            return Path.GetFullPath(f);
                        }
                    }
                }

                // モデルディレクトリ直下の探索
                if (Directory.Exists(modelDirectory))
                {
                    foreach (var f in Directory.GetFiles(modelDirectory))
                    {
                        if (string.Equals(Path.GetFileName(f), fileName, StringComparison.OrdinalIgnoreCase))
                        {
                            return Path.GetFullPath(f);
                        }
                    }
                }

                // 拡張子を変更して再検索 (.tga -> .png / .bmp / .jpg)
                string baseNameNoExt = Path.GetFileNameWithoutExtension(fileName);
                string[] testExts = { ".png", ".bmp", ".jpg", ".tga" };
                string searchDir = Directory.Exists(dir) ? dir : modelDirectory;
                if (Directory.Exists(searchDir))
                {
                    foreach (var te in testExts)
                    {
                        string testP = Path.Combine(searchDir, baseNameNoExt + te);
                        if (File.Exists(testP)) return Path.GetFullPath(testP);
                    }
                }

                // モデルディレクトリ配下の全サブディレクトリを再帰検索 (階層ズレの吸収)
                if (Directory.Exists(modelDirectory))
                {
                    try
                    {
                        foreach (var f in Directory.GetFiles(modelDirectory, "*.*", SearchOption.AllDirectories))
                        {
                            string curName = Path.GetFileName(f);
                            if (string.Equals(curName, fileName, StringComparison.OrdinalIgnoreCase))
                            {
                                return Path.GetFullPath(f);
                            }
                            if (string.Equals(Path.GetFileNameWithoutExtension(curName), baseNameNoExt, StringComparison.OrdinalIgnoreCase))
                            {
                                string curExt = Path.GetExtension(f).ToLowerInvariant();
                                if (testExts.Contains(curExt))
                                {
                                    return Path.GetFullPath(f);
                                }
                            }
                        }
                    }
                    catch
                    {
                        // アクセス権限等によるスキップ
                    }
                }
            }

            return null;
        }

        /// <summary>
        /// 指定された画像ファイルからWPF ImageBrushを読み込みます。
        /// </summary>
        public static ImageBrush? LoadTextureBrush(string filePath)
        {
            if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
            {
                return null;
            }

            string fullPath = Path.GetFullPath(filePath);
            if (_textureCache.TryGetValue(fullPath, out var cachedBrush))
            {
                return cachedBrush;
            }

            try
            {
                BitmapSource? bitmapSource = null;
                string ext = Path.GetExtension(fullPath).ToLowerInvariant();

                if (ext == ".tga")
                {
                    bitmapSource = LoadTga(fullPath);
                }
                else
                {
                    // 標準形式 (png, jpg, bmp, gif, tiff, spa, sph)
                    bitmapSource = LoadStandardImage(fullPath);
                }

                if (bitmapSource != null)
                {
                    // physics_bridge_cs と同様に Absolute (0,0,1,1) マッピングを指定し、頂点UV座標を正しく反映
                    var brush = new ImageBrush(bitmapSource)
                    {
                        TileMode = TileMode.Tile,
                        ViewportUnits = BrushMappingMode.Absolute,
                        Viewport = new Rect(0, 0, 1, 1)
                    };
                    brush.Freeze();
                    _textureCache[fullPath] = brush;
                    return brush;
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[TextureLoader] テクスチャ読み込み例外 ({filePath}): {ex.Message}");
            }

            return null;
        }

        /// <summary>
        /// 標準的な画像フォーマット（PNG/JPEG/BMP等）をメモリストリーム経由で読み込みます。
        /// </summary>
        private static BitmapSource? LoadStandardImage(string filePath)
        {
            try
            {
                byte[] bytes = File.ReadAllBytes(filePath);
                using var ms = new MemoryStream(bytes);
                var decoder = BitmapDecoder.Create(ms, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
                if (decoder.Frames.Count > 0)
                {
                    var frame = decoder.Frames[0];
                    var bitmap = new WriteableBitmap(frame);
                    bitmap.Freeze();
                    return bitmap;
                }
            }
            catch
            {
                // フォールバック: 通常のBitmapImage
                try
                {
                    var bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.UriSource = new Uri(filePath, UriKind.Absolute);
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.EndInit();
                    bmp.Freeze();
                    return bmp;
                }
                catch
                {
                    return null;
                }
            }
            return null;
        }

        /// <summary>
        /// TGA (Truevision Targa) 画像ファイルをデコードして BitmapSource を生成します。
        /// </summary>
        public static BitmapSource? LoadTga(string filePath)
        {
            try
            {
                byte[] data = File.ReadAllBytes(filePath);
                if (data.Length < 18) return null;

                int idLength = data[0];
                int imageType = data[2]; // 2: 非圧縮True-color, 10: RLE圧縮True-color, 3: グレースケール, 11: RLEグレースケール
                int width = data[12] | (data[13] << 8);
                int height = data[14] | (data[15] << 8);
                int bpp = data[16]; // bits per pixel (24 または 32)
                byte descriptor = data[17];
                bool isTopDown = (descriptor & 0x20) != 0;

                if (width <= 0 || height <= 0) return null;
                if (imageType != 2 && imageType != 10 && imageType != 3 && imageType != 11) return null;

                int bytesPerPixel = bpp / 8;
                if (bytesPerPixel != 3 && bytesPerPixel != 4 && bytesPerPixel != 1) return null;

                int offset = 18 + idLength;
                int pixelCount = width * height;
                byte[] bgraPixels = new byte[pixelCount * 4];

                if (imageType == 2 || imageType == 3)
                {
                    // 非圧縮読み込み
                    int srcStride = width * bytesPerPixel;
                    for (int y = 0; y < height; y++)
                    {
                        int targetY = isTopDown ? y : (height - 1 - y);
                        int rowSrc = offset + (y * srcStride);
                        int rowDst = targetY * width * 4;

                        for (int x = 0; x < width; x++)
                        {
                            int pSrc = rowSrc + (x * bytesPerPixel);
                            int pDst = rowDst + (x * 4);

                            if (bytesPerPixel == 4)
                            {
                                bgraPixels[pDst + 0] = data[pSrc + 0]; // B
                                bgraPixels[pDst + 1] = data[pSrc + 1]; // G
                                bgraPixels[pDst + 2] = data[pSrc + 2]; // R
                                bgraPixels[pDst + 3] = data[pSrc + 3]; // A
                            }
                            else if (bytesPerPixel == 3)
                            {
                                bgraPixels[pDst + 0] = data[pSrc + 0]; // B
                                bgraPixels[pDst + 1] = data[pSrc + 1]; // G
                                bgraPixels[pDst + 2] = data[pSrc + 2]; // R
                                bgraPixels[pDst + 3] = 255;            // A
                            }
                            else
                            {
                                byte gray = data[pSrc];
                                bgraPixels[pDst + 0] = gray;
                                bgraPixels[pDst + 1] = gray;
                                bgraPixels[pDst + 2] = gray;
                                bgraPixels[pDst + 3] = 255;
                            }
                        }
                    }
                }
                else if (imageType == 10 || imageType == 11)
                {
                    // RLE圧縮読み込み
                    byte[] rawDecoded = new byte[pixelCount * bytesPerPixel];
                    int decodedPixels = 0;
                    int cur = offset;

                    while (decodedPixels < pixelCount && cur < data.Length)
                    {
                        byte packetHeader = data[cur++];
                        int count = (packetHeader & 0x7F) + 1;

                        if ((packetHeader & 0x80) != 0)
                        {
                            // ランレングスパケット
                            byte[] pixel = new byte[bytesPerPixel];
                            for (int i = 0; i < bytesPerPixel && cur < data.Length; i++)
                            {
                                pixel[i] = data[cur++];
                            }
                            for (int i = 0; i < count && decodedPixels < pixelCount; i++)
                            {
                                int dstIdx = decodedPixels * bytesPerPixel;
                                for (int b = 0; b < bytesPerPixel; b++)
                                {
                                    rawDecoded[dstIdx + b] = pixel[b];
                                }
                                decodedPixels++;
                            }
                        }
                        else
                        {
                            // Rawパケット
                            for (int i = 0; i < count && decodedPixels < pixelCount && cur + bytesPerPixel <= data.Length; i++)
                            {
                                int dstIdx = decodedPixels * bytesPerPixel;
                                for (int b = 0; b < bytesPerPixel; b++)
                                {
                                    rawDecoded[dstIdx + b] = data[cur++];
                                }
                                decodedPixels++;
                            }
                        }
                    }

                    // ピクセル並び替え（下から上 -> 上から下への反転処理を含む）
                    for (int y = 0; y < height; y++)
                    {
                        int targetY = isTopDown ? y : (height - 1 - y);
                        int rowSrc = y * width * bytesPerPixel;
                        int rowDst = targetY * width * 4;

                        for (int x = 0; x < width; x++)
                        {
                            int pSrc = rowSrc + (x * bytesPerPixel);
                            int pDst = rowDst + (x * 4);

                            if (bytesPerPixel == 4)
                            {
                                bgraPixels[pDst + 0] = rawDecoded[pSrc + 0];
                                bgraPixels[pDst + 1] = rawDecoded[pSrc + 1];
                                bgraPixels[pDst + 2] = rawDecoded[pSrc + 2];
                                bgraPixels[pDst + 3] = rawDecoded[pSrc + 3];
                            }
                            else if (bytesPerPixel == 3)
                            {
                                bgraPixels[pDst + 0] = rawDecoded[pSrc + 0];
                                bgraPixels[pDst + 1] = rawDecoded[pSrc + 1];
                                bgraPixels[pDst + 2] = rawDecoded[pSrc + 2];
                                bgraPixels[pDst + 3] = 255;
                            }
                            else
                            {
                                byte gray = rawDecoded[pSrc];
                                bgraPixels[pDst + 0] = gray;
                                bgraPixels[pDst + 1] = gray;
                                bgraPixels[pDst + 2] = gray;
                                bgraPixels[pDst + 3] = 255;
                            }
                        }
                    }
                }

                int stride = width * 4;
                var bs = BitmapSource.Create(width, height, 96, 96, PixelFormats.Bgra32, null, bgraPixels, stride);
                bs.Freeze();
                return bs;
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[TextureLoader] TGA読み込み例外 ({filePath}): {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// PMXマテリアル情報および解決済みテクスチャからWPF 3Dマテリアル（MaterialGroup）を構築します。
        /// </summary>
        public static Material CreateMmdMaterial(PmxMaterial mat, string? resolvedTexturePath, bool isTransparent = false)
        {
            ImageBrush? texBrush = null;
            if (!string.IsNullOrWhiteSpace(resolvedTexturePath))
            {
                texBrush = LoadTextureBrush(resolvedTexturePath);
            }

            if (texBrush != null)
            {
                if (isTransparent && mat.Diffuse[3] < 0.95f)
                {
                    if (mat.Diffuse[3] <= 0.01f)
                    {
                        var transparentBrush = new SolidColorBrush(Colors.Transparent);
                        transparentBrush.Freeze();
                        return new DiffuseMaterial(transparentBrush);
                    }
                    var cloneBrush = texBrush.Clone();
                    cloneBrush.Opacity = mat.Diffuse[3];
                    cloneBrush.Freeze();
                    return new DiffuseMaterial(cloneBrush);
                }
                return new DiffuseMaterial(texBrush);
            }
            else
            {
                byte alphaByte = isTransparent ? (byte)Math.Clamp((int)(mat.Diffuse[3] * 255), 40, 255) : (byte)255;
                Color matColor = Color.FromArgb(
                    alphaByte,
                    (byte)Math.Clamp((int)(mat.Diffuse[0] * 255), 0, 255),
                    (byte)Math.Clamp((int)(mat.Diffuse[1] * 255), 0, 255),
                    (byte)Math.Clamp((int)(mat.Diffuse[2] * 255), 0, 255)
                );
                var solidBrush = new SolidColorBrush(matColor);
                solidBrush.Freeze();
                return new DiffuseMaterial(solidBrush);
            }
        }
    }
}
