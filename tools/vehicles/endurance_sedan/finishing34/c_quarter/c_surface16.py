"""Corrected complete seal-route seeds and actual roof-edge tangent strip."""
import math
from .boundary02 import section, unit, cross, sub
from . import c_surface14 as previous

class Surface(previous.Surface):

    def __init__(self, rows, plan, side):
        super().__init__(rows, plan, side)
        roof = rows['LOD0_Roof']
        column = 0 if side == 'L' else 14
        self.roof_points = [[self.sign * p[0], p[1], p[2]] for p in roof['vertices'][17 * column:17 * (column + 1)]]
        self.roof_inside = [[self.sign * p[0], p[1], p[2]] for p in roof['vertices'][255 + 17 * column:255 + 17 * (column + 1)]]
        if len(self.roof_points) != 17:
            raise ValueError('Unexpected exact roof top/underside indexing')
        self.roof_rear = min((p[1] for p in self.roof_points))
        self.roof_s = (self.roof_rear - self.front) / (self.a[1] - self.front)
        self.top_points[0] = self.roof_edge(self.front)[0]
        lengths = [0.0]
        for a, b in zip(self.top_points, self.top_points[1:]):
            lengths.append(lengths[-1] + math.dist(a, b))
        self.us = sorted([v / lengths[-1] for v in lengths] + [0.045])
        top_us = [v / lengths[-1] for v in lengths]
        roof_d = self.roof_edge(self.front)[2]
        self.start_d[0] = [v * (self.a[1] - self.front) for v in roof_d]
        self.top = [previous.Cubic(list(zip(top_us, [p[k] for p in self.top_points])), (self.top_points[1][0] - self.top_points[0][0]) / top_us[1] if k == 0 else 0.0, (self.top_points[-1][k] - self.top_points[-2][k]) / (top_us[-1] - top_us[-2])) for k in range(3)]
        seal = rows['LOD0_BacklightSeal']
        inner_points = [(self.roof_s, self.roof_edge(self.roof_rear)[0])]
        sections = []
        for y in (-1.31, -1.38, -1.47, -1.58, -1.69, -1.8, -1.88):
            candidates = [s for s in section(seal, y) if self.sign * s['geometry_normal'][0] > 0.9 and min((self.sign * p[0] for p in s['points'])) > 0.65]
            if not candidates:
                raise ValueError(('Missing complete actual outer seal band', side, y))
            all_points = [p for s in candidates for p in s['points']]
            a = min(all_points, key=lambda p: p[2])
            b = max(all_points, key=lambda p: p[2])
            n = unit([sum((math.dist(*s['points']) * s['geometry_normal'][k] for s in candidates)) for k in range(3)])
            p = [(a[k] + b[k]) / 2 + 0.001 * n[k] for k in range(3)]
            p[0] *= self.sign
            parameter = (y - self.front) / (self.a[1] - self.front)
            inner_points.append((parameter, p))
            sections.append({'source_y': y, 'actual_complete_outer_band_ends': [a, b], 'all_native_triangles': [s['triangle'] for s in candidates], 'seed': p, 'not_a_finite_mating_certificate': True})
        inner_points.append((1.0, self.a))
        functions = [previous.Cubic([(s, p[k]) for s, p in inner_points], self.start_d[0][k], self.end_d[0][k]) for k in range(3)]
        self.inner = []
        for k in range(3):

            def value(s, k=k):
                if s <= self.roof_s:
                    return self.roof_edge(self.front + (self.a[1] - self.front) * s)[0][k]
                return functions[k](s)
            self.inner.append(value)
        self.controls.update({'inner': inner_points, 'upper': self.top_points, 'whole_seal_sections': sections, 'roof_seam_parameter': self.roof_s, 'roof_seam_top_edges': self.roof_points[:2], 'geometric_tangent_strip_u': 0.045, 'u_blend_end': 0.3, 's_blend_end': self.roof_s + 0.15})

    def roof_edge(self, y):
        ps = self.roof_points
        j = next((i for i in range(len(ps) - 1) if min(ps[i][1], ps[i + 1][1]) <= y <= max(ps[i][1], ps[i + 1][1])), 0 if y < ps[0][1] else len(ps) - 2)
        a, b = ps[j:j + 2]
        t = (y - a[1]) / (b[1] - a[1])
        p = [(1 - t) * a[k] + t * b[k] for k in range(3)]
        p[1] = y
        c, d = self.roof_inside[j:j + 2]
        inner = [(1 - t) * c[k] + t * d[k] for k in range(3)]
        return (p, inner, [(b[k] - a[k]) / (b[1] - a[1]) for k in range(3)])

    @staticmethod
    def smooth(t):
        t = max(0.0, min(1.0, t))
        return t * t * t * (10 + t * (-15 + 6 * t))

    def point(self, s, u):
        base = super().point(s, u)
        w_s = 1 - self.smooth((s - self.roof_s) / 0.15)
        w_u = 1 - self.smooth((u - 0.045) / 0.255)
        if w_s == 0 or w_u == 0:
            return base
        inside = super().point(s, 0.0)
        outside = super().point(s, 1.0)
        dy = outside[1] - inside[1]
        dx = outside[0] - inside[0]
        derivative = self.roof_edge(self.front)[2]
        direction = [dx, dy, derivative[2] * dy]
        linear = [inside[k] + u * direction[k] for k in range(3)]
        return [base[k] + w_s * w_u * (linear[k] - base[k]) for k in range(3)]

def make(original, rows, plan, side, encode):
    old = previous.Surface
    try:
        previous.Surface = Surface
        return previous.make(original, rows, plan, side, encode)
    finally:
        previous.Surface = old
