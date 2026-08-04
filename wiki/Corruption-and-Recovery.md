# Corruption and recovery

WIMF separates three concepts:

1. **Detection:** headers, directories, tile payloads, and extensions are validated.
2. **Containment:** independently decodable tiles prevent one damaged payload from cascading through the image.
3. **Recovery:** optional anti-rot parity can reconstruct damage within its bounded shard budget.

Strict decoding rejects invalid offsets, unknown modes, checksum failures, truncated entropy streams, unsafe expansion sizes, and malformed extensions.

Diagnostic preview is deliberately separate. It reconstructs verified tiles and replaces failed tiles with an obvious placeholder. The result is labeled unsafe and is not treated as a valid decode.

Do not describe a partially reconstructed preview as universal “corruption resistance.” Report the mutation area/count, verified tiles, failed tiles, repair status, and final pixel match.
