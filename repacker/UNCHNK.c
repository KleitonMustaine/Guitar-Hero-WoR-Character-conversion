#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "miniz.h"

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

//converts little endian to big endian
#define swapEndian32(x) __builtin_bswap32(x)

static void header_from_file(CHNKHeader *h){
    h->header_size = swapEndian32(h->header_size);
    h->compressed_size = swapEndian32(h->compressed_size);
    h->next_chunk_dist = swapEndian32(h->next_chunk_dist);
    h->next_slot_size = swapEndian32(h->next_slot_size);
    h->decompressed_size = swapEndian32(h->decompressed_size);
    h->output_offset = swapEndian32(h->output_offset);
}



int decompress_chnk(const char *input_path, const char *output_path){
    FILE *file = fopen (input_path, "rb");
    if(!file){
        printf("Failed to open the archive\n");
        return -1;
    }

    FILE *output = fopen(output_path, "wb");
    if(!output){
        printf("Failed to write the output archive\n");
        fclose(file);
        return -1;
    }

    CHNKHeader header;
    unsigned long int current_chnk_pos = 0;
    unsigned int chnk_count = 0;

    while(1){

        
        fseek(file, current_chnk_pos, SEEK_SET);
        if (fread(&header, 1, sizeof(CHNKHeader),file) != sizeof(CHNKHeader)){
            fprintf(stderr, "Failed to read the header at the offset 0x%lX\n", current_chnk_pos);
            break;
        }
        header_from_file(&header);
        if(memcmp(header.signature, "CHNK", 4) != 0){
            fprintf(stderr, "Invalid Signature at the 0x%lX", current_chnk_pos);
            break;
        }

        printf("Processing Chunk #%d | Compressed: %u bytes | Decompressed: %u bytes | Address: 0x%X\n", 
               chnk_count++, header.compressed_size, header.decompressed_size, header.output_offset);

        unsigned char *comp_buf = (unsigned char *)malloc(header.compressed_size);
        unsigned char *decomp_buf = (unsigned char *)malloc(header.decompressed_size);

        if (!comp_buf || !decomp_buf){
            fprintf(stderr, "Memory allocation error for the chunck #%d\n", chnk_count);
            free(comp_buf);
            free(decomp_buf);
            break;
        }

        fseek(file, current_chnk_pos + header.header_size, SEEK_SET);
        if (fread(comp_buf, 1, header.compressed_size, file) != header.compressed_size) {
            fprintf(stderr, "Error at reading Chunk data\n");
            free(comp_buf); free(decomp_buf);
            break;
        }

        mz_ulong addr_len = header.decompressed_size;

        size_t written = tinfl_decompress_mem_to_mem(decomp_buf, header.decompressed_size, comp_buf, header.compressed_size, 0);

        if(written == TINFL_DECOMPRESS_MEM_TO_MEM_FAILED || written != header.decompressed_size){
            fprintf(stderr, "Failed to decompress. Error code: %lld\n", written);
            free(comp_buf);
            free(decomp_buf);
            break;
        }
        fseek(output, header.output_offset, SEEK_SET);
        fwrite(decomp_buf, 1, addr_len, output);

        free(comp_buf);
        free(decomp_buf);

        if(header.next_chunk_dist == 0xFFFFFFFF){
            printf("End of the archive reached\n");
            break;
        }

        current_chnk_pos += header.next_chunk_dist;

    }
    fclose(file);
    fclose(output);

    return 0;

}

int recompress_chnk(const char *input_path, const char *output_path){
    FILE *file = fopen (input_path, "rb");
    if(!file){
        printf("Failed to open the archive\n");
        return -1;
    }

    FILE *output = fopen(output_path, "wb");
    if(!output){
        printf("Failed to write the output archive\n");
        fclose(file);
        return -1;
    }

    CHNKHeader header;
    unsigned long int current_bytes_written = 0;
    unsigned int pos = 0;

    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fseek(file, 0, SEEK_SET);

    if(size < 0){
        fprintf(stderr, "Failed to read the file\n");
        fclose(file);
        fclose(output);
        return -1;
    }

    unsigned char *buffer = malloc(size);

    if(!buffer){
        fprintf(stderr, "Out of memory\n");
        fclose(file);
        fclose(output);
        return -1;
    }

    fread(buffer, 1, size, file);

    unsigned int count = (size + 0x7FFFF) / 0x80000;

    unsigned char **comp = malloc(count * sizeof *comp);
    if(!comp){
        fprintf(stderr, "Out of memory\n");
        fclose(file);
        fclose(output);
        return -1;
    }

    size_t *comp_size = malloc(count * sizeof *comp_size);
        if(!comp_size){
        fprintf(stderr, "Out of memory\n");
        fclose(file);
        fclose(output);
        return -1;
    }
    uint32_t *slot = malloc(count * sizeof *slot);
        if(!slot){
        fprintf(stderr, "Out of memory\n");
        fclose(file);
        fclose(output);
        return -1;
    }

    for(unsigned int i = 0; i < count; i++){
        unsigned char *src = buffer + i * 0x80000;

        size_t piece = size - i * 0x80000;
        
        if(piece > 0x80000){
            piece = 0x80000;
        }
        comp[i] = tdefl_compress_mem_to_heap(src, piece, &comp_size[i], TDEFL_DEFAULT_MAX_PROBES);

        if(comp[i] == NULL){
            fprintf(stderr,"Compression Failed\n");
            return -1;
        }
        slot[i] = (0x80 + comp_size[i] + 0x7FF) & ~0x7FF;

    }

    for(unsigned int i = 0; i < count; i++){
        memset(&header, 0, sizeof header);

        memcpy(header.signature, "CHNK", 4);
        header.header_size = 0x80;
        header.compressed_size = comp_size[i];

        size_t piece = size - i * 0x80000;
        if (piece > 0x80000){
            piece = 0x80000;
        } 

        header.decompressed_size = piece;

        header.output_offset = i * 0x80000;

        if (i == count - 1) {
            header.next_chunk_dist = 0xFFFFFFFF;
            header.next_slot_size  = 0;
        } else {
            header.next_chunk_dist = slot[i];
            header.next_slot_size  = slot[i + 1];
        }

        header_from_file(&header);

        fwrite(&header, 1, sizeof header, output);
        fwrite(comp[i], 1, comp_size[i], output);

        size_t pad = slot[i] - 0x80 - comp_size[i];
        for (size_t j = 0; j < pad; j++){
            fputc(0, output);
        }
            
       mz_free(comp[i]);
    }

    free(slot);
    free(comp_size);
    free(comp);
    free(buffer);
    fclose(output);
    fclose(file);
    return -1;
}

int main(int argc, char **argv){

    if (argc != 4) {
        fprintf(stderr, "use: %s d|c <input> <output>\n", argv[0]);
        return 1;
    }
    if (strcmp(argv[1], "d") == 0)
        return decompress_chnk(argv[2], argv[3]) == 0 ? 0 : 1;
    if (strcmp(argv[1], "c") == 0)
        return recompress_chnk(argv[2], argv[3]) == 0 ? 0 : 1;

    fprintf(stderr, "unknown mode '%s' (use d or c)\n", argv[1]);
    return 1;
}

