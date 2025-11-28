"""TF/SD card flashing module.

This module handles:
- Device validation (whole-device only)
- Safe write operations with fsync
- Hash-based verification
- Dry-run and force modes

All operations follow the safety rules in docs/SAFETY.md:
- Explicit device paths only (no guessing)
- Pre-flight checks and optional wipe
- Synchronous, flushed writes
- Hash verification after write
"""
