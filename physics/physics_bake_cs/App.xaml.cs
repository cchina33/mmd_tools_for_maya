using System;
using System.IO;
using System.Windows;

namespace PhysicsSimulationBakeViewer
{
    public partial class App : Application
    {
        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);

            // カレントディレクトリを自身の実行ファイル配置フォルダに明示設定 (ネイティブDLLの探索を安定化)
            try
            {
                Directory.SetCurrentDirectory(AppContext.BaseDirectory);
            }
            catch
            {
                // 設定失敗時は続行
            }

            // 未処理例外を標準エラー出力へ通知し、Maya側のログで捕捉可能にする
            DispatcherUnhandledException += (s, args) =>
            {
                Console.Error.WriteLine($"[WPF UIスレッド例外] {args.Exception.Message}\n{args.Exception.StackTrace}");
                Console.Error.Flush();
            };
            AppDomain.CurrentDomain.UnhandledException += (s, args) =>
            {
                if (args.ExceptionObject is Exception ex)
                {
                    Console.Error.WriteLine($"[未処理例外] {ex.Message}\n{ex.StackTrace}");
                    Console.Error.Flush();
                }
            };

            string pmxPath = "";
            string vmdPath = "";
            string? outVmdPath = null;
            int lookahead = 16;
            double warmupSeconds = 2.0;
            int? startFrame = null;
            int? endFrame = null;
            int substepHz = 120;

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
                else if ((a.Equals("--substep", StringComparison.OrdinalIgnoreCase) || a.Equals("--substep-hz", StringComparison.OrdinalIgnoreCase)) && i + 1 < args.Length)
                {
                    if (int.TryParse(args[++i], out int sh))
                    {
                        substepHz = Math.Clamp(sh, 60, 480);
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

            // VMDモーションが指定されていない場合の対応 (CLI連携モード時はダイアログを出さず初期ポーズで進行)
            if (string.Equals(vmdPath, "none", StringComparison.OrdinalIgnoreCase))
            {
                vmdPath = "";
            }
            else if (string.IsNullOrWhiteSpace(vmdPath) || !File.Exists(vmdPath))
            {
                bool isCliMode = args.Any(a => a.Equals("--pmx", StringComparison.OrdinalIgnoreCase));
                if (!isCliMode)
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
            }

            var wnd = new ViewerWindow(pmxPath, vmdPath, outVmdPath, lookahead, warmupSeconds, startFrame, endFrame, substepHz);
            wnd.Show();
        }
    }
}
