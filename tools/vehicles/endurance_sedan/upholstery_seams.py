"""Seat cushion stitching following the actual piecewise planar pad surface."""
from fractions import Fraction as F
import math

import numpy as np


def section(pad, first, last, radius):
    """Intersect the original pad facets, then miter a four-point thread section.

    The cushion route is a straight line in XY. Its height follows every actual
    top-facet boundary, including native float32 deviations. No sampled-height
    interpolation or additional burial is used to hide an unsupported span.
    """
    if abs(first.y-last.y)>1e-12 or not first.x<last.x or radius<=0:
        raise ValueError('Expected an ordered transverse cushion seam')
    y=F(float(first.y))
    lo=F(float(first.x))
    hi=F(float(last.x))
    pad.data.calc_loop_triangles()
    vertices=[tuple(F(float(c)) for c in pad.matrix_world@v.co) for v in pad.data.vertices]
    facets=[]
    knots={lo,hi}
    for face in pad.data.loop_triangles:
        tri=[vertices[i] for i in face.vertices]
        a,b,c=tri
        cross=((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
        if cross<=0:
            continue
        if y<min(v[1] for v in tri) or y>max(v[1] for v in tri):
            continue
        facets.append((tri,cross))
        for p,q in zip(tri,tri[1:]+tri[:1]):
            if p[1]==q[1]:
                values=[p[0],q[0]] if p[1]==y else []
            elif min(p[1],q[1])<=y<=max(p[1],q[1]):
                values=[p[0]+(q[0]-p[0])*(y-p[1])/(q[1]-p[1])]
            else:
                values=[]
            knots.update(x for x in values if lo<x<hi)
    path=[]
    for x in sorted(knots):
        heights=[]
        for (a,b,c),denominator in facets:
            wb=((x-a[0])*(c[1]-a[1])-(y-a[1])*(c[0]-a[0]))/denominator
            wc=((b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]))/denominator
            if wb>=0 and wc>=0 and wb+wc<=1:
                heights.append(a[2]+wb*(b[2]-a[2])+wc*(c[2]-a[2]))
        if not heights:
            raise ValueError('Cushion seam escapes the actual front pad facets')
        point=(x,y,max(heights))
        # Remove only algebraically identical line subdivisions.
        while len(path)>1:
            a,b=path[-2:]
            if (b[0]-a[0])*(point[2]-b[2])!=(b[2]-a[2])*(point[0]-b[0]):
                break
            path.pop()
        path.append(point)
    points=np.array([[float(c) for c in p] for p in path],dtype=np.float64)
    tangents=np.diff(points,axis=0)
    lengths=np.linalg.norm(tangents,axis=1)
    if np.any(lengths<=1e-6):
        raise ValueError('Native cushion seam facet knots collapse')
    tangents/=lengths[:,None]
    normals=np.stack((-tangents[:,2],np.zeros(len(tangents)),tangents[:,0]),axis=1)
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    miters=[normals[0]]
    for a,b in zip(normals,normals[1:]):
        direction=a+b
        direction/=np.linalg.norm(direction)
        denominator=float(direction@a)
        if denominator<.98:
            raise ValueError('Cushion thread requires an excessive miter')
        miters.append(direction/denominator)
    miters.append(normals[-1])
    vertices=[]
    lateral=np.array([0.,1.,0.])
    for point,miter in zip(points,miters):
        center=point+miter*(radius*.85)
        vertices.extend((center+lateral*radius,center+miter*radius,
                         center-lateral*radius,center-miter*radius))
    if not all(math.isfinite(float(c)) for p in vertices for c in p):
        raise ValueError('Nonfinite cushion thread output')
    return [tuple(float(c) for c in p) for p in vertices], {
        'method':'Exact actual-facet intersection with offset-plane miter joins',
        'rings':len(path),'radius_m':radius,'maximum_normal_burial_m':radius*.15,
        'minimum_span_m':float(lengths.min()),
        'maximum_miter_ratio':max(float(np.linalg.norm(v)) for v in miters),
    }
