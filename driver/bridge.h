// VRChat Translator audio bridge. Nonpaged, fixed-size storage; no file I/O.
#pragma once
#include <ntddk.h>

void VrctBridgeInitialize();
void VrctBridgeClear(bool musicInput = false);
void VrctBridgeWrite(const UCHAR* source, ULONG bytes, bool musicInput = false);
void VrctBridgeRead(UCHAR* destination, ULONG bytes, ULONGLONG* cursor, bool musicInput = false);
