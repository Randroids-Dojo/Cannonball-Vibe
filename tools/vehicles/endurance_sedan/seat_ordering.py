"""Stable native seat ordering operations; no file IO or historical mesh data."""
import math
import bpy
from mathutils import Vector


def angle(a, b):
    cross = (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    assert math.hypot(*a) > 0 and math.hypot(*b) > 0
    return math.degrees(math.atan2(math.hypot(*cross), sum(x*y for x,y in zip(a,b))))


def order(vertices, triangles):
    points = [tuple(v) for v in vertices]
    if len(set(points)) != len(points):
        raise ValueError('Coincident distinct native vertices require explicit topology ownership')
    selected = sorted(range(len(points)), key=lambda i: points[i])
    mapping = {old:new for new,old in enumerate(selected)}
    faces = []
    for index, face in enumerate(triangles):
        mapped = tuple(mapping[v] for v in face)
        rotation = min(range(3), key=lambda i: mapped[i:]+mapped[:i])
        faces.append((mapped[rotation:]+mapped[:rotation], index, rotation))
    faces.sort(key=lambda row:row[0])
    if len({row[0] for row in faces}) != len(faces):
        raise ValueError('Duplicate oriented native triangles are not reordered away')
    return selected, faces


def operations(recipe, encode):
    records = []
    original_reference = recipe._reference

    def reference(obj):
        name, vertices, triangles, normals = original_reference(obj)
        selected, faces = order(vertices, triangles)
        values = []
        for _,index,rotation in faces:
            row = normals[index]
            values.append(row[rotation:]+row[:rotation])
        return name, [vertices[i] for i in selected], [face for face,_,_ in faces], values

    def triangulate(obj):
        old = obj.data
        old.calc_loop_triangles()
        triangles = list(old.loop_triangles)
        selected, faces = order([v.co for v in old.vertices], [t.vertices for t in triangles])
        old_normals = [tuple(n.vector) for n in old.corner_normals]
        fields = []
        for face,index,rotation in faces:
            t = triangles[index]
            loops = list(t.loops)
            loops = loops[rotation:]+loops[:rotation]
            polygon = old.polygons[t.polygon_index]
            fields.append({'normal':[old_normals[i] for i in loops],
                'uvs':{layer.name:[tuple(layer.data[i].uv) for i in loops] for layer in old.uv_layers},
                'material':polygon.material_index, 'smooth':polygon.use_smooth})
        mesh = bpy.data.meshes.new(obj.name+'_CanonicalTriangles')
        mesh.from_pydata([tuple(old.vertices[i].co) for i in selected], [], [f for f,_,_ in faces])
        mesh.update()
        for mat in old.materials:
            mesh.materials.append(mat)
        for polygon,row in zip(mesh.polygons,fields):
            polygon.material_index, polygon.use_smooth = row['material'], row['smooth']
        for name in [layer.name for layer in old.uv_layers]:
            layer = mesh.uv_layers.new(name=name)
            values = [value for row in fields for value in row['uvs'][name]]
            for item,value in zip(layer.data,values):
                item.uv = value
            assert [tuple(item.uv) for item in layer.data] == values
        targets = [value for row in fields for value in row['normal']]
        encoding = encode(mesh,targets)
        maximum = max(angle(a,b.vector) for a,b in zip(targets,mesh.corner_normals))
        if not encoding['passed'] or maximum > .025:
            raise ValueError('Canonical native ordering changed requested corner field beyond .025 degrees')
        assert all(tuple(mesh.vertices[i].co) == tuple(old.vertices[j].co) for i,j in enumerate(selected))
        records.append({'name':obj.name,'triangles':len(faces),'vertices':len(selected),
            'exact_coordinates':True,'exact_uv_corners':True,'oriented_triangles_conserved':True,
            'target_to_native_degrees':maximum,'limit_degrees':.025,'encoding':encoding})
        obj.data = mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)

    return {'triangulate': triangulate, 'reference': reference, 'records': records}
