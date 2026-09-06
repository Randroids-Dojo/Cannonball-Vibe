// Alternating LODs cover complementary pixels through the same fade band.
// One value per MultiMesh group keeps materials and tree instances shared.
instance uniform bool tree_lod_inverse : instance_index(0) = false;

float tree_lod_threshold(vec2 pixel) {
	float noise = fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715))));
	return tree_lod_inverse ? 1.0 - noise : noise;
}
