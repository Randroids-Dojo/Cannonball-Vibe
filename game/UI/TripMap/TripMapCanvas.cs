using Cannonball.Core.Simulation;
using Godot;

namespace Cannonball.Game.UI;

public sealed partial class TripMapCanvas : Control
{
    private const float MinimumZoom = 0.75f;
    private const float MaximumZoom = 8;
    private TripMapProjectionState? _state;
    private Vector2 _pan;
    private float _zoom = 1;
    private TripMapPoint _minimum;
    private TripMapPoint _maximum;
    private int _drawBatchCount;

    public float Zoom => _zoom;
    public Vector2 Pan => _pan;
    public int DrawBatchCount => _drawBatchCount;

    public override void _Ready()
    {
        MouseFilter = MouseFilterEnum.Stop;
        SetMeta("automation_id", "trip-map.canvas");
    }

    public override void _Draw()
    {
        DrawMapBackground();
        if (_state is null)
        {
            return;
        }
        _drawBatchCount = 0;
        DrawSegments(_state.Alternatives.SelectMany(alternative => alternative.Segments),
            new Color("091019"), 7, countBatch: false);
        DrawSegments(_state.Alternatives.SelectMany(alternative => alternative.Segments),
            new Color("8b9aad"), 3);
        DrawSegments(_state.Planned, new Color("091019"), 14, countBatch: false);
        DrawSegments(_state.Planned, new Color("eaf1f8"), 8);
        DrawSegments(_state.Traveled, new Color("091019"), 18, countBatch: false);
        DrawSegments(_state.Traveled, new Color("25d0a5"), 11);

        foreach (var feature in _state.UpcomingFeatures)
        {
            DrawFeatureMarker(feature);
        }
        DrawSquareMarker(_state.Start, new Color("f4f7fb"), 10);
        DrawDiamondMarker(_state.Destination, new Color("ff6674"), 13);
        DrawMarker(_state.Current, new Color("4cb5ff"), 15);
        DrawLine(
            ToCanvas(_state.Current) + new Vector2(0, -22),
            ToCanvas(_state.Current) + new Vector2(0, 22),
            Colors.White,
            3);
    }

    public void SetState(TripMapProjectionState state)
    {
        _state = state;
        var allPoints = state.Traveled.Concat(state.Planned)
            .SelectMany(segment => segment.Points)
            .Concat(state.Alternatives.SelectMany(alternative =>
                alternative.Segments.SelectMany(segment => segment.Points)))
            .Append(state.Start)
            .Append(state.Destination)
            .ToArray();
        _minimum = new TripMapPoint(
            allPoints.Min(candidate => candidate.XMeters),
            allPoints.Min(candidate => candidate.YMeters));
        _maximum = new TripMapPoint(
            allPoints.Max(candidate => candidate.XMeters),
            allPoints.Max(candidate => candidate.YMeters));
        Recenter();
    }

    public void PanBy(Vector2 delta)
    {
        var limit = new Vector2(Math.Max(80, Size.X * 0.45f), Math.Max(80, Size.Y * 0.45f));
        _pan = new Vector2(
            Math.Clamp(_pan.X + delta.X, -limit.X, limit.X),
            Math.Clamp(_pan.Y + delta.Y, -limit.Y, limit.Y));
        QueueRedraw();
    }

    public void ZoomBy(float factor)
    {
        _zoom = Math.Clamp(_zoom * factor, MinimumZoom, MaximumZoom);
        QueueRedraw();
    }

    public void Recenter()
    {
        _pan = Vector2.Zero;
        _zoom = 1;
        QueueRedraw();
    }

    private void DrawMapBackground()
    {
        DrawRect(new Rect2(Vector2.Zero, Size), new Color("101a27"));
        const float gridStep = 80;
        var minor = new Color(0.20f, 0.29f, 0.39f, 0.22f);
        for (var x = gridStep; x < Size.X; x += gridStep)
        {
            DrawLine(new Vector2(x, 0), new Vector2(x, Size.Y), minor, 1);
        }
        for (var y = gridStep; y < Size.Y; y += gridStep)
        {
            DrawLine(new Vector2(0, y), new Vector2(Size.X, y), minor, 1);
        }
        DrawRect(
            new Rect2(new Vector2(1, 1), Size - new Vector2(2, 2)),
            new Color("34485e"),
            filled: false,
            width: 2);
    }

    private void DrawSegments(
        IEnumerable<TripMapPathSegment> segments,
        Color color,
        float width,
        bool countBatch = true)
    {
        var batch = new List<Vector2>();
        void Flush()
        {
            if (batch.Count >= 2)
            {
                DrawPolyline(batch.ToArray(), color, width, antialiased: true);
                if (countBatch)
                {
                    _drawBatchCount++;
                }
            }
            batch.Clear();
        }

        foreach (var segment in segments)
        {
            var points = new Vector2[segment.Points.Count];
            for (var index = 0; index < segment.Points.Count; index++)
            {
                points[index] = ToCanvas(segment.Points[index]);
            }
            if (points.Length < 2)
            {
                continue;
            }
            if (batch.Count > 0 && batch[^1].DistanceSquaredTo(points[0]) > 0.01f)
            {
                Flush();
            }
            var startIndex = batch.Count == 0 ? 0 : 1;
            for (var index = startIndex; index < points.Length; index++)
            {
                batch.Add(points[index]);
            }
        }
        Flush();
    }

    private void DrawMarker(TripMapPoint point, Color color, float radius)
    {
        var center = ToCanvas(point);
        DrawCircle(center, radius + 3, new Color("121a25"));
        DrawCircle(center, radius, color);
        DrawCircle(center, radius * 0.38f, Colors.White);
    }

    private void DrawSquareMarker(TripMapPoint point, Color color, float radius)
    {
        var center = ToCanvas(point);
        var shadow = new Rect2(
            center - Vector2.One * (radius + 3),
            Vector2.One * (radius + 3) * 2);
        var marker = new Rect2(center - Vector2.One * radius, Vector2.One * radius * 2);
        DrawRect(shadow, new Color("091019"));
        DrawRect(marker, color);
        DrawRect(marker.Grow(-4), new Color("101a27"));
    }

    private void DrawDiamondMarker(TripMapPoint point, Color color, float radius)
    {
        var center = ToCanvas(point);
        DrawColoredPolygon(Diamond(center, radius + 4), new Color("091019"));
        DrawColoredPolygon(Diamond(center, radius), color);
        DrawColoredPolygon(Diamond(center, radius * 0.42f), new Color("101a27"));
    }

    private void DrawFeatureMarker(TripMapFeature feature)
    {
        var center = ToCanvas(feature.Position);
        var accent = new Color("f6bd55");
        switch (feature.Kind)
        {
            case TripMapFeatureKind.HighwayTransfer:
                DrawColoredPolygon(Diamond(center, 12), new Color("091019"));
                DrawColoredPolygon(Diamond(center, 9), accent);
                DrawColoredPolygon(Diamond(center, 4), new Color("101a27"));
                break;
            case TripMapFeatureKind.ServiceStop:
                DrawRect(
                    new Rect2(center - Vector2.One * 10, Vector2.One * 20),
                    new Color("091019"));
                DrawRect(
                    new Rect2(center - Vector2.One * 7, Vector2.One * 14),
                    accent);
                DrawCircle(center, 3, new Color("101a27"));
                break;
            default:
                DrawCircle(center, 11, new Color("091019"));
                DrawCircle(center, 8, accent);
                DrawCircle(center, 3, new Color("101a27"));
                break;
        }
    }

    private static Vector2[] Diamond(Vector2 center, float radius) =>
    [
        center + Vector2.Up * radius,
        center + Vector2.Right * radius,
        center + Vector2.Down * radius,
        center + Vector2.Left * radius,
    ];

    private Vector2 ToCanvas(TripMapPoint point)
    {
        if (_state is null)
        {
            return Vector2.Zero;
        }
        var minimumX = _minimum.XMeters;
        var maximumX = _maximum.XMeters;
        var minimumY = _minimum.YMeters;
        var maximumY = _maximum.YMeters;
        var spanX = Math.Max(1, maximumX - minimumX);
        var spanY = Math.Max(1, maximumY - minimumY);
        var padding = 72f;
        var scale = Math.Min(
            Math.Max(1, Size.X - (padding * 2)) / (float)spanX,
            Math.Max(1, Size.Y - (padding * 2)) / (float)spanY) * _zoom;
        var contentWidth = (float)spanX * scale;
        var contentHeight = (float)spanY * scale;
        return new Vector2(
            ((float)(point.XMeters - minimumX) * scale) + ((Size.X - contentWidth) / 2),
            ((float)(maximumY - point.YMeters) * scale) + ((Size.Y - contentHeight) / 2)) + _pan;
    }
}
