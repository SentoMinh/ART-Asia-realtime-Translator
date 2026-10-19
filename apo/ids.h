#pragma once
#include <guiddef.h>
#include <propkeydef.h>
inline constexpr GUID CLSID_VrctMicApo = {0x512d15b9,0x38ae,0x42c4,{0x97,0x47,0xab,0xb9,0x88,0x25,0x21,0x21}};
inline constexpr PROPERTYKEY PKEY_VrctToken = {{0xa5e509a4,0xf54b,0x47d9,{0x99,0x4d,0x8b,0xb2,0xd4,0xea,0xdd,0x5f}},1};
inline constexpr PROPERTYKEY PKEY_VrctUserSid = {PKEY_VrctToken.fmtid,2};
// Explicit local-namespace option only for the standalone harness, not deployment.
inline constexpr PROPERTYKEY PKEY_VrctTestLocal = {PKEY_VrctToken.fmtid,3};
