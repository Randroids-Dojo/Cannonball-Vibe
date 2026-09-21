"""Bound both sides of the actual incident sheet-stock constraints."""
import itertools
import numpy as np
from .maths import plane_miter as minimum_miter
from .vectors import f32


def plane_miter(p,normals,anchors,depth=.001201,fixed_y=None):
    q,proof=minimum_miter(p,normals,anchors,depth,fixed_y)
    ceiling=.001999
    if proof['maximum_incident_stock_m']<=ceiling:return q,proof
    if fixed_y is not None:raise ValueError('Bounded fixed-Y stock needs a complete section construction')
    point=np.asarray(p);N=np.asarray(normals);offset=np.asarray([np.dot(n,np.asarray(a)-point)for n,a in zip(N,anchors)])
    A=np.concatenate([N,-N]);b=np.concatenate([offset-depth,ceiling-offset])
    target=-depth*N.mean(axis=0);valid=[]
    for count in range(1,min(3,len(A))+1):
        for ids in itertools.combinations(range(len(A)),count):
            C=A[list(ids)];gram=C@C.T
            if abs(np.linalg.det(gram))<1e-16:continue
            delta=target-C.T@np.linalg.solve(gram,C@target-b[list(ids)])
            if np.max(A@delta-b)<=1e-10:valid.append((float(np.dot(delta-target,delta-target)),delta,ids))
    if not valid:raise ValueError(('No common1.201..1.999mm finite sheet section',p,normals))
    _,delta,active=min(valid,key=lambda q:q[0]);q=f32(point+delta);stock=offset-N@(np.asarray(q)-point)
    return q,{'active':active,'diagonal_m':float(np.linalg.norm(np.asarray(q)-point)),
              'minimum_incident_stock_m':float(stock.min()),'maximum_incident_stock_m':float(stock.max()),
              'bounded_normal_stock_m':[depth,ceiling]}
