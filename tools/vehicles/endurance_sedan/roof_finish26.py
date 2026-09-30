"""Current-scene roof recipes; all reference surfaces are read before mutation."""
import bpy
from . import corner_encoding as codec
from . import roof_feature26 as native
from . import roof_continuity08 as field
from . import roof_centers21 as centers
from . import roof_resection29 as resection
from . import roof_outer_section50 as outer
from . import roof_transition_field57 as transition
from . import roof_long_skin96 as long_skin
from . import roof_closure13 as closure


def install(obj, candidate):
    expected = native.row(candidate)
    expected['name'] = obj.name
    old = obj.data
    obj.data = candidate.data
    obj.modifiers.clear()
    bpy.data.objects.remove(candidate, do_unlink=True)
    if old.users == 0: bpy.data.meshes.remove(old)
    bpy.context.view_layer.update()
    assert native.row(obj) == expected


def apply():
    proof = []
    roof = native.row(bpy.data.objects['LOD0_Roof'])
    for side in ('L', 'R'):
        obj = bpy.data.objects['LOD0_StampedPillar_C' + side]
        rail = bpy.data.objects['LOD0_RoofSideRail_' + side]
        candidate, details = native.make(obj, roof, native.row(rail), side)
        install(obj, candidate)
        proof.append({'stage': 'feature', 'side': side, 'details': details})
        candidate, details = field.make(obj, native.row(obj), roof, 'outer_flare', codec.encode)
        install(obj, candidate)
        proof.append({'stage': 'continuity', 'side': side, 'details': details})
        # The closeout was authored against this real stage, before subsequent
        # outer C-pillar refinement. Its carrier surfaces remain unchanged.
        names = ['LOD0_Roof', 'LOD0_BacklightSeal', 'LOD0_PillarC_' + side,
                 'LOD0_DoorApertureSeal_R' + side]
        carriers = {name: native.row(bpy.data.objects[name]) for name in names}
        web, details = closure.make(obj, native.row(obj), None, carriers,
                                    bpy.data.materials['Material_Paint'])
        world = web.matrix_world.copy()
        web.parent = obj.parent
        web.matrix_world = world
        for collection in list(web.users_collection): collection.objects.unlink(web)
        for collection in obj.users_collection: collection.objects.link(web)
        web['assembly_boundary'] = 'Supplementary2mm roof closeout. Five named finite mounting domains and distributed roof support; no structural-load/weather simulation.'
        proof.append({'stage': 'closure', 'side': side, 'details': details})
        old = native.row(obj)
        candidate, details = centers.make(obj, old, field.station_ids(old), codec.encode)
        install(obj, candidate)
        proof.append({'stage': 'centers', 'side': side, 'details': details})
        candidate, details = resection.make(obj, native.row(obj), roof, native.row(rail),
                                             field.station_ids, codec.encode)
        install(obj, candidate)
        proof.append({'stage': 'resection', 'side': side, 'details': details})
        frame = native.row(bpy.data.objects['LOD0_DoorFrame_R' + side])
        profile = outer.make_surface(native.row(obj), native.row(rail), frame)
        staged = []
        for target, make in ((obj, outer.pillar), (rail, outer.rail)):
            candidate, details = make(target, native.row(target), frame, codec.encode, profile)
            staged.append((target, candidate))
            proof.append({'stage': 'outer', 'object': target.name, 'details': details})
        for target, candidate in staged: install(target, candidate)
        candidate, details = transition.make(obj, native.row(obj), codec.encode)
        install(obj, candidate)
        proof.append({'stage': 'transition-field', 'side': side, 'details': details})
        candidate, details, _ = long_skin.make(obj, native.row(obj), codec.encode)
        install(obj, candidate)
        proof.append({'stage': 'long-skin', 'side': side, 'details': details})
    return proof
