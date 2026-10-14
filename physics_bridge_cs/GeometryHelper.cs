using System;
using System.Windows.Media;
using System.Windows.Media.Media3D;

namespace MmdPhysicsBridge
{
    // 3D形状生成用ヘルパークラス
    public static class GeometryHelper
    {
        // 球（剛体可視化用）
        public static ModelVisual3D CreateSphere(Point3D center, double radius, Color color, int slices = 12, int stacks = 8)
        {
            var mesh = new MeshGeometry3D();

            for (int stack = 0; stack <= stacks; stack++)
            {
                double phi = Math.PI * stack / stacks;
                double y = radius * Math.Cos(phi);
                double r = radius * Math.Sin(phi);

                for (int slice = 0; slice <= slices; slice++)
                {
                    double theta = 2.0 * Math.PI * slice / slices;
                    double x = r * Math.Cos(theta);
                    double z = r * Math.Sin(theta);

                    mesh.Positions.Add(new Point3D(center.X + x, center.Y + y, center.Z + z));
                }
            }

            for (int stack = 0; stack < stacks; stack++)
            {
                for (int slice = 0; slice < slices; slice++)
                {
                    int i0 = stack * (slices + 1) + slice;
                    int i1 = i0 + 1;
                    int i2 = (stack + 1) * (slices + 1) + slice;
                    int i3 = i2 + 1;

                    mesh.TriangleIndices.Add(i0);
                    mesh.TriangleIndices.Add(i2);
                    mesh.TriangleIndices.Add(i1);

                    mesh.TriangleIndices.Add(i1);
                    mesh.TriangleIndices.Add(i2);
                    mesh.TriangleIndices.Add(i3);
                }
            }

            var material = new DiffuseMaterial(new SolidColorBrush(color));
            return new ModelVisual3D
            {
                Content = new GeometryModel3D(mesh, material)
            };
        }

        // ボックス（剛体可視化用）
        public static ModelVisual3D CreateBox(Point3D center, Vector3D size, Color color, Matrix3D? transform = null)
        {
            var mesh = new MeshGeometry3D();
            double hx = size.X * 0.5;
            double hy = size.Y * 0.5;
            double hz = size.Z * 0.5;

            Point3D[] corners = new Point3D[]
            {
                new(-hx, -hy, -hz), new(hx, -hy, -hz), new(hx, hy, -hz), new(-hx, hy, -hz),
                new(-hx, -hy, hz),  new(hx, -hy, hz),  new(hx, hy, hz),  new(-hx, hy, hz)
            };

            for (int i = 0; i < corners.Length; i++)
            {
                Point3D p = corners[i];
                if (transform.HasValue)
                {
                    p = transform.Value.Transform(p);
                }
                mesh.Positions.Add(new Point3D(center.X + p.X, center.Y + p.Y, center.Z + p.Z));
            }

            int[] faces = new int[]
            {
                0, 2, 1, 0, 3, 2, // 前
                5, 6, 4, 4, 6, 7, // 後
                4, 7, 0, 0, 7, 3, // 左
                1, 2, 5, 5, 2, 6, // 右
                3, 7, 2, 2, 7, 6, // 上
                4, 0, 5, 5, 0, 1  // 下
            };

            foreach (int idx in faces)
            {
                mesh.TriangleIndices.Add(idx);
            }

            var material = new DiffuseMaterial(new SolidColorBrush(color));
            return new ModelVisual3D
            {
                Content = new GeometryModel3D(mesh, material)
            };
        }

        // カプセル（剛体可視化用、Y軸に沿ったカプセル）
        public static ModelVisual3D CreateCapsule(Point3D center, double radius, double height, Color color, int slices = 10, int stacks = 4)
        {
            var mesh = new MeshGeometry3D();
            double halfH = height * 0.5;

            // 上半球 (0 から pi/2)
            for (int stack = 0; stack <= stacks; stack++)
            {
                double phi = (Math.PI * 0.5) * stack / stacks;
                double y = radius * Math.Cos(phi) + halfH;
                double r = radius * Math.Sin(phi);

                for (int slice = 0; slice <= slices; slice++)
                {
                    double theta = 2.0 * Math.PI * slice / slices;
                    double x = r * Math.Cos(theta);
                    double z = r * Math.Sin(theta);
                    mesh.Positions.Add(new Point3D(center.X + x, center.Y + y, center.Z + z));
                }
            }

            // 下半球 (pi/2 から pi)
            for (int stack = 0; stack <= stacks; stack++)
            {
                double phi = (Math.PI * 0.5) + (Math.PI * 0.5) * stack / stacks;
                double y = radius * Math.Cos(phi) - halfH;
                double r = radius * Math.Sin(phi);

                for (int slice = 0; slice <= slices; slice++)
                {
                    double theta = 2.0 * Math.PI * slice / slices;
                    double x = r * Math.Cos(theta);
                    double z = r * Math.Sin(theta);
                    mesh.Positions.Add(new Point3D(center.X + x, center.Y + y, center.Z + z));
                }
            }

            int totalRows = (stacks + 1) * 2;
            for (int s = 0; s < totalRows - 1; s++)
            {
                for (int slice = 0; slice < slices; slice++)
                {
                    int i0 = s * (slices + 1) + slice;
                    int i1 = i0 + 1;
                    int i2 = (s + 1) * (slices + 1) + slice;
                    int i3 = i2 + 1;

                    mesh.TriangleIndices.Add(i0);
                    mesh.TriangleIndices.Add(i2);
                    mesh.TriangleIndices.Add(i1);

                    mesh.TriangleIndices.Add(i1);
                    mesh.TriangleIndices.Add(i2);
                    mesh.TriangleIndices.Add(i3);
                }
            }

            var material = new DiffuseMaterial(new SolidColorBrush(color));
            return new ModelVisual3D
            {
                Content = new GeometryModel3D(mesh, material)
            };
        }

        // ボーン連結ライン（直方体で表現）
        public static ModelVisual3D CreateBoneLine(Point3D from, Point3D to, double thickness, Color color)
        {
            Vector3D dir = to - from;
            double len = dir.Length;
            if (len < 0.001) return new ModelVisual3D();

            dir.Normalize();
            Vector3D up = Math.Abs(dir.Y) > 0.99 ? new Vector3D(1, 0, 0) : new Vector3D(0, 1, 0);
            Vector3D right = Vector3D.CrossProduct(dir, up);
            right.Normalize();
            up = Vector3D.CrossProduct(right, dir);
            up.Normalize();

            right *= thickness * 0.5;
            up *= thickness * 0.5;

            var mesh = new MeshGeometry3D();
            Point3D[] pts = new Point3D[]
            {
                from - right - up, from + right - up, from + right + up, from - right + up,
                to - right - up,   to + right - up,   to + right + up,   to - right + up
            };

            foreach (var p in pts) mesh.Positions.Add(p);

            int[] faces = new int[]
            {
                0, 2, 1, 0, 3, 2, 5, 6, 4, 4, 6, 7,
                4, 7, 0, 0, 7, 3, 1, 2, 5, 5, 2, 6,
                3, 7, 2, 2, 7, 6, 4, 0, 5, 5, 0, 1
            };
            foreach (int idx in faces) mesh.TriangleIndices.Add(idx);

            var material = new DiffuseMaterial(new SolidColorBrush(color));
            return new ModelVisual3D
            {
                Content = new GeometryModel3D(mesh, material)
            };
        }

        // 地面グリッド
        public static ModelVisual3D CreateGrid(double size = 40.0, double step = 2.0)
        {
            var group = new Model3DGroup();
            Color gridColor = Color.FromArgb(60, 180, 180, 180);

            for (double x = -size; x <= size; x += step)
            {
                Color c = (Math.Abs(x) < 0.01) ? Color.FromArgb(160, 255, 100, 100) : gridColor;
                var line = CreateBoneLine(new Point3D(x, 0, -size), new Point3D(x, 0, size), 0.08, c);
                if (line.Content != null) group.Children.Add(line.Content);
            }

            for (double z = -size; z <= size; z += step)
            {
                Color c = (Math.Abs(z) < 0.01) ? Color.FromArgb(160, 100, 100, 255) : gridColor;
                var line = CreateBoneLine(new Point3D(-size, 0, z), new Point3D(size, 0, z), 0.08, c);
                if (line.Content != null) group.Children.Add(line.Content);
            }

            return new ModelVisual3D { Content = group };
        }
    }
}
