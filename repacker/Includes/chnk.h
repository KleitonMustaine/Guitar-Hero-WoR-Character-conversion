#pragma once
#include <stddef.h>
#include <stdint.h>

#pragma pack(push, 1)

typedef struct 
{
    char     signature[4];       // 0x00: "CHNK"
    uint32_t header_size;        // 0x04: always 0x80
    uint32_t compressed_size;    // 0x08: size of the compressed data
    uint32_t next_chunk_dist;    // 0x0C: distance to the nearest chunk (0xFFFFFFFF = fim)
    uint32_t next_slot_size;     // 0x10: slot size (ignored)
    uint32_t decompressed_size;  // 0x14: original size of the data
    uint32_t output_offset;      // 0x18: Offset of the output data
    uint8_t  reserved[100];      // 0x1C to 0x80: zero fill or reserved
}CHNKHeader;

#pragma pack(pop)

void header_from_file(CHNKHeader *h);
unsigned char *chnk_comp(const unsigned char *data, size_t size, size_t *out_size, uint32_t *out_chnk, uint32_t *out_first_slot);
int chnk_decomp(const unsigned char *src, size_t src_size,unsigned char *dst, size_t dst_size);