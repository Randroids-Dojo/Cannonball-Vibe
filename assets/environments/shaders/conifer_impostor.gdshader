shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

#include "conifer_lod_fade.gdshaderinc"

uniform sampler2D tree_albedo : source_color, filter_linear_mipmap_anisotropic;

void fragment() {
	if (ALPHA <= tree_lod_threshold(FRAGCOORD.xy)) {
		discard;
	}
	vec4 sample = texture(tree_albedo, UV);
	ALPHA = sample.a;
	ALPHA_SCISSOR_THRESHOLD = 0.45;
	ALBEDO = sample.rgb * vec3(0.50, 0.58, 0.44);
	ROUGHNESS = 0.9;
	SPECULAR = 0.5;
}
