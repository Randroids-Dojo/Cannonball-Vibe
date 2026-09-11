"""Editable rear lamps fitted to the original body and moving trunk envelope."""

from . import geometry as geo
from . import model


def strip(name, cx, cz, width, height, depths, material, collection, parent,
          steps=16, vertical_steps=1, common_upper_grid=False):
    """Closed ribbon with a formed interior; all layers share the body ray."""
    xs = [cx-width/2+width*i/steps for i in range(steps+1)]
    zs = [cz-height/2+height*j/vertical_steps for j in range(vertical_steps+1)]
    if common_upper_grid:
        # Different X grids created a real intersection along a nonplanar seat.
        # Keep the cover/backplate stations and add only the outer frame margins.
        xs = [cx-.209]+[cx-.207+.414*i/16 for i in range(17)]+[cx+.209]
        zs = [.926, .930]
    stride = len(zs)
    layer = len(xs)*stride
    vertices = [(x, model.rear_surface_y(x,z)+depth, z)
                for depth in depths for x in xs for z in zs]
    faces = []
    for i in range(len(xs)-1):
        for j in range(stride-1):
            a, b = i*stride+j, (i+1)*stride+j
            faces.extend([(a,b,b+1,a+1), (a+layer,a+1+layer,b+1+layer,b+layer)])
    boundary = [i*stride for i in range(len(xs))]
    boundary += [(len(xs)-1)*stride+j for j in range(1,stride)]
    boundary += [i*stride+stride-1 for i in reversed(range(len(xs)-1))]
    boundary += [j for j in reversed(range(1,stride-1))]
    faces.extend((a,a+layer,b+layer,b) for a,b in zip(boundary,boundary[1:]+boundary[:1]))
    obj = geo.mesh(name,vertices,faces,material,collection,parent,smooth=True)
    # Apply after native float32 vertex creation, matching the independently
    # checked construction. The outward face remains at its original contour.
    for index, vertex in enumerate(obj.data.vertices):
        factor = min(1., max(0., (vertex.co.z-.868)/.058))
        vertex.co.z -= .010*(depths[index//layer]/.087)*factor
    obj.data.update()
    geo.project_uv(obj)
    obj['fit_surface'] = 'Original pre-cut rear body Y(X,Z); shared ray and frame seating grid'
    obj['upper_interior_relief_m'] = .010
    return obj


def build(side, symbol, collection, lod, mats, pivots):
    """One complete original lamp: backplate, four walls, cover and emitters."""
    cx = side*.65
    strip('LOD0_TaillightHousing_'+symbol,cx,.868,.414,.116,(.081,.087),
          mats['trim'],collection,lod,vertical_steps=4)
    for z in (.808,.928):
        strip('LOD0_TaillightWall_'+symbol+str(z),cx,z,.418,.004,(0.,.087),
              mats['trim'],collection,lod,common_upper_grid=z==.928)
    strip('LOD0_TaillightCover_'+symbol,cx,.868,.414,.116,(0.,.003),
          mats['optical_glass'],collection,lod,vertical_steps=4)
    for end in (-1,1):
        wall = strip('LOD0_TaillightSideReturn_'+symbol+str(end),cx+end*.208,
                     .868,.002,.116,(0.,.087),mats['trim'],collection,lod,
                     steps=1,vertical_steps=4)
        wall['assembly_boundary'] = 'Closed side return with individually checked cover and frame seats'
    for dz in (-.036,.036):
        obj = strip('LOD0_TailGuide_'+symbol+str(dz),cx,.868+dz,.389,.009,
                    (.018,.023),mats['taillight'],collection,lod)
        geo.parent_at_pivot(obj,pivots['Light_Tail_R'+symbol])
    for label,x,z,w,h,material,anchor in (
        ('BrakeEmitter',cx,.884,.354,.015,mats['brake'],'Light_Brake_'+symbol),
        ('ReverseEmitter',side*.54,.85,.120,.014,mats['reverse'],'Light_Reverse_'+symbol),
        ('RearIndicator',side*.737,.85,.133,.014,mats['indicator_left' if side<0 else 'indicator_right'],'Light_Indicator_R'+symbol)):
        obj = strip('LOD0_'+label+'_'+symbol,x,z,w,h,(.018,.023),material,collection,lod)
        geo.parent_at_pivot(obj,pivots[anchor])
