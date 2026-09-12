"""Shared-edge clipping of evaluated support triangles without float32 cracks."""

import math
import struct
from fractions import Fraction

from mathutils import Vector


def _clip(poly, axis, bound, greater):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        inside_a=a[axis]>=bound if greater else a[axis]<=bound
        inside_b=b[axis]>=bound if greater else b[axis]<=bound
        if inside_a:result.append(a)
        if inside_a != inside_b:
            fraction=(bound-a[axis])/(b[axis]-a[axis])
            result.append(tuple(x+(y-x)*fraction for x,y in zip(a,b)))
    return list(dict.fromkeys(result))


def _native(point):
    return tuple(struct.unpack('<f',struct.pack('<f',float(value)))[0] for value in point)


def patch(triangles, rect):
    """Retain the support's true planes; round shared results only once.

    Opposite traversals of a shared edge produce exactly the same intersection
    before native encoding. No coordinate rounding key or positional welding
    determines whether an edge is internal to the clipped support patch.
    """
    if len(rect)!=4 or not all(math.isfinite(v) for v in rect):
        raise ValueError('Support rectangle is invalid')
    if rect[0]>=rect[1] or rect[2]>=rect[3]:
        raise ValueError('Support rectangle is empty')
    planes=[(0,Fraction(rect[0]),True),(0,Fraction(rect[1]),False),
            (1,Fraction(rect[2]),True),(1,Fraction(rect[3]),False)]
    result=[]
    for triangle in triangles:
        if len(triangle)!=3 or not all(math.isfinite(v) for p in triangle for v in p):
            raise ValueError('Support triangle is invalid')
        if (max(p[0] for p in triangle)<rect[0] or min(p[0] for p in triangle)>rect[1]
                or max(p[1] for p in triangle)<rect[2] or min(p[1] for p in triangle)>rect[3]):
            continue
        poly=[tuple(Fraction(float(v)) for v in point) for point in triangle]
        for axis,bound,greater in planes:
            if poly:poly=_clip(poly,axis,bound,greater)
        for index in range(1,len(poly)-1):
            a,b,c=poly[0],poly[index],poly[index+1]
            u=tuple(y-x for x,y in zip(a,b));v=tuple(y-x for x,y in zip(a,c))
            normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            if sum(value*value for value in normal)<=Fraction(4e-24):continue
            native=[_native(point) for point in (a,b,c)]
            if len(set(native))!=3:
                raise ValueError('Support clipping collapses under native encoding')
            result.append([Vector(point) for point in native])
    if not result:raise RuntimeError('Cabin fitting lies beyond its headliner support')
    return result
