shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, unshaded;

uniform sampler2D mirror_left : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D mirror_right : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D mirror_rear : source_color, filter_linear_mipmap, repeat_enable;
instance uniform int mirror_index = -1;

void fragment() {
	vec2 mirror_uv = vec2(1.0 - UV.x, UV.y);
	if (mirror_index == 0) {
		ALBEDO = texture(mirror_left, mirror_uv).rgb;
	} else if (mirror_index == 1) {
		ALBEDO = texture(mirror_right, mirror_uv).rgb;
	} else if (mirror_index == 2) {
		ALBEDO = texture(mirror_rear, mirror_uv).rgb;
	} else {
		ALBEDO = vec3(0.0);
	}
}
