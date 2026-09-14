"""Current-input cover construction: corners. Source provenance is in the private port manifest."""

import itertools

import numpy as np

def _minimum_norm(planes, point):
    # Complete small-dimensional convex halfspace projection. All candidate
    # active sets are enumerated; no one-coordinate or camera-ray correction.
    normals=np.asarray([n for n,c in planes]);constants=np.asarray([c for n,c in planes])
    options=[]
    for size in range(4):
        for ids in itertools.combinations(range(len(planes)),size):
            if not ids:q=point.copy()
            else:
                a=normals[list(ids)];delta=constants[list(ids)]-a@point
                gram=a@a.T
                if np.linalg.matrix_rank(gram,tol=1e-12)<size:continue
                q=point+a.T@np.linalg.solve(gram,delta)
            if np.all(normals@q>=constants-1e-12):options.append(q)
    if not options:raise ValueError('No shared normal-stock inner corner')
    return min(options,key=lambda q:float(np.sum((q-point)**2)))
