"""Scope65 coherent whole-panel field and literal manufactured arch domains.

Connected fans use area times corner-angle weights, split at material or60deg
physical creases. The declared64-facet manufactured arch returns form a
separate radial guide domain. No old normal is sampled at a new point.
"""
import math
from collections import defaultdict
import numpy as np
def arch_faces(row):
    v=np.asarray(row['vertices']);t=np.asarray(row['triangles']);xyz=v[t];raw=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);n=raw/np.linalg.norm(raw,axis=1)[:,None];found={}
    for fi,ps in enumerate(xyz):
        if not np.all((np.abs(ps[:,0])>=.46-1e-6)&(np.abs(ps[:,0])<=1.3+1e-6)):continue
        for facet in range(64):
            a=(facet+.5)*math.tau/64;ny,nz=math.cos(a),math.sin(a)
            if n[fi]@np.array([0.,-ny,-nz])<.99999:continue
            plane=max(abs((p[1]-1.46)*ny+(p[2]-.3433)*nz-.4483*math.cos(math.pi/64))for p in ps)
            span=max(abs(-(p[1]-1.46)*nz+(p[2]-.3433)*ny)for p in ps)
            if plane<=1e-6 and span<=.4483*math.sin(math.pi/64)+1e-6:
                if fi in found:raise ValueError('Ambiguous finite arch domain')
                found[fi]={'facet':facet,'plane_error_m':plane,'tangent_extent_m':span}
    return found