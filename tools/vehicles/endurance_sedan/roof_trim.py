"""Editable cabin fittings seated on the evaluated molded headliner."""

from collections import Counter

import bpy

from . import geometry as geo
from . import surface_clip


def evaluated_vertices(obj):
    bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh()
    vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    return vertices


def install(collection, lod, mats, headliner):
    bpy.context.view_layer.update()
    evaluated=headliner.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
    vertices=[evaluated.matrix_world@v.co for v in mesh.vertices]
    underside=[]
    for triangle in mesh.loop_triangles:
        points=[vertices[i].copy() for i in triangle.vertices]
        if (points[1]-points[0]).cross(points[2]-points[0]).z < -1e-10:
            underside.append(list(reversed(points)))
    evaluated.to_mesh_clear()
    if not underside:raise RuntimeError('Headliner underside is absent')

    def patch(rect):
        return surface_clip.patch(underside,rect)

    def pad(name,rect,bottom,component):
        # Preserve the actual underside triangulation, so the mount is flush
        # over its whole footprint instead of intersecting a curved ceiling.
        vertices=[];indices={};faces=[]
        for triangle in patch(rect):
            face=[]
            for point in triangle:
                key=tuple(point)
                if key not in indices:indices[key]=len(vertices);vertices.append(list(point))
                face.append(indices[key])
            faces.append(tuple(face))
        count=len(vertices)
        edges=Counter(tuple(sorted((face[i],face[(i+1)%3]))) for face in faces for i in range(3))
        boundary=[(face[i],face[(i+1)%3]) for face in faces for i in range(3)
                  if edges[tuple(sorted((face[i],face[(i+1)%3]))) ]==1]
        if min(v[2] for v in vertices)-bottom<.002:raise RuntimeError('Cabin mounting pad is too thin')
        vertices += [[v[0],v[1],bottom] for v in vertices[:count]]
        faces += [tuple(i+count for i in reversed(face)) for face in list(faces)]
        faces += [(a,b,b+count,a+count) for a,b in boundary]
        obj=geo.mesh(name,vertices,faces,mats['trim'],collection,lod)
        obj['assembly_boundary']='Upper face mates with actual headliner underside; lower face mates with '+component
        obj['mounted_component']=component
        obj['support_clipping']='Exact shared-edge clipping, one float32 encoding; no rounded welding keys'
        return obj

    def fit_below(obj):
        points=evaluated_vertices(obj)
        rect=(min(p.x for p in points),max(p.x for p in points),min(p.y for p in points),max(p.y for p in points))
        low=min(p.z for triangle in patch(rect) for p in triangle)
        top=max(p.z for p in points)
        delta=low-.003-top
        obj.location.z+=delta
        obj['headliner_unmounted_gap_m']=.003
        return top+delta,delta

    for side in (-1,1):
        name='LOD0_Sunvisor_'+str(side)
        visor=geo.box(name,(side*.402,.005,1.345),(.353,.163,.016),mats['fabric'],collection,lod,radius=.006)
        top,_=fit_below(visor)
        for index,x in enumerate((side*.402-.09,side*.402+.09)):
            pad('LOD0_VisorMount_'+str(side)+'_'+str(index),(x-.009,x+.009,.044,.062),top,name)

    console=geo.box('LOD0_RoofConsole',(0,-.035,1.372),(.146,.213,.022),mats['trim'],collection,lod,radius=.008)
    top,delta=fit_below(console)
    console_bottom=min(p.z for p in evaluated_vertices(console))
    for side in (-1,1):
        lens=geo.box('LOD0_ReadingLens_'+str(side),(side*.042,-.058,1.358+delta),(.039,.080,.002),mats['headlight'],collection,lod,radius=.0005)
        lens.location.z+=console_bottom-max(p.z for p in evaluated_vertices(lens))
        lens['assembly_boundary']='Upper reading-lens face is flush with the roof-console underside'
    for index,y in enumerate((-.102,.030)):
        pad('LOD0_ConsoleMount_'+str(index),(-.011,.011,y-.009,y+.009),top,console.name)

    for side in (-1,1):
        x=side*.610;ys=(-.852,-.657);ends=[]
        name='LOD0_GrabHandle_'+str(side)
        for index,y in enumerate(ys):
            rect=(x-.010,x+.010,y-.010,y+.010)
            bottom=min(p.z for triangle in patch(rect) for p in triangle)-.004
            ends.append(bottom)
            pad('LOD0_HandleMount_'+str(side)+'_'+str(index),rect,bottom,name)
        points=[(x,ys[0],ends[0]),(x,ys[0],ends[0]-.017),(side*.595,-.842,1.315),
                (side*.595,-.671,1.315),(x,ys[1],ends[1]-.017),(x,ys[1],ends[1])]
        handle=geo.tube(name,points,.008,mats['trim'],collection,lod,sides=8)
        handle['assembly_boundary']='Both capped ends mate with the corresponding headliner mounting pad'
