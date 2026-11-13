#pragma once
#include <algorithm>
#include <cstdint>

// Four floats computed together, for the loops of snap_index.cpp.
//
// A Float4 holds 4 floats, called lanes. An operation on two Float4 applies to the 4 pairs
// of lanes, with one processor instruction where the processor has one. A comparison gives
// a Mask4: one yes or no per lane.
//
// Example, with values = {1, 5, 2, 9}:
//   Float4 a = load4(values);
//   Mask4 small = a <= fill4(2.0f);    // yes, no, yes, no
//   int bits = lane_bits(small);       // 0b0101: bit i is set if lane i says yes
//   Float4 b = select4(small, a, fill4(0.0f));   // {1, 0, 2, 0}
//
// The loops are written with these types, and not left to the compiler to transform. With
// g++ at -O3, a search is 1.3 to 2.5 times slower with the plain version below.
//
// There are three versions with the same results. SSE2 is part of every 64-bit x86
// processor. NEON is part of every 64-bit ARM processor. The plain version is for any other
// processor. No build of the project compiles the plain version on these two processors:
// define SCGRAPH_PLAIN_FLOAT4 to compile it on any processor, for a test by hand.

#if !defined(SCGRAPH_PLAIN_FLOAT4) && (defined(__SSE2__) || defined(_M_X64))
#include <emmintrin.h>

struct Float4 { __m128 lanes; };
struct Mask4 { __m128 lanes; };

inline Float4 load4(const float* values) { return {_mm_loadu_ps(values)}; }
inline void store4(float* values, Float4 a) { _mm_storeu_ps(values, a.lanes); }
inline Float4 fill4(float value) { return {_mm_set1_ps(value)}; }
inline Float4 operator+(Float4 a, Float4 b) { return {_mm_add_ps(a.lanes, b.lanes)}; }
inline Float4 operator-(Float4 a, Float4 b) { return {_mm_sub_ps(a.lanes, b.lanes)}; }
inline Float4 operator*(Float4 a, Float4 b) { return {_mm_mul_ps(a.lanes, b.lanes)}; }
inline Float4 min4(Float4 a, Float4 b) { return {_mm_min_ps(a.lanes, b.lanes)}; }
inline Float4 max4(Float4 a, Float4 b) { return {_mm_max_ps(a.lanes, b.lanes)}; }
inline Mask4 operator<=(Float4 a, Float4 b) { return {_mm_cmple_ps(a.lanes, b.lanes)}; }
inline Mask4 operator>=(Float4 a, Float4 b) { return {_mm_cmpge_ps(a.lanes, b.lanes)}; }
inline Mask4 operator&(Mask4 a, Mask4 b) { return {_mm_and_ps(a.lanes, b.lanes)}; }
// Lane by lane: the lane of `yes` where the mask says yes, else the lane of `no`
inline Float4 select4(Mask4 mask, Float4 yes, Float4 no) {
    return {_mm_or_ps(_mm_and_ps(mask.lanes, yes.lanes), _mm_andnot_ps(mask.lanes, no.lanes))};
}
// The mask as an integer: bit i is set if lane i says yes
inline int lane_bits(Mask4 mask) { return _mm_movemask_ps(mask.lanes); }

#elif !defined(SCGRAPH_PLAIN_FLOAT4) && (defined(__aarch64__) || defined(_M_ARM64))
#include <arm_neon.h>

struct Float4 { float32x4_t lanes; };
struct Mask4 { uint32x4_t lanes; };

inline Float4 load4(const float* values) { return {vld1q_f32(values)}; }
inline void store4(float* values, Float4 a) { vst1q_f32(values, a.lanes); }
inline Float4 fill4(float value) { return {vdupq_n_f32(value)}; }
inline Float4 operator+(Float4 a, Float4 b) { return {vaddq_f32(a.lanes, b.lanes)}; }
inline Float4 operator-(Float4 a, Float4 b) { return {vsubq_f32(a.lanes, b.lanes)}; }
inline Float4 operator*(Float4 a, Float4 b) { return {vmulq_f32(a.lanes, b.lanes)}; }
inline Float4 min4(Float4 a, Float4 b) { return {vminq_f32(a.lanes, b.lanes)}; }
inline Float4 max4(Float4 a, Float4 b) { return {vmaxq_f32(a.lanes, b.lanes)}; }
inline Mask4 operator<=(Float4 a, Float4 b) { return {vcleq_f32(a.lanes, b.lanes)}; }
inline Mask4 operator>=(Float4 a, Float4 b) { return {vcgeq_f32(a.lanes, b.lanes)}; }
inline Mask4 operator&(Mask4 a, Mask4 b) { return {vandq_u32(a.lanes, b.lanes)}; }
// Lane by lane: the lane of `yes` where the mask says yes, else the lane of `no`
inline Float4 select4(Mask4 mask, Float4 yes, Float4 no) {
    return {vbslq_f32(mask.lanes, yes.lanes, no.lanes)};
}
// The mask as an integer: bit i is set if lane i says yes
inline int lane_bits(Mask4 mask) {
    const uint32_t bit_of_lane[4] = {1, 2, 4, 8};
    return int(vaddvq_u32(vandq_u32(mask.lanes, vld1q_u32(bit_of_lane))));
}

#else

struct Float4 { float lanes[4]; };
struct Mask4 { bool lanes[4]; };

inline Float4 load4(const float* values) {
    return {{values[0], values[1], values[2], values[3]}};
}
inline void store4(float* values, Float4 a) {
    for (int i = 0; i < 4; ++i) values[i] = a.lanes[i];
}
inline Float4 fill4(float value) { return {{value, value, value, value}}; }
inline Float4 operator+(Float4 a, Float4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] += b.lanes[i];
    return a;
}
inline Float4 operator-(Float4 a, Float4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] -= b.lanes[i];
    return a;
}
inline Float4 operator*(Float4 a, Float4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] *= b.lanes[i];
    return a;
}
inline Float4 min4(Float4 a, Float4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] = a.lanes[i] < b.lanes[i] ? a.lanes[i] : b.lanes[i];
    return a;
}
inline Float4 max4(Float4 a, Float4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] = a.lanes[i] > b.lanes[i] ? a.lanes[i] : b.lanes[i];
    return a;
}
inline Mask4 operator<=(Float4 a, Float4 b) {
    Mask4 mask;
    for (int i = 0; i < 4; ++i) mask.lanes[i] = a.lanes[i] <= b.lanes[i];
    return mask;
}
inline Mask4 operator>=(Float4 a, Float4 b) {
    Mask4 mask;
    for (int i = 0; i < 4; ++i) mask.lanes[i] = a.lanes[i] >= b.lanes[i];
    return mask;
}
inline Mask4 operator&(Mask4 a, Mask4 b) {
    for (int i = 0; i < 4; ++i) a.lanes[i] = a.lanes[i] && b.lanes[i];
    return a;
}
// Lane by lane: the lane of `yes` where the mask says yes, else the lane of `no`
inline Float4 select4(Mask4 mask, Float4 yes, Float4 no) {
    for (int i = 0; i < 4; ++i) yes.lanes[i] = mask.lanes[i] ? yes.lanes[i] : no.lanes[i];
    return yes;
}
// The mask as an integer: bit i is set if lane i says yes
inline int lane_bits(Mask4 mask) {
    int bits = 0;
    for (int i = 0; i < 4; ++i) bits |= int(mask.lanes[i]) << i;
    return bits;
}

#endif

// The lowest of the 4 lanes
inline float lowest4(Float4 a) {
    float lanes[4];
    store4(lanes, a);
    return std::min(std::min(lanes[0], lanes[1]), std::min(lanes[2], lanes[3]));
}
