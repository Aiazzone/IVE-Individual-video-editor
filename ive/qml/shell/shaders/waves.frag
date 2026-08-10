#version 440
// The idle waves, computed per pixel - the PS4-menu technique.
//
// No geometry at all: every pixel evaluates a few layered sines, so the
// curves are as smooth as the screen resolution and there is nothing to
// segment. `time` grows forever and the sines wrap it naturally - an
// endless animation, not a loop, so there is no seam to catch.
//
// Each band is a soft ribbon: a thin bright crest line (narrow exponential
// around the curve) over a body that fades downwards (one-sided
// exponential). Three sines per band at unrelated frequencies keep the
// water from ever visibly repeating; alternating drift signs make
// neighbouring ribbons slide past each other.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;
    vec4 topColor;
    vec4 bottomColor;
    vec4 waveColor;
} ubuf;

float band(vec2 uv, float base, float amp, float freq,
           float drift, float swell, float phase)
{
    float y = base
        + sin(uv.x * freq + ubuf.time * drift + phase) * amp
        + sin(uv.x * freq * 2.13 - ubuf.time * swell + phase * 1.7) * amp * 0.35
        + sin(uv.x * freq * 0.47 + ubuf.time * swell * 0.6 + phase * 3.1) * amp * 0.5;
    float d = uv.y - y;
    float crest = exp(-abs(d) * 90.0) * 0.55;
    float body = d > 0.0 ? exp(-d * 5.0) * 0.30 : 0.0;
    return crest + body;
}

void main()
{
    vec2 uv = qt_TexCoord0;
    vec3 bg = mix(ubuf.topColor.rgb, ubuf.bottomColor.rgb,
                  smoothstep(0.0, 1.0, uv.y));
    float a = 0.0;
    a += band(uv, 0.40, 0.050, 4.9,  0.11, 0.070, 0.0);
    a += band(uv, 0.49, 0.070, 3.7, -0.08, 0.050, 1.9);
    a += band(uv, 0.58, 0.060, 5.7,  0.06, 0.090, 3.7);
    a += band(uv, 0.68, 0.080, 3.1, -0.05, 0.060, 5.1);
    a += band(uv, 0.77, 0.050, 6.3,  0.09, 0.040, 0.8);
    vec3 colour = bg + ubuf.waveColor.rgb * a;
    fragColor = vec4(colour, 1.0) * ubuf.qt_Opacity;
}
