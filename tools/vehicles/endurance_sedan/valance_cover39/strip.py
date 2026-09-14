"""Current-input cover construction: strip. Source provenance is in the private port manifest."""

import math

import numpy as np

def triangles(vertices, left, right):
    left=[v for i,v in enumerate(left) if i==0 or v!=left[i-1]]
    right=[v for i,v in enumerate(right) if i==0 or v!=right[i-1]]
    if len(set(left))!=len(left) or len(set(right))!=len(right):raise ValueError('Nonconsecutive repeated chain knot')
    if min(len(left),len(right))<2 or set(left)&set(right):
        raise ValueError('Ruled strip needs two distinct complete chains')
    points=np.asarray(vertices,dtype=float)
    def score(t):
        p=points[t];edges=[float(np.linalg.norm(p[(i+1)%3]-p[i])) for i in range(3)]
        area=float(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0])))
        if area<=1e-14:return math.inf
        return area+1e-3*sum(e*e for e in edges)
    costs={(0,0):0.};previous={}
    for total in range(len(left)+len(right)-1):
        for i in range(len(left)):
            j=total-i
            if not 0<=j<len(right) or (i,j) not in costs:continue
            for ni,nj,t in ((i+1,j,[left[i],left[i+1] if i+1<len(left) else left[i],right[j]]),
                            (i,j+1,[left[i],right[j+1] if j+1<len(right) else right[j],right[j]])):
                if ni>=len(left) or nj>=len(right):continue
                value=costs[i,j]+score(t)
                if value<costs.get((ni,nj),math.inf):costs[ni,nj]=value;previous[ni,nj]=((i,j),t)
    key=(len(left)-1,len(right)-1)
    if key not in previous:raise ValueError('No finite noncollapsed ruled-strip triangulation')
    result=[]
    while key!=(0,0):key,t=previous[key];result.append(t)
    return result[::-1]
