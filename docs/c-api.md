# WIMF C ABI version 1 contract

`src/wimf_c.h` is the portable integration boundary for non-Python programs.
ABI version 1 is intentionally small and uses only fixed-width integers,
pointers, sizes, plain records, and C linkage.

## Versioning

- `WIMF_C_ABI_VERSION` and `wimf_abi_version()` identify the binary ABI.
- `wimf_codec_version()` identifies the codec release independently.
- The WIM2 bitstream version, C ABI version, and library release version are
  separate compatibility domains.
- Existing fields, enum values, function signatures, ownership rules, and
  exported symbol meanings will not change within ABI version 1.
- A breaking binary change requires ABI version 2 and a new shared-library
  major version.
- Call option initializer functions before setting fields. `struct_size` must
  match the ABI version used to compile the caller.

## Ownership and lifetime

- Input image, encoded-data, and metadata pointers remain caller-owned and must
  stay valid until the call returns.
- Successful output buffers are allocated by WIMF. Release them only with
  `wimf_buffer_free()` or `wimf_decoded_image_free()` from the same loaded library.
- Free functions accept null/empty records and clear released records, allowing
  cleanup paths to call them safely once.
- Status values and their fixed error messages are returned by value and require
  no cleanup.
- Do not copy an owning output record and free both copies.

## Threading

- Separate encode/decode calls may run concurrently; the native core has no
  mutable process-global codec state.
- A single options, input, or output record must not be mutated concurrently.
- `threads == 0` selects the library's conservative automatic worker count.
- Synchronous execution uses the calling thread. Threaded execution remains
  deterministic for identical inputs and options.
- Buffer free functions may be called from a different thread after the
  producing call has completed, provided no other thread uses the buffer.

## Errors and safety

- No C++ exception crosses the C boundary. Allocation failures become
  `WIMF_STATUS_RESOURCE_LIMIT`; unexpected exceptions become
  `WIMF_STATUS_INTERNAL`.
- On failure, output records are empty and safe to free.
- `WIMF_STATUS_CORRUPT_DATA` indicates malformed or checksum-invalid input;
  callers must not treat partial pixels as verified output.
- Decode expansion remains bounded by `max_output_bytes`.

## Metadata

Metadata is a sized UTF-8 JSON byte sequence and is not required to be
null-terminated. It is compressed, not encrypted.
