"""Final guarded distance LODs; the scene owner controls all source I/O."""
from .binding import digest, prepare, validate_context


def verify_current_front(*, context, expected_context_digest):
    """Verify the current front against its locked ordered construction chain.

    The original body and pre-front checkpoints come from the caller-bound
    construction companion. This does not replace the legacy shoulder checker
    against the separate pre-front source. No lower objects are required.
    """
    import bpy
    from . import front_feature_current
    validate_context(context, expected_context_digest)
    front = context['front_context']
    front_feature_current.bind(bpy.data.objects['LOD0_FrontBumper'], front)
    core = front['packet']['core']
    return {'schema': 'distance-lod-current-front-check38.v1',
        'input_lock_digest': context['expected_lock_digest'],
        'context_digest': expected_context_digest,
        'source': dict(context['input_lock']['roles']['source']),
        'construction': dict(context['input_lock']['roles']['construction']),
        'original_body_checkpoint_digest': digest(core['original_body']),
        'original_inlet_packet_digest': core['original_inlet_packet']['sha256'],
        'current_packet_digest': front['packet']['sha256'],
        'front_binding_digest': front['expected_binding_digest'],
        'proof': front['current_native_chain_proof']}


def apply(collection, lods, *, context, expected_context_digest):
    """Return final actual objects, proof and payload, including distant tires."""
    from . import api, tire
    validate_context(context, expected_context_digest)
    return tire.apply(collection, lods,
        binding=context['tire_binding'],
        expected_binding_digest=context['capture']['tire_binding_digest'],
        reference=context['reference'], api=api, material_capture=context['material_capture'],
        package=context['package'], optimization=context['optimization'], geometry=context['geometry'],
        surfaces=context['surfaces'], shell_certificate=context['shell_certificate'],
        profile=context['profile'], expected_profile_digest=context['capture']['profile_digest'],
        inherited_distance_only_names=context['embedded_specification']['original_packaging']
            ['distance_lod_revision23']['maximum_lod_zero_names'],
        raw_capture=context['raw_capture'], modifier_capture=context['modifier_capture'],
        front_context=context['front_context'])


__all__ = ['apply', 'prepare', 'digest', 'verify_current_front']
