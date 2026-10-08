#include "archive.h"
#include "common.h"

#define INDEX_ENTRY_SIZE     32
#define END_OF_INDEX_MARKER  0x2CB3EF3B
#define CRC_OFFSET_IN_ENTRY  16

#define PATH_PREFIX          "c:/gh6_burn/data/"
#define PATH_PREFIX_LEN      (sizeof(PATH_PREFIX) - 1)
#define INITIAL_CAPACITY     1024

typedef struct {
    uint32_t crc;
    char *name;
} KeyName;

static KeyName *g_keys = NULL;
static size_t g_keys_count = 0;
static size_t g_keys_cap = 0;

static int cmp_key(const void *a, const void *b) {
    const KeyName *item_a = (const KeyName *)a;
    const KeyName *item_b = (const KeyName *)b;

    if (item_a->crc < item_b->crc) {
        return -1;
    }
    if (item_a->crc > item_b->crc) {
        return 1;
    }
    return 0;
}

const char *key_name(uint32_t crc) {
    KeyName search_key;
    search_key.crc = crc;
    search_key.name = NULL;

    KeyName *found_key = bsearch(&search_key, g_keys, g_keys_count, sizeof(KeyName), cmp_key);

    if (found_key != NULL) {
        return found_key->name;
    }

    return NULL;
}

int load_keys(const char *path) {
    FILE *file = fopen(path, "r");
    if (!file) {
        fprintf(stderr, "Failed to open the list\n");
        return -1;
    }

    unsigned int parsed_crc;
    char parsed_name[1024];
    char line_buffer[1024];

    while (fgets(line_buffer, sizeof(line_buffer), file)) {
        if (sscanf(line_buffer, "%x %1023[^\n]", &parsed_crc, parsed_name) != 2) {
            continue;
        }

        if (g_keys_count == g_keys_cap) {
            size_t new_cap;
            if (g_keys_cap == 0) {
                new_cap = INITIAL_CAPACITY;
            } else {
                new_cap = g_keys_cap * 2;
            }

            KeyName *new_keys = realloc(g_keys, new_cap * sizeof(KeyName));
            if (new_keys == NULL) {
                fclose(file);
                return -1;
            }
            g_keys = new_keys;
            g_keys_cap = new_cap;
        }

        char *clean_name = parsed_name;
        if (strncmp(clean_name, PATH_PREFIX, PATH_PREFIX_LEN) == 0) {
            clean_name += PATH_PREFIX_LEN;
        }

        g_keys[g_keys_count].crc = parsed_crc;
        g_keys[g_keys_count].name = strdup(clean_name);
        g_keys_count++;
    }

    fclose(file);

    qsort(g_keys, g_keys_count, sizeof(KeyName), cmp_key);
    return 0;
}

const unsigned char *find_entry(const unsigned char *idx, long size, uint32_t crc) {
    for (long offset = 0; offset + INDEX_ENTRY_SIZE <= size; offset += INDEX_ENTRY_SIZE) {
        const unsigned char *entry = idx + offset;

        if (be32(entry) == END_OF_INDEX_MARKER) {
            break;
        }
        if (be32(entry + CRC_OFFSET_IN_ENTRY) == crc) {
            return entry;
        }
    }

    return NULL;
}

unsigned char *find_last(unsigned char *idx, long size) {
    for (long offset = 0; offset + INDEX_ENTRY_SIZE <= size; offset += INDEX_ENTRY_SIZE) {
        unsigned char *entry = idx + offset;

        if (be32(entry) == END_OF_INDEX_MARKER) {
            return entry;
        }
    }

    return NULL;
}

int resolve_crc(const char *arg, uint32_t *crc) {
    char *end_ptr;
    unsigned long parsed_hex = strtoul(arg, &end_ptr, 16);

    if (*end_ptr == '\0' && strlen(arg) == 8) {
        *crc = (uint32_t)parsed_hex;
        return 0;
    }

    size_t matches = 0;
    for (size_t i = 0; i < g_keys_count; i++) {
        if (strstr(g_keys[i].name, arg) != NULL) {
            if (matches == 0) {
                *crc = g_keys[i].crc;
            }
            fprintf(stderr, "  %08X %s\n", g_keys[i].crc, g_keys[i].name);
            matches++;
        }
    }
    if (matches == 1) {
        return 0;
    }
    if (matches > 1) {
        fprintf(stderr, "'%s' matches %zu names, be more specific\n", arg, matches);
    }

    return -1;
}