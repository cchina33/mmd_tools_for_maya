using System;
using System.IO;
using System.Windows;

namespace MmdPhysicsViewer
{
    public partial class App : Application
    {
        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);

            string pmxPath = "";
            string vmdPath = "";
            string? outVmdPath = null;
            int lookahead = 16;
            double warmupSeconds = 2.0;
            int? startFrame = null;
            int? endFrame = null;

            var args = e.Args;
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (a.Equals("--pmx", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    pmxPath = args[++i];
                }
                else if (a.Equals("--vmd", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    vmdPath = args[++i];
                }
                else if (a.Equals("--out-vmd", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    outVmdPath = args[++i];
                }
                else if (a.Equals("--lookahead", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    if (int.TryParse(args[++i], out int la))
                    {
                        lookahead = la;
                    }
                }
                else if (a.Equals("--warmup", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    if (double.TryParse(args[++i], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double wu))
                    {
                        warmupSeconds = Math.Max(0.0, wu);
                    }
                }
                else if (a.Equals("--start-frame", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    if (int.TryParse(args[++i], out int sf))
                    {
                        startFrame = sf;
                    }
                }
                else if (a.Equals("--end-frame", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
                {
                    if (int.TryParse(args[++i], out int ef))
                    {
                        endFrame = ef;
                    }
                }
            }

            // 引数が指定されていない場合のファイル選択ダイアログ対応 (単体起動時)
            if (string.IsNullOrWhiteSpace(pmxPath) || !File.Exists(pmxPath))
            {
                var ofdPmx = new Microsoft.Win32.OpenFileDialog
                {
                    Title = "表示するPMXモデルファイルを選択してください",
                    Filter = "PMXモデル (*.pmx)|*.pmx|全てのファイル (*.*)|*.*"
                };
                if (ofdPmx.ShowDialog() == true)
                {
                    pmxPath = ofdPmx.FileName;
                }
                else
                {
                    Shutdown(0);
                    return;
                }
            }

            // VMDモーションが指定されていない場合は任意選択、キャンセル時は空モーションでプレビュー
            if (string.IsNullOrWhiteSpace(vmdPath) || !File.Exists(vmdPath))
            {
                var ofdVmd = new Microsoft.Win32.OpenFileDialog
                {
                    Title = "適用するVMDモーションファイルを選択してください (キャンセルで初期ポーズ物理)",
                    Filter = "VMDモーション (*.vmd)|*.vmd|全てのファイル (*.*)|*.*"
                };
                if (ofdVmd.ShowDialog() == true)
                {
                    vmdPath = ofdVmd.FileName;
                }
            }

            var wnd = new ViewerWindow(pmxPath, vmdPath, outVmdPath, lookahead, warmupSeconds, startFrame, endFrame);
            wnd.Show();
        }
    }
}
