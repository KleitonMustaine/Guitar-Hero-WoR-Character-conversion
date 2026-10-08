#include "common.h"


unsigned char *load_file(const char *path, long *size)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;

    fseek(f, 0, SEEK_END);
    *size = ftell(f);
    fseek(f, 0, SEEK_SET);

    if (*size < 0) { 
        fclose(f); 
        return NULL; 
    } 
    size_t alloc_size;
    if(*size == 0){
        alloc_size =1;
    }else{
        alloc_size = (size_t)*size;
    }
        
    unsigned char *buf = malloc(alloc_size);

    if(buf){
        if(fread(buf,1, *size, f) != (size_t)*size){
            free(buf);
            buf = NULL;
        }
    }
    fclose(f);
    return buf;
}


//reads 4 bytes at p as a big endian number
uint32_t be32(const unsigned char *p){
    return (uint32_t)p[0] << 24 |
           (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8  |
           (uint32_t)p[3];
}


void put_be32(unsigned char *p, uint32_t v){
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}