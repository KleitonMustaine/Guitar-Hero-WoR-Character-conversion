#pragma once
#include <stdint.h>

int load_keys(const char *path);
const char *key_name(uint32_t crc);
int resolve_crc(const char *arg, uint32_t *crc);
const unsigned char *find_entry(const unsigned char *idx, long size, uint32_t crc);
unsigned char *find_last(unsigned char *idx, long size);